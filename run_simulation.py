"""60-day benchmark: 30 days summer + 30 days polar night, three controllers.

Controllers
  always_on   Genset 1 every hour at clamp(load + 4.17, 24, 80) kW; wind/PV unused.
  rule        RuleBasedFallbackController (reactive, no forecast, no optimizer).
  polar_ems   24 h MILP, replanned every 6 h or on a blizzard flag, with every plan
              executed against ACTUAL load/wind/PV by simulation/executor.py.

Weather modes (the repo has no weather forecast model, so both ends are shown)
  true         The optimizer is given the true future weather. Upper bound.
  persistence  The optimizer is given yesterday's weather at the same hour. A naive,
               pessimistic bound; a real numerical forecast would land in between.

Usage: python run_simulation.py          (about 3-4 minutes)
Writes results/benchmark_results.json, which the dashboard and API read.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from polar_ems.config import DEFAULT_STATION_CONFIG
from polar_ems.forecasting.forecaster import PolarForecaster
from polar_ems.optimizer.milp_solver import PolarMILPOptimizer
from polar_ems.safety.fallback_controller import RuleBasedFallbackController
from polar_ems.simulation.executor import execute_hour
from polar_ems.simulation.microgrid import PolarMicrogridSimulator
from polar_ems.simulation.synthetic_data import generate_polar_dataset

CFG = DEFAULT_STATION_CONFIG
RESULTS_PATH = Path(__file__).resolve().parent / "results" / "benchmark_results.json"
WEATHER_MODES = ("true", "persistence")
DEFERRABLE_KW = 4.17  # 100 kWh/day flexible load served evenly by the baseline controllers

LIMITATIONS = [
    "All data is synthetic (polar_ems/simulation/synthetic_data.py); no station logs, ERA5, BSRN or AWS data were used.",
    "No weather forecast model exists. 'true' gives the optimizer the true weather (upper bound); 'persistence' gives it yesterday's weather (naive bound).",
    "Plans are executed against actual load, wind and PV by a simple re-balancing policy (executor.py), not an optimum; unplanned genset starts are counted.",
    "The always-on baseline never uses wind or PV, so part of every saving vs always-on is simply using renewables. The rule controller is a fallback, not a tuned station controller.",
    "The load model trains on the first 96 h of the series it is then scored on.",
    "Single synthetic series per season and no confidence intervals; run-to-run solver differences are about 0.1%.",
]


def _weather_window(ds, h, span, mode):
    if mode == "true":
        sl = slice(h, h + span)
        return ds.ambient_temp_c[sl], ds.wind_speed_ms[sl], ds.solar_irradiance_w_m2[sl]
    idx = [max(0, h + i - 24) for i in range(span)]
    return ([ds.ambient_temp_c[j] for j in idx], [ds.wind_speed_ms[j] for j in idx],
            [ds.solar_irradiance_w_m2[j] for j in idx])


def run_benchmark_month(season, days=30, weather_mode="true"):
    ds = generate_polar_dataset(season=season, days=days)
    sim = PolarMicrogridSimulator(CFG)
    forecaster = PolarForecaster(CFG)
    optimizer = PolarMILPOptimizer(CFG)
    rule_ctrl = RuleBasedFallbackController(CFG)
    fb_ctrl = RuleBasedFallbackController(CFG)   # used only when no valid plan exists
    n = ds.num_hours
    cut_out = CFG.wind.cut_out_speed_ms

    train = min(96, len(ds.critical_load_kw))
    forecaster.train_load_forecaster(hours=list(range(train)), temps=ds.ambient_temp_c[:train],
                                     loads=ds.critical_load_kw[:train])

    base_fuel = base_uns = 0.0
    rule_fuel = rule_uns = 0.0
    rule_soc, rule_on, rule_starts, rule_off = 0.65, True, 0, 0
    soc, g_on, g_run = 0.65, [True, False], [4, 0]
    fuel = uns = shed = curt = dfr_served = 0.0
    starts = off_hours = solves = failures = fallback_hours = unplanned = 0
    solve_ms, load_ape = [], []
    plan, plan_idx = None, 0
    keys = ("genset_kw", "batt_charge_kw", "batt_discharge_kw", "soc_polar_ems", "soc_rule_based",
            "demand_kw", "wind_kw", "pv_kw", "wind_speed_ms", "curtailed_kw", "unserved_kw")
    series = {k: [] for k in keys}

    for h in range(n):
        crit, pv, wind = ds.critical_load_kw[h], ds.raw_pv_kw[h], ds.raw_wind_kw[h]
        wspd, temp, blz = ds.wind_speed_ms[h], ds.ambient_temp_c[h], ds.blizzard_flags[h]
        wind_avail = 0.0 if wspd >= cut_out else wind
        eff_kwh, c_eff, d_eff = sim.get_effective_battery_capacity(temp)

        demand0 = crit + DEFERRABLE_KW
        bp = max(24.0, min(80.0, demand0))
        base_fuel += sim.calculate_genset_fuel(bp, True, genset_idx=0)
        base_uns += max(0.0, demand0 - 80.0)

        r = rule_ctrl.dispatch_step(critical_load_kw=crit, deferrable_load_kw=DEFERRABLE_KW, pv_kw=pv,
                                    wind_kw=wind, wind_speed_ms=wspd, current_soc=rule_soc, ambient_temp_c=temp)
        rule_fuel += r["fuel_l"]
        rule_uns += r["unserved_kw"]
        rule_off += int(r["diesel_off"])
        r_on = not r["diesel_off"]
        rule_starts += int(r_on and not rule_on)
        rule_on = r_on
        rule_soc = float(np.clip(rule_soc + (r["batt_charge_kw"] * c_eff - r["batt_discharge_kw"] / d_eff) / eff_kwh,
                                 CFG.battery.min_soc, CFG.battery.max_soc))

        if plan is None or plan_idx >= 6 or (blz and not getattr(plan, "blizzard_handled", False)):
            span = min(24, n - h)
            t_f, w_f, i_f = _weather_window(ds, h, span, weather_mode)
            fc = forecaster.forecast_horizon(current_hour=h, horizon_hours=span,
                                             past_loads=ds.critical_load_kw[max(0, h - 24):h],
                                             forecast_temps=t_f, forecast_wind_speeds=w_f, forecast_irradiances=i_f)
            new = optimizer.optimize_horizon(
                horizon_hours=span, initial_soc=soc, initial_genset_states=list(g_on), initial_run_hours=list(g_run),
                forecast_loads_kw=fc["forecast_load_kw"], forecast_pv_kw=fc["forecast_pv_kw"],
                forecast_wind_kw=fc["forecast_wind_kw"], forecast_wind_speeds=w_f, ambient_temps_c=t_f,
                blizzard_override=blz)
            if new.success:
                plan, plan.blizzard_handled, plan_idx = new, blz, 0
                solves += 1
                solve_ms.append(new.solve_duration_ms)
                for i in range(min(6, span)):
                    a = ds.critical_load_kw[h + i]
                    if a > 0:
                        load_ape.append(abs(fc["forecast_load_kw"][i] - a) / a)
            else:
                failures += 1

        if plan is not None and plan_idx < len(plan.genset1_kw):
            i = plan_idx
            x = execute_hour(sim, planned_g_kw=[plan.genset1_kw[i], plan.genset2_kw[i]],
                             planned_g_on=[plan.genset1_state[i], plan.genset2_state[i]],
                             planned_chg_kw=plan.batt_charge_kw[i], planned_dis_kw=plan.batt_discharge_kw[i],
                             planned_def_kw=plan.deferrable_kw[i], critical_kw=crit, wind_kw=wind_avail,
                             pv_kw=pv, soc=soc, ambient_temp_c=temp, prev_g_on=g_on)
            plan_idx += 1
            fuel += x.fuel_l
            uns += x.unserved_kw
            shed += x.deferrable_shed_kw
            curt += x.curtailed_kw
            dfr_served += x.deferrable_kw
            starts += sum(x.started)
            unplanned += int(x.unplanned_start)
            off_hours += int(not any(x.g_on))
            g_on = list(x.g_on)
            g_run = [g_run[k] + 1 if g_on[k] else 0 for k in (0, 1)]
            soc = x.soc
            g_tot, chg, dis, dfr, cu, un = sum(x.g_kw), x.chg_kw, x.dis_kw, x.deferrable_kw, x.curtailed_kw, x.unserved_kw
        else:
            f = fb_ctrl.dispatch_step(critical_load_kw=crit, deferrable_load_kw=DEFERRABLE_KW, pv_kw=pv,
                                      wind_kw=wind, wind_speed_ms=wspd, current_soc=soc, ambient_temp_c=temp)
            fallback_hours += 1
            fuel += f["fuel_l"]
            uns += f["unserved_kw"]
            dfr_served += DEFERRABLE_KW
            new_on = [bool(f["genset1_on"]), bool(f["genset2_on"])]
            starts += sum(new_on[k] and not g_on[k] for k in (0, 1))
            off_hours += int(not any(new_on))
            g_on = new_on
            g_run = [g_run[k] + 1 if g_on[k] else 0 for k in (0, 1)]
            soc = float(np.clip(soc + (f["batt_charge_kw"] * c_eff - f["batt_discharge_kw"] / d_eff) / eff_kwh,
                                CFG.battery.min_soc, CFG.battery.max_soc))
            g_tot, chg, dis, dfr, cu, un = f["genset1_kw"] + f["genset2_kw"], f["batt_charge_kw"], f["batt_discharge_kw"], DEFERRABLE_KW, f["curtailment_kw"], f["unserved_kw"]
            curt += cu

        for k, v in zip(keys, (g_tot, chg, dis, soc * 100.0, rule_soc * 100.0, crit + dfr + chg,
                               wind_avail, pv, wspd, cu, un)):
            series[k].append(round(float(v), 1))

    co2 = CFG.gensets[0].co2_kg_per_l_diesel
    days_n = n / 24.0
    gen_kwh = sum(series["genset_kw"])
    dem_kwh = sum(c + DEFERRABLE_KW for c in ds.critical_load_kw)
    return {
        "season": season, "weather_mode": weather_mode, "hours": n, "days": days,
        "always_on_fuel_l": base_fuel, "rule_fuel_l": rule_fuel, "polar_ems_fuel_l": fuel,
        "saving_vs_always_on_pct": (base_fuel - fuel) / base_fuel * 100.0,
        "saving_vs_rule_pct": (rule_fuel - fuel) / rule_fuel * 100.0,
        "rule_saving_vs_always_on_pct": (base_fuel - rule_fuel) / base_fuel * 100.0,
        "co2_avoided_t": (base_fuel - fuel) * co2 / 1000.0,
        "polar_ems_unserved_kwh": uns, "rule_unserved_kwh": rule_uns, "always_on_unserved_kwh": base_uns,
        "deferrable_required_kwh": days_n * CFG.deferrable.daily_energy_kwh,
        "deferrable_delivered_kwh": dfr_served, "deferrable_shed_kwh": shed,
        "genset_starts_polar_ems": starts, "genset_starts_rule": rule_starts, "genset_starts_always_on": 1,
        "genset_off_hours_polar_ems": off_hours, "genset_off_hours_rule": rule_off,
        "unplanned_starts": unplanned, "curtailed_kwh": curt,
        "milp_solves": solves, "milp_failures": failures, "fallback_hours": fallback_hours,
        "avg_solve_ms": float(np.mean(solve_ms)) if solve_ms else 0.0,
        "load_mape_pct": float(np.mean(load_ape) * 100.0) if load_ape else None,
        "non_diesel_share_pct": (1.0 - gen_kwh / dem_kwh) * 100.0,
        "series": series,
    }


def combine(months):
    s = lambda k: sum(m[k] for m in months)
    base, rule, pol = s("always_on_fuel_l"), s("rule_fuel_l"), s("polar_ems_fuel_l")
    return {
        "always_on_fuel_l": base, "rule_fuel_l": rule, "polar_ems_fuel_l": pol,
        "saving_vs_always_on_pct": (base - pol) / base * 100.0,
        "saving_vs_rule_pct": (rule - pol) / rule * 100.0,
        "co2_avoided_t": s("co2_avoided_t"),
        "polar_ems_unserved_kwh": s("polar_ems_unserved_kwh"), "rule_unserved_kwh": s("rule_unserved_kwh"),
        "deferrable_required_kwh": s("deferrable_required_kwh"), "deferrable_delivered_kwh": s("deferrable_delivered_kwh"),
        "deferrable_shed_kwh": s("deferrable_shed_kwh"),
        "genset_starts_polar_ems": s("genset_starts_polar_ems"), "genset_starts_rule": s("genset_starts_rule"),
        "milp_solves": s("milp_solves"), "milp_failures": s("milp_failures"), "fallback_hours": s("fallback_hours"),
    }


def main():
    t0 = time.time()
    out = {"meta": {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "weather_modes": list(WEATHER_MODES), "limitations": LIMITATIONS}, "modes": {}}
    for mode in WEATHER_MODES:
        months = [run_benchmark_month(s, 30, mode) for s in ("summer", "polar_night")]
        out["modes"][mode] = {"summer": months[0], "polar_night": months[1], "combined": combine(months)}
        print(f"\n=== weather mode: {mode} ===")
        for m in months:
            print(f"{m['season']:>11}: always-on {m['always_on_fuel_l']:>7,.0f} L | rule {m['rule_fuel_l']:>7,.0f} L | "
                  f"POLAR EMS {m['polar_ems_fuel_l']:>7,.0f} L ({-m['saving_vs_always_on_pct']:.1f}% vs always-on, "
                  f"{-m['saving_vs_rule_pct']:.1f}% vs rule) | unserved {m['polar_ems_unserved_kwh']:.1f} kWh "
                  f"(rule {m['rule_unserved_kwh']:.1f}) | shed {m['deferrable_shed_kwh']:.0f} kWh | "
                  f"starts {m['genset_starts_polar_ems']} (rule {m['genset_starts_rule']}) | "
                  f"load MAPE {m['load_mape_pct']:.1f}% | solves {m['milp_solves']}, {m['avg_solve_ms']:.0f} ms, fallback {m['fallback_hours']} h")
        c = out["modes"][mode]["combined"]
        print(f"   combined: POLAR EMS {c['polar_ems_fuel_l']:,.0f} L = {-c['saving_vs_always_on_pct']:.1f}% vs always-on, "
              f"{-c['saving_vs_rule_pct']:.1f}% vs rule | CO2 avoided {c['co2_avoided_t']:.1f} t | unserved {c['polar_ems_unserved_kwh']:.1f} kWh")
    RESULTS_PATH.parent.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(out))
    print("\nLimitations:\n - " + "\n - ".join(LIMITATIONS))
    print(f"\nSaved {RESULTS_PATH.relative_to(RESULTS_PATH.parent.parent)} in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
