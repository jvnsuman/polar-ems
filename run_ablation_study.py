"""Command-Line Runner for AI ML vs Persistence Ablation Study.

Directly addresses SIH Judge Critique:
"Thin justification for why AI specifically helps versus simpler rules.
Need an ablation study to isolate AI's contribution: AI vs Rule-based vs Persistence."
"""

import sys
import json
from polar_ems.config import DEFAULT_STATION_CONFIG
from polar_ems.simulation.synthetic_data import generate_polar_dataset
from polar_ems.forecasting.ablation import PolarAblationEngine

def main():
    days = 7
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            pass
            
    print("=" * 75)
    print(f"   POLAR EMS - AI ML vs PERSISTENCE ABLATION STUDY ({days} DAYS)")
    print("=" * 75)
    print("Evaluating 4 controlled dispatch modes under identical weather & load realizations:")
    print("  1. Baseline Heuristic: Persistence forecast + Rule-based controller")
    print("  2. Persistence + MILP: Persistence forecast + SciPy HiGHS MILP optimizer")
    print("  3. POLAR EMS (AI ML):  HistGradientBoosting ML + SciPy HiGHS MILP optimizer")
    print("  4. Perfect Oracle:     Ground truth knowledge + SciPy HiGHS MILP optimizer")
    print("-" * 75)

    engine = PolarAblationEngine(DEFAULT_STATION_CONFIG)
    ds = generate_polar_dataset(season="summer", days=days)
    
    res = engine.run_ablation_study(ds, simulation_days=days)
    
    print("\n[EMPIRICAL ABLATION RESULTS]")
    print(f"{'Configuration':<26} | {'Fuel (L)':<10} | {'Starts':<8} | {'Load MAPE':<10} | {'Wind NMAE':<10} | {'Unserved'}")
    print("-" * 78)
    
    r = res["ablation_results"]
    print(f"{'1. Persistence + Rule':<26} | {r['persistence_rule']['fuel_l']:<10} | {r['persistence_rule']['starts']:<8} | {r['persistence_rule']['load_mape']:<9}% | {r['persistence_rule']['wind_nmae']:<9}% | {r['persistence_rule']['unserved_kwh']} kWh")
    print(f"{'2. Persistence + MILP':<26} | {r['persistence_milp']['fuel_l']:<10} | {r['persistence_milp']['starts']:<8} | {r['persistence_milp']['load_mape']:<9}% | {r['persistence_milp']['wind_nmae']:<9}% | {r['persistence_milp']['unserved_kwh']} kWh")
    print(f"{'3. POLAR EMS (AI ML)':<26} | {r['polar_ems_ai']['fuel_l']:<10} | {r['polar_ems_ai']['starts']:<8} | {r['polar_ems_ai']['load_mape']:<9}% | {r['polar_ems_ai']['wind_nmae']:<9}% | {r['polar_ems_ai']['unserved_kwh']} kWh")
    print(f"{'4. Perfect Oracle Bound':<26} | {r['perfect_oracle']['fuel_l']:<10} | {r['perfect_oracle']['starts']:<8} | {r['perfect_oracle']['load_mape']:<9}% | {r['perfect_oracle']['wind_nmae']:<9}% | {r['perfect_oracle']['unserved_kwh']} kWh")
    print("-" * 78)
    
    ai = res["ai_attribution"]
    print(f"\nAI FORECAST ATTRIBUTION (ML vs Naive Persistence with identical MILP optimizer):")
    print(f"  • Direct Fuel Saved by AI Forecast: {ai['fuel_saved_litres']} Litres in {days} days")
    print(f"  • Percentage Fuel Reduction by AI:  {ai['fuel_saved_pct']}%")
    print(f"  • Load MAPE Accuracy Improvement:    {ai['mape_improvement_pct_pts']} percentage points")
    print(f"  • Wind NMAE Accuracy Improvement:    {ai['wind_nmae_improvement_pct_pts']} percentage points")
    print("=" * 75)

if __name__ == "__main__":
    main()
