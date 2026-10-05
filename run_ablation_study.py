"""Forecast ablation runner. Usage: python run_ablation_study.py [days]

Runs the five-controller ablation (see polar_ems/forecasting/ablation.py for
what each comparison does and does not show) on a summer and a polar-night
series and saves results/ablation_results.json.
"""

import json
import sys
from pathlib import Path

from polar_ems.config import DEFAULT_STATION_CONFIG
from polar_ems.forecasting.ablation import PolarAblationEngine, ALL_CONFIGS
from polar_ems.simulation.synthetic_data import generate_polar_dataset

LABELS = {
    "persistence_rule": "1. Rule controller (no forecast)",
    "persistence_milp": "2. MILP + persistence forecasts",
    "persistence_load_true_weather": "3. MILP + persistence load, true weather",
    "polar_ems_ai": "4. MILP + ML load, true weather",
    "perfect_oracle": "5. MILP + perfect information",
}


def fmt(v):
    return "n/a" if v is None else f"{v}%"


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7
    engine = PolarAblationEngine(DEFAULT_STATION_CONFIG)
    out = {}
    for season in ("summer", "polar_night"):
        ds = generate_polar_dataset(season=season, days=max(days, 8))
        res = engine.run_ablation_study(ds, simulation_days=days)
        out[season] = res
        print("=" * 100)
        print(f"ABLATION: {season.upper()} ({days} days, replan every 6 h, 24 h horizon)")
        print("=" * 100)
        print(f"{'Configuration':<44}{'Fuel (L)':>9}{'Starts':>8}{'Unserved':>10}{'Shed kWh':>10}{'Load MAPE':>11}  Weather input")
        for n in ALL_CONFIGS:
            r = res["ablation_results"][n]
            print(f"{LABELS[n]:<44}{r['fuel_l']:>9}{r['starts']:>8}{r['unserved_kwh']:>10}{r['deferrable_shed_kwh']:>10}{fmt(r['load_mape']):>11}  {r['weather_input']}")
        a = res["attribution"]
        print("-" * 100)
        print(f"Optimizer vs rule controller (2 vs 1):           {a['optimizer_vs_rule_litres']:>8} L")
        print(f"Knowing the weather vs persistence (3 vs 2):     {a['true_weather_vs_persistence_weather_litres']:>8} L   (not ML skill)")
        print(f"ML load model vs persistence load (4 vs 3):      {a['ml_load_vs_persistence_load_litres']:>8} L ({a['ml_load_vs_persistence_load_pct']}%)")
        print(f"Remaining gap to perfect information (4 vs 5):   {a['remaining_gap_to_oracle_litres']:>8} L")
        print("Notes: " + " ".join(res["notes"]))
    Path("results").mkdir(exist_ok=True)
    Path("results/ablation_results.json").write_text(json.dumps(out, indent=2))
    print("\nSaved results/ablation_results.json")


if __name__ == "__main__":
    main()
