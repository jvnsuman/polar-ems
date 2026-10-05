"""Forecast ablation: what do the forecasts and the optimizer each contribute?

Five controllers run on identical weather and load, replanned every 6 h over a
24 h horizon:

1. persistence_rule              Rule-based controller (it uses no forecast).
2. persistence_milp              MILP fed 24 h-persistence forecasts of load, wind, PV.
3. persistence_load_true_weather MILP fed persistence LOAD but TRUE wind/PV/temperature.
4. polar_ems_ai                  MILP fed the ML (gradient boosting) LOAD forecast and
                                 TRUE wind/PV/temperature (what run_simulation.py does).
5. perfect_oracle                MILP fed the true load, wind, PV, temperature.

Reading the results correctly:
- 4 vs 3 isolates the ML load model (weather held identical).
- 3 vs 2 is the value of knowing the weather. It says nothing about ML skill:
  there is no weather forecast model in this repository.
- 4 vs 5 is the fuel cost of the remaining load-forecast error.
- 2 vs 1 is the optimizer's contribution over the rule controller.

Every plan is executed against actual load, wind and PV by
polar_ems/simulation/executor.py, so forecast error costs fuel or unserved
energy; `unserved_kwh` is a realized shortfall after that re-balancing. Fuel
counts both gensets and any unplanned genset start. The ML model trains on the
first 96 h of the series it is then scored on.
"""

import numpy as np
from typing import Dict, Any
from ..config import StationConfig, DEFAULT_STATION_CONFIG
from ..simulation.microgrid import PolarMicrogridSimulator
from ..simulation.synthetic_data import PolarDataset
from ..forecasting.forecaster import PolarForecaster
from ..optimizer.milp_solver import PolarMILPOptimizer
from ..safety.fallback_controller import RuleBasedFallbackController
from ..simulation.executor import execute_hour

MILP_CONFIGS = ["persistence_milp", "persistence_load_true_weather", "polar_ems_ai", "perfect_oracle"]
ALL_CONFIGS = ["persistence_rule"] + MILP_CONFIGS
WEATHER_INPUT = {
    "persistence_rule": "actual (rule controller sees current weather)",
    "persistence_milp": "24 h persistence forecast",
    "persistence_load_true_weather": "true (no forecast error)",
    "polar_ems_ai": "true (no forecast error)",
    "perfect_oracle": "true (no forecast error)",
}
LOAD_INPUT = {
    "persistence_rule": "none",
    "persistence_milp": "24 h persistence",
    "persistence_load_true_weather": "24 h persistence",
    "polar_ems_ai": "gradient boosting (ML)",
    "perfect_oracle": "true load",
}


