"""Synthetic, climate-calibrated station weather scenarios (NOT observations).

Generates hourly temperature, wind, irradiance and load series with np.random,
using simple physics and rough climatological ranges for Bharati (69.4 S, 76.2 E),
Maitri (70.8 S, 11.7 E) and Himadri (78.9 N, 11.9 E). Nothing here is read from
ERA5, an automatic weather station or any other observation, so it cannot
validate the controller against real weather. Replacing it with a real ERA5 or
station-AWS series is the main open validation task.
"""

import math
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class RealStationWeatherSeries:
    station_name: str
    latitude_deg: float
    longitude_deg: float
    season: str
    num_hours: int
    timestamps: List[str]
    ambient_temp_c: List[float]
    wind_speed_ms: List[float]
    solar_irradiance_w_m2: List[float]
    blizzard_cutout_flags: List[bool]
    rime_icing_flags: List[bool]
    critical_load_kw: List[float]
    deferrable_load_daily_kwh: float

def generate_station_climate_weather(
    station: str = "Bharati",
    season: str = "winter",
    days: int = 30,
    seed: int = 101
) -> RealStationWeatherSeries:
    """Generates a synthetic weather scenario with a station-like climate (not observations)."""
    np.random.seed(seed if season == "winter" else seed + 42)
    num_hours = days * 24
    
    # Station coordinates
    if station.lower() == "maitri":
        lat, lon = -70.76, 11.73
        base_temp_offset = -3.5  # colder inland oasis
    elif station.lower() == "himadri":
        lat, lon = 78.92, 11.93
        base_temp_offset = 2.0   # maritime Arctic
    else: # Bharati (default)
        lat, lon = -69.40, 76.18
        base_temp_offset = 0.0
        
    timestamps = [f"Day {h//24 + 1:02d} {h%24:02d}:00" for h in range(num_hours)]
    ambient_temps: List[float] = []
    wind_speeds: List[float] = []
    irradiances: List[float] = []
    cutouts: List[bool] = []
    icings: List[bool] = []
    critical_loads: List[float] = []
    
    is_summer = (season.lower() == "summer")
    
    # Generate realistic physics-grounded weather features
    for h in range(num_hours):
        day = h // 24
        hour = h % 24
        
        # 1. Solar Irradiance
        if is_summer:
            # 24h daylight in Antarctica summer (Dec-Jan)
            # Declination ~ -23 deg
            declination = -23.0 * (math.pi / 180.0)
            lat_rad = lat * (math.pi / 180.0)
            hour_angle = (hour - 12) * 15.0 * (math.pi / 180.0)
            sin_elev = math.sin(lat_rad) * math.sin(declination) + math.cos(lat_rad) * math.cos(declination) * math.cos(hour_angle)
            elevation_deg = math.degrees(math.asin(max(0.01, sin_elev)))
            
            # GHI model: clear sky with passing low Antarctic stratus clouds
            clear_sky = 950.0 * max(0.0, math.sin(math.radians(elevation_deg))) ** 1.15
            # Stochastic cloud extinction (synoptic fronts every 4-6 days)
            cloud_extinction = 0.82 + 0.18 * math.sin(2 * math.pi * h / (24 * 5.2)) + np.random.normal(0, 0.04)
            cloud_extinction = float(np.clip(cloud_extinction, 0.25, 1.0))
            irr = clear_sky * cloud_extinction
        else:
            # Polar night (June-July): Sun remains strictly below horizon 24/7
            irr = 0.0
            
        # 2. Ambient Temperature
        if is_summer:
            # Coastal Antarctic summer: -10°C to +1°C
            diurnal = 3.2 * math.sin(2 * math.pi * (hour - 10) / 24.0)
            synoptic = 4.0 * math.sin(2 * math.pi * h / (24 * 6.5))
            temp = -6.5 + base_temp_offset + diurnal + synoptic + np.random.normal(0, 1.2)
        else:
            # Deep polar night winter: -38°C to -20°C
            synoptic = 7.5 * math.sin(2 * math.pi * h / (24 * 7.0))
            cold_plunge = -4.0 if (10 <= day <= 14 or 22 <= day <= 26) else 0.0
            temp = -30.0 + base_temp_offset + synoptic + cold_plunge + np.random.normal(0, 1.8)
            
        # 3. Wind Speed & Katabatic Blizzard Dynamics
        # Katabatic winds flow persistently from the ice plateau
        katabatic_base = 8.5 + 3.0 * math.sin(2 * math.pi * h / (24 * 3.8))
        
        # Real Blizzard Storms:
        # In Bharati winter, 2 to 3 major blizzard events occur per month
        blizzard_intensity = 0.0
        if not is_summer:
            # Storm 1: Days 5 to 7 (intense katabatic blizzard)
            if 5 * 24 <= h <= 7 * 24 + 12:
                blizzard_intensity = 19.5 + 4.5 * math.sin(2 * math.pi * (h - 5 * 24) / 36.0)
            # Storm 2: Days 16 to 18 (violent polar storm with peak gusts > 30 m/s)
            elif 16 * 24 <= h <= 18 * 24 + 6:
                blizzard_intensity = 22.0 + 5.0 * math.sin(2 * math.pi * (h - 16 * 24) / 30.0)
            # Storm 3: Days 25 to 27
            elif 25 * 24 <= h <= 27 * 24:
                blizzard_intensity = 17.5 + 4.0 * math.sin(2 * math.pi * (h - 25 * 24) / 24.0)
        else:
            # Summer gales (moderate)
            if 12 * 24 <= h <= 13 * 24 + 12:
                blizzard_intensity = 12.0
                
        wind = katabatic_base + blizzard_intensity + np.random.normal(0, 2.2)
        wind = float(np.clip(wind, 1.0, 36.0))
        
        # Cutout flag: Turbines automatically lock and feather at >= 25.0 m/s
        cutout = (wind >= 25.0)
        # Rime icing: occurs when cold (-32°C to -15°C) with high humidity/moderate wind
        icing = (temp < -24.0 and 6.0 <= wind <= 16.0 and not cutout)
        
        # 4. Critical Science & Life-Support Station Load
        base_station = 54.0 if is_summer else 64.0
        diurnal_activity = 6.0 * math.sin(2 * math.pi * (hour - 8) / 24.0)
        # Extreme cold demands extra trace heating on water pipes
        pipe_trace_heating = max(0.0, (-temp - 20.0) * 0.9)
        load = base_station + diurnal_activity + pipe_trace_heating + np.random.normal(0, 1.8)
        load = float(max(28.0, load))
        
        ambient_temps.append(float(round(temp, 2)))
        wind_speeds.append(float(round(wind, 2)))
        irradiances.append(float(round(irr, 2)))
        cutouts.append(cutout)
        icings.append(icing)
        critical_loads.append(float(round(load, 2)))
        
    return RealStationWeatherSeries(
        station_name=station,
        latitude_deg=lat,
        longitude_deg=lon,
        season=season,
        num_hours=num_hours,
        timestamps=timestamps,
        ambient_temp_c=ambient_temps,
        wind_speed_ms=wind_speeds,
        solar_irradiance_w_m2=irradiances,
        blizzard_cutout_flags=cutouts,
        rime_icing_flags=icings,
        critical_load_kw=critical_loads,
        deferrable_load_daily_kwh=100.0
    )
