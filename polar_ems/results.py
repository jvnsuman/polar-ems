"""Read the results written by run_simulation.py (results/benchmark_results.json).

The dashboard and API show only what the simulation produced. If the file is
missing they say so; they never fall back to remembered or deck numbers.
"""

import json
from pathlib import Path
from typing import Any, Dict

RESULTS_PATH = Path(__file__).resolve().parent.parent / "results" / "benchmark_results.json"
CUTOUT_MS = 25.0


class ResultsMissing(RuntimeError):
    pass


def load_results() -> Dict[str, Any]:
    if not RESULTS_PATH.exists():
        raise ResultsMissing("results/benchmark_results.json not found. Run: python run_simulation.py")
    return json.loads(RESULTS_PATH.read_text())


def benchmark_summary() -> Dict[str, Any]:
    res = load_results()
    modes = {}
    for mode, seasons in res["modes"].items():
        modes[mode] = {
            name: {k: v for k, v in block.items() if k != "series"} for name, block in seasons.items()
        }
    return {"meta": res["meta"], "modes": modes}


def week_view(season: str = "polar_night", mode: str = "persistence") -> Dict[str, Any]:
    """A 7-day window of the executed POLAR EMS dispatch. The window is the 7 days of
    the month with the most turbine cut-out hours (ties: highest wind), chosen from the data."""
    res = load_results()
    m = res["modes"][mode][season]
    s = m["series"]
    n_days = m["hours"] // 24
    best, best_key = 0, (-1, -1.0)
    for d in range(0, n_days - 6):
        w = s["wind_speed_ms"][d * 24:(d + 7) * 24]
        key = (sum(1 for x in w if x >= CUTOUT_MS), max(w))
        if key > best_key:
            best, best_key = d, key
    a, b = best * 24, (best + 7) * 24
    pick = lambda k: s[k][a:b]
    hours = b - a
    label_mode = {"true": "true weather given to optimizer (upper bound)",
                  "persistence": "yesterday's weather given to optimizer (naive bound)"}[mode]
    return {
        "season": season, "weather_mode": mode, "weather_mode_note": label_mode,
        "window_start_day": best + 1, "hours": hours,
        "timestamps": [f"Day {best + 1 + h // 24} {h % 24:02d}:00" for h in range(hours)],
        "day_labels": [f"Day {h // 24 + 1}" if h % 24 == 12 else "" for h in range(hours)],
        "genset_kw": pick("genset_kw"), "wind_kw": pick("wind_kw"), "pv_kw": pick("pv_kw"),
        "batt_discharge_kw": pick("batt_discharge_kw"), "batt_charge_kw": pick("batt_charge_kw"),
        "demand_kw": pick("demand_kw"), "soc_polar_ems": pick("soc_polar_ems"),
        "soc_rule_based": pick("soc_rule_based"), "wind_speed_ms": pick("wind_speed_ms"),
        "cutout_threshold": [CUTOUT_MS] * hours,
        "metrics": {
            "diesel_savings_pct": round(-m["saving_vs_always_on_pct"], 1),
            "diesel_liters_str": (f"{m['always_on_fuel_l']:,.0f} L -> {m['polar_ems_fuel_l']:,.0f} L in {m['days']} days "
                                  f"(rule-based: {m['rule_fuel_l']:,.0f} L, {-m['saving_vs_rule_pct']:.1f}%)"),
            "gensets_off_hours": m["genset_off_hours_polar_ems"],
            "gensets_off_sub": f"of {m['hours']} h (rule-based {m['genset_off_hours_rule']} h, always-on 0 h)",
            "renewable_share_pct": round(m["non_diesel_share_pct"], 0),
            "renewable_sub": "of demand not met by diesel (always-on 0%)",
            "unserved_kwh": round(m["polar_ems_unserved_kwh"], 1),
            "unserved_sub": f"after real-time re-balancing; {m['deferrable_shed_kwh']:.0f} kWh deferrable load shed",
        },
    }
