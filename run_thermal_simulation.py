"""Stand-alone combined heat and power snapshot (not part of the dispatch optimizer).

Shows, for three operating points, the station heat demand, the genset waste heat
recovered, and the auxiliary boiler fuel needed when the gensets are off. The
coefficients (UA, heat recovery ratio, boiler efficiency) are assumptions in
polar_ems/simulation/thermal_model.py, not measured station values.
"""

from polar_ems.simulation.thermal_model import PolarThermalEngine, ThermalConfig
import json

def main():
    print("=" * 75)
    print("   POLAR EMS - COMBINED HEAT & POWER (CHP) & AUXILIARY BOILER ENGINE")
    print("=" * 75)
    print("Polar Station Thermal Balance Parameters:")
    print("  • Habitat Comfort Setpoint: +18.0 °C")
    print("  • Station Heat Loss (UA):   1.25 kW/°C (well-insulated containerized polar module)")
    print("  • Snow-Melt Thermal Draw:   8.0 kW_th (continuous potable water production)")
    print("  • CHP Heat Recovery Ratio:  1.35 kW_th / kW_elec (jacket water + exhaust recovery)")
    print("  • Auxiliary Boiler Effic.:  84.0% (polar-grade oil-fired burner, 0.118 L/kWh_th)")
    print("-" * 75)

    engine = PolarThermalEngine()

    # Compare 3 distinct operational regimes:
    # Scenario A: Moderate Summer (-8°C, Genset at 45 kW)
    res_a = engine.step(genset_kw=45.0, ambient_temp_c=-8.0)
    
    # Scenario B: Deep Winter Storm (-35°C, Genset at 60 kW)
    res_b = engine.step(genset_kw=60.0, ambient_temp_c=-35.0)

    # Scenario C: 100% Renewable Wind Mode in Winter (-30°C, Genset OFF = 0 kW)
    res_c = engine.step(genset_kw=0.0, ambient_temp_c=-30.0)

    print("\n[OPERATIONAL THERMAL REGIME SNAPSHOTS]")
    print(f"\n1. Austral Summer (-8°C, Genset @ 45 kW):")
    print(f"   • Station Thermal Demand:     {res_a['demand_kw_th']} kW_th")
    print(f"   • Genset Heat Recovered:      {res_a['recovered_kw_th']} kW_th")
    print(f"   • Heat Status:                SURPLUS ({res_a['surplus_kw_th']} kW_th excess dumped to radiator)")
    print(f"   • Auxiliary Boiler Required:  NO (Boiler Fuel: 0.0 L/h)")

    print(f"\n2. Austral Winter with Genset (-35°C, Genset @ 60 kW):")
    print(f"   • Station Thermal Demand:     {res_b['demand_kw_th']} kW_th")
    print(f"   • Genset Heat Recovered:      {res_b['recovered_kw_th']} kW_th")
    print(f"   • Heat Status:                SURPLUS ({res_b['surplus_kw_th']} kW_th excess dumped)")
    print(f"   • Auxiliary Boiler Required:  NO (Boiler Fuel: 0.0 L/h)")

    print(f"\n3. Austral Winter 100% Renewable Mode (-30°C, Genset OFF @ 0 kW):")
    print(f"   • Station Thermal Demand:     {res_c['demand_kw_th']} kW_th")
    print(f"   • Genset Heat Recovered:      0.0 kW_th (Genset OFF)")
    print(f"   • Thermal Deficit:            {res_c['deficit_kw_th']} kW_th")
    print(f"   • Auxiliary Boiler Required:  YES (Boiler Fuel: {res_c['boiler_fuel_l']} L/h)")
    from polar_ems.config import DEFAULT_STATION_CONFIG
    from polar_ems.simulation.microgrid import PolarMicrogridSimulator
    gen_fuel = PolarMicrogridSimulator(DEFAULT_STATION_CONFIG).calculate_genset_fuel(60.0, True, genset_idx=0)
    net = gen_fuel - res_c['boiler_fuel_l']
    print(f"   • Net fuel, genset off vs on: Genset at 60 kW burns {gen_fuel:.1f} L/h; the boiler burns {res_c['boiler_fuel_l']} L/h instead.")
    print(f"                                 Net saving {net:.1f} L/h ({net / gen_fuel * 100:.0f}% of the genset's fuel), if renewables replace all 60 kW of electricity.")
    print("   Assumptions: heat recovery 1.35 kW_th per kW_el and 84% boiler efficiency; heating is not inside the dispatch optimizer.")
    print("=" * 75)

if __name__ == "__main__":
    main()
