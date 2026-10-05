"""Summary statistics of a synthetic station-climate weather scenario.

Usage: python run_station_weather_scenario.py [Bharati|Maitri|Himadri]

The series is generated with np.random (polar_ems/simulation/station_weather.py);
it is NOT an observation or reanalysis record. This script only describes it.
"""

import sys

import numpy as np

from polar_ems.simulation.station_weather import generate_station_climate_weather


def main():
    station = sys.argv[1] if len(sys.argv) > 1 else "Bharati"
    d = generate_station_climate_weather(station=station, season="winter", days=30)
    print(f"Synthetic climate-calibrated scenario: {station} (not observations)")
    print(f"  Hours:                 {d.num_hours}")
    print(f"  Temperature:           {min(d.ambient_temp_c):.1f} to {max(d.ambient_temp_c):.1f} C (mean {np.mean(d.ambient_temp_c):.1f})")
    print(f"  Wind speed:            max {max(d.wind_speed_ms):.1f} m/s, mean {np.mean(d.wind_speed_ms):.1f} m/s")
    print(f"  Hours at/above cut-out:{sum(d.blizzard_cutout_flags):>5}")
    print(f"  Rime-icing risk hours: {sum(d.rime_icing_flags):>5}")
    print(f"  Critical load:         {min(d.critical_load_kw):.1f} to {max(d.critical_load_kw):.1f} kW (mean {np.mean(d.critical_load_kw):.1f})")


if __name__ == "__main__":
    main()