class PolarAblationEngine:
    def __init__(self, config: StationConfig = DEFAULT_STATION_CONFIG):
        self.cfg = config
        self.sim = PolarMicrogridSimulator(config)
        self.optimizer = PolarMILPOptimizer(config)
        self.rule_ctrl = RuleBasedFallbackController(config)
        self.forecaster = PolarForecaster(config)

    def run_ablation_study(self, dataset: PolarDataset, simulation_days: int = 14) -> Dict[str, Any]:
        num_hours = min(len(dataset.critical_load_kw), simulation_days * 24)
        stride = 6

        train_h = min(96, num_hours // 2)
        self.forecaster.train_load_forecaster(
            hours=list(range(train_h)),
            temps=dataset.ambient_temp_c[:train_h],
            loads=dataset.critical_load_kw[:train_h],
        )

        results = {n: {"fuel_l": 0.0, "unserved_kwh": 0.0, "deferrable_shed_kwh": 0.0, "starts": 0} for n in ALL_CONFIGS}
        soc = {n: 0.65 for n in ALL_CONFIGS}
        last_state = {n: [True, False] for n in ALL_CONFIGS}
        run_hours = {n: [4, 0] for n in ALL_CONFIGS}
        solver_failures = {n: 0 for n in MILP_CONFIGS}
        p_load_err, ml_load_err, p_wind_err = [], [], []
        rule_on = True

        for start_h in range(0, num_hours - 24, stride):
            H = 24
            sl = slice(start_h, start_h + H)
            a_load = dataset.critical_load_kw[sl]
            a_wind = dataset.raw_wind_kw[sl]
            a_pv = dataset.raw_pv_kw[sl]
            a_temp = dataset.ambient_temp_c[sl]
            a_wspd = dataset.wind_speed_ms[sl]

            hist = [max(0, start_h + i - 24) for i in range(H)]
            p_load = [dataset.critical_load_kw[j] for j in hist]
            p_wind = [dataset.raw_wind_kw[j] for j in hist]
            p_pv = [dataset.raw_pv_kw[j] for j in hist]
            p_wspd = [dataset.wind_speed_ms[j] for j in hist]

            ml = self.forecaster.forecast_horizon(
                current_hour=start_h, horizon_hours=H,
                past_loads=dataset.critical_load_kw[max(0, start_h - 24):start_h],
                forecast_temps=a_temp, forecast_wind_speeds=a_wspd,
                forecast_irradiances=dataset.solar_irradiance_w_m2[sl],
            )
            for i in range(H):
                if a_load[i] > 0:
                    p_load_err.append(abs(p_load[i] - a_load[i]) / a_load[i])
                    ml_load_err.append(abs(ml["forecast_load_kw"][i] - a_load[i]) / a_load[i])
                p_wind_err.append(abs(p_wind[i] - a_wind[i]) / 100.0)

            inputs = {
                "persistence_milp": (p_load, p_pv, p_wind, p_wspd),
                "persistence_load_true_weather": (p_load, a_pv, a_wind, a_wspd),
                "polar_ems_ai": (ml["forecast_load_kw"], ml["forecast_pv_kw"], ml["forecast_wind_kw"], a_wspd),
                "perfect_oracle": (a_load, a_pv, a_wind, a_wspd),
            }
            blizzard = bool(dataset.blizzard_flags[start_h]) if hasattr(dataset, "blizzard_flags") else False
            plans = {}
            for n, (fl, fpv, fw, fws) in inputs.items():
                plans[n] = self.optimizer.optimize_horizon(
                    horizon_hours=H, initial_soc=soc[n],
                    initial_genset_states=list(last_state[n]), initial_run_hours=list(run_hours[n]),
                    forecast_loads_kw=fl, forecast_pv_kw=fpv, forecast_wind_kw=fw,
                    forecast_wind_speeds=fws, ambient_temps_c=a_temp, blizzard_override=blizzard,
                )

            for s in range(stride):
                h = start_h + s
                t_amb = dataset.ambient_temp_c[h]
                eff_kwh, c_eff, d_eff = self.sim.get_effective_battery_capacity(t_amb)

                r = self.rule_ctrl.dispatch_step(
                    critical_load_kw=dataset.critical_load_kw[h], deferrable_load_kw=4.17,
                    pv_kw=dataset.raw_pv_kw[h], wind_kw=dataset.raw_wind_kw[h],
                    wind_speed_ms=dataset.wind_speed_ms[h], current_soc=soc["persistence_rule"],
                    ambient_temp_c=t_amb,
                )
                results["persistence_rule"]["fuel_l"] += r["fuel_l"]
                results["persistence_rule"]["unserved_kwh"] += r["unserved_kw"]
                g_on = not r["diesel_off"]
                if g_on and not rule_on:
                    results["persistence_rule"]["starts"] += 1
                rule_on = g_on
                d = (r["batt_charge_kw"] * c_eff - r["batt_discharge_kw"] / d_eff) / eff_kwh
                soc["persistence_rule"] = float(np.clip(soc["persistence_rule"] + d, 0.20, 0.95))

                wind_act = 0.0 if dataset.wind_speed_ms[h] >= self.cfg.wind.cut_out_speed_ms else dataset.raw_wind_kw[h]
                for n in MILP_CONFIGS:
                    p = plans[n]
                    if p.success:
                        plan_g = [p.genset1_kw[s], p.genset2_kw[s]]
                        plan_on = [p.genset1_state[s], p.genset2_state[s]]
                        plan_chg, plan_dis, plan_def = p.batt_charge_kw[s], p.batt_discharge_kw[s], p.deferrable_kw[s]
                    else:
                        solver_failures[n] += 1
                        plan_g, plan_on, plan_chg, plan_dis, plan_def = [0.0, 0.0], [False, False], 0.0, 0.0, 4.17
                    x = execute_hour(
                        self.sim, planned_g_kw=plan_g, planned_g_on=plan_on, planned_chg_kw=plan_chg,
                        planned_dis_kw=plan_dis, planned_def_kw=plan_def,
                        critical_kw=dataset.critical_load_kw[h], wind_kw=wind_act,
                        pv_kw=dataset.raw_pv_kw[h], soc=soc[n], ambient_temp_c=t_amb,
                        prev_g_on=last_state[n],
                    )
                    results[n]["fuel_l"] += x.fuel_l
                    results[n]["unserved_kwh"] += x.unserved_kw
                    results[n]["deferrable_shed_kwh"] += x.deferrable_shed_kw
                    results[n]["starts"] += sum(x.started)
                    last_state[n] = list(x.g_on)
                    run_hours[n] = [run_hours[n][i] + 1 if x.g_on[i] else 0 for i in (0, 1)]
                    soc[n] = x.soc

        p_mape = float(np.mean(p_load_err) * 100.0) if p_load_err else None
        ml_mape = float(np.mean(ml_load_err) * 100.0) if ml_load_err else None
        p_nmae = float(np.mean(p_wind_err) * 100.0) if p_wind_err else None

        for n in ALL_CONFIGS:
            results[n]["fuel_l"] = round(results[n]["fuel_l"], 1)
            results[n]["unserved_kwh"] = round(results[n]["unserved_kwh"], 1)
            results[n]["deferrable_shed_kwh"] = round(results[n]["deferrable_shed_kwh"], 1)
            results[n]["weather_input"] = WEATHER_INPUT[n]
            results[n]["load_input"] = LOAD_INPUT[n]
            results[n]["load_mape"] = {
                "persistence_milp": p_mape, "persistence_load_true_weather": p_mape,
                "polar_ems_ai": ml_mape, "perfect_oracle": 0.0, "persistence_rule": None,
            }[n]
            results[n]["wind_nmae"] = p_nmae if n == "persistence_milp" else (None if n == "persistence_rule" else 0.0)
            for k in ("load_mape", "wind_nmae"):
                if results[n][k] is not None:
                    results[n][k] = round(results[n][k], 2)
            if n in solver_failures:
                results[n]["solver_failures"] = solver_failures[n]

        f = {n: results[n]["fuel_l"] for n in ALL_CONFIGS}
        ml_effect = f["persistence_load_true_weather"] - f["polar_ems_ai"]
        return {
            "simulation_days": simulation_days,
            "season": dataset.season,
            "ablation_results": results,
            "attribution": {
                "optimizer_vs_rule_litres": round(f["persistence_rule"] - f["persistence_milp"], 1),
                "true_weather_vs_persistence_weather_litres": round(f["persistence_milp"] - f["persistence_load_true_weather"], 1),
                "ml_load_vs_persistence_load_litres": round(ml_effect, 1),
                "ml_load_vs_persistence_load_pct": round(ml_effect / max(1.0, f["persistence_load_true_weather"]) * 100.0, 2),
                "remaining_gap_to_oracle_litres": round(f["polar_ems_ai"] - f["perfect_oracle"], 1),
            },
            # Kept for dashboard compatibility; this is the isolated ML-load effect only.
            "ai_attribution": {
                "fuel_saved_litres": round(ml_effect, 1),
                "fuel_saved_pct": round(ml_effect / max(1.0, f["persistence_load_true_weather"]) * 100.0, 2),
                "mape_improvement_pct_pts": round((p_mape - ml_mape), 2) if p_mape is not None and ml_mape is not None else None,
                "wind_nmae_improvement_pct_pts": 0.0,
            },
            "notes": [
                "No weather forecast model exists in this repository; configs 3-5 receive true weather.",
                "Plans are executed against actual conditions by a simple re-balancing policy (executor.py); it is not an optimum.",
                "Single synthetic series per season; no confidence intervals.",
            ],
        }
