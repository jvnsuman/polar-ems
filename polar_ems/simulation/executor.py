"""Real-time execution of a planned hour against actual conditions.

A plan is built from forecasts. Executing it as written would hide every
forecast error: the plan balances on paper whatever the real load, wind and PV
do. This module takes one planned hour and re-balances it against what actually
happened, so forecast error costs fuel or unserved energy.

Policy (simple and transparent, not an optimum):
- Keep the plan's genset on/off commitment; clip battery power to physical limits.
- Surplus: trim running gensets toward minimum load, then battery discharge, then
  charge the battery, then curtail wind/PV.
- Deficit: battery discharge first, then raise running gensets, then start an idle
  genset (counted as a start), then shed deferrable load, and only then unserved.

Not modelled: genset ramp rates, minimum run time for unplanned starts, the
daily 100 kWh deferrable-energy requirement (shed energy is reported instead),
and protection-relay or PLC behaviour.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class ExecutedHour:
    g_kw: List[float]
    g_on: List[bool]
    started: List[bool]
    chg_kw: float
    dis_kw: float
    deferrable_kw: float
    deferrable_shed_kw: float
    curtailed_kw: float
    unserved_kw: float
    fuel_l: float
    soc: float
    unplanned_start: bool


def execute_hour(sim, *, planned_g_kw, planned_g_on, planned_chg_kw, planned_dis_kw,
                 planned_def_kw, critical_kw, wind_kw, pv_kw, soc, ambient_temp_c,
                 prev_g_on) -> ExecutedHour:
    bat, gen = sim.battery_cfg, sim.genset_cfg
    eff_kwh, c_eff, d_eff = sim.get_effective_battery_capacity(ambient_temp_c)
    max_dis = max(0.0, min(bat.max_discharge_kw, (soc - bat.min_soc) * eff_kwh * d_eff))
    max_chg = max(0.0, min(bat.max_charge_kw, (bat.max_soc - soc) * eff_kwh / c_eff))

    on = [bool(planned_g_on[0]), bool(planned_g_on[1])]
    g = [max(gen[i].min_kw, min(gen[i].rated_kw, planned_g_kw[i])) if on[i] else 0.0 for i in (0, 1)]
    chg = min(max(0.0, planned_chg_kw), max_chg)
    dis = min(max(0.0, planned_dis_kw), max_dis)
    dfr = max(0.0, planned_def_kw)
    dfr_planned = dfr
    ren = max(0.0, wind_kw) + max(0.0, pv_kw)
    curt = 0.0
    uns = 0.0
    planned_on = list(on)

    diff = sum(g) + ren + dis - (critical_kw + dfr + chg)
    if diff >= 0.0:
        for i in (1, 0):
            if on[i]:
                r = min(diff, max(0.0, g[i] - gen[i].min_kw))
                g[i] -= r
                diff -= r
        r = min(diff, dis)
        dis -= r
        diff -= r
        add = min(diff, max_chg - chg)
        chg += add
        diff -= add
        curt = diff
    else:
        need = -diff
        add = min(need, max_dis - dis)
        dis += add
        need -= add
        for i in (0, 1):
            if on[i] and need > 0.0:
                add = min(need, gen[i].rated_kw - g[i])
                g[i] += add
                need -= add
        for i in (0, 1):
            if not on[i] and need > 1e-9:
                out = min(gen[i].rated_kw, max(gen[i].min_kw, need))
                g[i], on[i] = out, True
                need -= out
                if need < 0.0:
                    curt += -need
                    need = 0.0
        shed = min(need, dfr)
        dfr -= shed
        need -= shed
        uns = need

    fuel = sum(sim.calculate_genset_fuel(g[i], on[i], genset_idx=i) for i in (0, 1))
    d_soc = (chg * c_eff - dis / d_eff) / eff_kwh
    new_soc = min(bat.max_soc, max(bat.min_soc, soc + d_soc))
    return ExecutedHour(
        g_kw=g, g_on=on,
        started=[on[i] and not prev_g_on[i] for i in (0, 1)],
        chg_kw=chg, dis_kw=dis, deferrable_kw=dfr,
        deferrable_shed_kw=max(0.0, dfr_planned - dfr),
        curtailed_kw=curt, unserved_kw=uns, fuel_l=fuel, soc=new_soc,
        unplanned_start=any(on[i] and not planned_on[i] for i in (0, 1)),
    )
