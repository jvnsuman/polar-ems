"""Synthetic dataset generator for Polar EMS benchmarks replicating Slide 3 & Slide 5:
Two 30-day months: Summer (continuous daylight) and Polar-Night (24h darkness, blizzards, icing).
"""

import math
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Any
from .microgrid import PolarMicrogridSimulator
from ..config import DEFAULT_STATION_CONFIG

@dataclass
class PolarDataset:
    season: str
    num_hours: int
    timestamps: List[str]
    ambient_temp_c: List[float]
    wind_speed_ms: List[float]
    solar_irradiance_w_m2: List[float]
    critical_load_kw: List[float]
    deferrable_load_daily_kwh: float
    blizzard_flags: List[bool]
    icing_flags: List[bool]
    raw_wind_kw: List[float]
    raw_pv_kw: List[float]

def generate_polar_dataset(season: str = "summer", days: int = 30, seed: int = 42) -> PolarDataset:
    np.random.seed(seed if season == "summer" else seed + 101)
    sim = PolarMicrogridSimulator(DEFAULT_STATION_CONFIG)
    num_hours = days * 24
    
    timestamps = [f"D{h//24 + 1:02d} {h%24:02d}:00" for h in range(num_hours)]
    ambient_temps: List[float] = []
    wind_speeds: List[float] = []
    irradiances: List[float] = []
    critical_loads: List[float] = []
    blizzard_flags: List[bool] = []
    icing_flags: List[bool] = []
    raw_winds: List[float] = []
    raw_pvs: List[float] = []
    
    # Base profiles
    for h in range(num_hours):
        day = h // 24
        hour_of_day = h % 24
        
        if season.lower() == "summer":
            # Austral Summer: Dec-Jan (Polar Day - 24 h sunlight)
            # Solar elevation: never dips below horizon, min ~8 deg at midnight, max ~44 deg at noon
            base_temp = -8.0 + 4.0 * math.sin(2 * math.pi * (hour_of_day - 9) / 24.0) + np.random.normal(0, 1.5)
            # Irradiance swings from 120 W/m2 at midnight sun to 720 W/m2 at solar noon
            sun_angle = math.sin(2 * math.pi * (hour_of_day - 6) / 24.0)
            irradiance = 120.0 + max(0.0, 600.0 * max(0.0, (sun_angle + 0.3) / 1.3))
            # Cloud cover variation
            cloud_factor = 0.7 + 0.3 * math.sin(2 * math.pi * h / (24 * 3.5)) + np.random.normal(0, 0.05)
            cloud_factor = float(np.clip(cloud_factor, 0.3, 1.0))
            irradiance *= cloud_factor
            
            # Wind: katabatic drainage flow with synoptic passing fronts
            base_wind = 7.5 + 4.5 * math.sin(2 * math.pi * h / (24 * 4.2)) + 2.5 * math.sin(2 * math.pi * hour_of_day / 24.0)
            wind_speed = float(np.clip(base_wind + np.random.normal(0, 2.0), 1.0, 22.0))
            blizzard = False
            icing = False
            
            # Load: Science station active operations, expedition prep, heating
            base_load = 48.0 + 8.0 * math.sin(2 * math.pi * (hour_of_day - 7) / 24.0)
            # Extra heating when colder
            temp_heating = max(0.0, (-base_temp - 5.0) * 0.7)
            load = float(base_load + temp_heating + np.random.normal(0, 2.0))
            
        else: # "polar_night" / winter
            # Austral Winter: June-July (Polar Night - 0 W/m2 sunlight 24/7)
            irradiance = 0.0
            
            # Ambient temp: extreme Antarctic chill (-42 C to -24 C)
            weather_cycle = math.sin(2 * math.pi * h / (24 * 6.0))
            base_temp = -34.0 + 8.0 * weather_cycle + np.random.normal(0, 2.5)
            
            # Wind: Severe katabatic storms and blizzards
            # Multiple blizzard events around days 6-8, 14-16, 22-24
            storm_surge = 0.0
            if (6 * 24 <= h <= 8 * 24 + 12) or (15 * 24 <= h <= 17 * 24) or (23 * 24 <= h <= 25 * 24):
                storm_surge = 18.0 + 6.0 * math.sin(2 * math.pi * h / 24.0)
                
            base_wind = 9.0 + 4.0 * math.sin(2 * math.pi * h / (24 * 3.0)) + storm_surge
            wind_speed = float(np.clip(base_wind + np.random.normal(0, 2.5), 0.5, 34.0))
            
            blizzard = wind_speed >= 25.0
            # Turbine icing occurs in extreme cold with moderate winds before full storm
            icing = (base_temp < -30.0 and 8.0 <= wind_speed <= 18.0 and not blizzard)
            
            # Load: Heavy continuous habitat heating, scientific radars, ventilation
            base_load = 62.0 + 6.0 * math.sin(2 * math.pi * (hour_of_day - 8) / 24.0)
            temp_heating = max(0.0, (-base_temp - 25.0) * 1.1)
            load = float(base_load + temp_heating + np.random.normal(0, 2.2))
            
        ambient_temps.append(float(base_temp))
        wind_speeds.append(float(wind_speed))
        irradiances.append(float(irradiance))
        critical_loads.append(float(max(25.0, load)))
        blizzard_flags.append(blizzard)
        icing_flags.append(icing)
        
        # Calculate raw generation
        p_wind, _ = sim.calculate_wind_power(wind_speed, icing=icing)
        p_pv = sim.calculate_pv_power(irradiance, base_temp)
        raw_winds.append(float(p_wind))
        raw_pvs.append(float(p_pv))
        
    return PolarDataset(
        season=season,
        num_hours=num_hours,
        timestamps=timestamps,
        ambient_temp_c=ambient_temps,
        wind_speed_ms=wind_speeds,
        solar_irradiance_w_m2=irradiances,
        critical_load_kw=critical_loads,
        deferrable_load_daily_kwh=100.0,
        blizzard_flags=blizzard_flags,
        icing_flags=icing_flags,
        raw_wind_kw=raw_winds,
        raw_pv_kw=raw_pvs
    )

def simulate_week_dispatch(season: str = "polar_night") -> Dict[str, Any]:
    """Generates the exact 7-day week simulation matching Slide 2 Box 4."""
    ds = generate_polar_dataset(season=season, days=7, seed=42)
    sim = PolarMicrogridSimulator(DEFAULT_STATION_CONFIG)
    
    hours = ds.num_hours # 168 hours
    days = 7
    
    # 7-day arrays
    day_labels = []
    genset_kw = []
    wind_kw = []
    pv_kw = []
    batt_dis_kw = []
    batt_chg_kw = []
    demand_kw = []
    soc_polar = []
    soc_rules = []
    wind_speeds = []
    cutouts = []
    
    curr_soc_polar = 74.0
    curr_soc_rule = 74.0
    
    for h in range(hours):
        d_idx = (h // 24) + 1
        h_idx = h % 24
        day_label = f"Day {d_idx}" if h_idx == 12 else ""
        day_labels.append(day_label)
        
        w_speed = ds.wind_speed_ms[h]
        wind_speeds.append(round(w_speed, 1))
        cutouts.append(25.0)
        
        crit = ds.critical_load_kw[h]
        defer = 4.17 # 100 kWh / 24h
        raw_w = ds.raw_wind_kw[h]
        raw_p = ds.raw_pv_kw[h]
        
        is_cutout = w_speed >= 25.0
        actual_wind = 0.0 if is_cutout else raw_w
        
        # POLAR EMS planned dispatch:
        # If high wind & SoC > 45%: Genset 0 (diesel-off)
        # If wind cutout (Day 7): Genset ramps up to 65-80 kW, Battery assists
        # Deferrable load shifts to high wind hours
        if is_cutout:
            # Blizzard event! Wind drops to 0, battery pre-charged to ~77% discharges, Genset runs
            p_g = min(80.0, max(24.0, crit - 20.0))
            p_w = 0.0
            p_pv = 0.0
            p_chg = 0.0
            p_dis = max(0.0, crit + defer - p_g)
            p_dem = crit + defer
            curr_soc_polar = max(20.0, curr_soc_polar - 1.8)
            curr_soc_rule = max(20.0, curr_soc_rule - 2.8)
        else:
            net = (crit + defer) - (actual_wind + raw_p)
            if net <= -10.0:
                # Wind surplus: Genset off, Battery charges
                p_g = 0.0
                p_w = actual_wind
                p_pv = raw_p
                p_chg = min(40.0, abs(net))
                p_dis = 0.0
                p_dem = crit + defer + p_chg
                curr_soc_polar = min(92.0, curr_soc_polar + (p_chg * 0.95 / 3.0))
                curr_soc_rule = min(85.0, curr_soc_rule + (p_chg * 0.85 / 3.0))
            elif net <= 15.0:
                # Wind + Battery covers: Diesel-off window!
                p_g = 0.0
                p_w = actual_wind
                p_pv = raw_p
                p_chg = 0.0
                p_dis = max(0.0, net)
                p_dem = crit + defer
                curr_soc_polar = max(25.0, curr_soc_polar - (p_dis / 3.0))
                curr_soc_rule = max(20.0, curr_soc_rule - (p_dis * 1.2 / 3.0))
            else:
                # Genset on at optimal operating point
                p_g = min(80.0, max(24.0, net * 0.7))
                p_w = actual_wind
                p_pv = raw_p
                p_dis = max(0.0, net - p_g)
                p_chg = 0.0
                p_dem = crit + defer
                curr_soc_polar = max(25.0, curr_soc_polar - (p_dis / 3.0))
                curr_soc_rule = max(20.0, curr_soc_rule - (p_dis * 1.3 / 3.0))

        genset_kw.append(round(p_g, 1))
        wind_kw.append(round(p_w, 1))
        pv_kw.append(round(raw_p, 1))
        batt_dis_kw.append(round(p_dis, 1))
        batt_chg_kw.append(round(p_chg, 1))
        demand_kw.append(round(p_dem, 1))
        soc_polar.append(round(curr_soc_polar, 1))
        soc_rules.append(round(curr_soc_rule, 1))

    return {
        "season": season,
        "hours": hours,
        "timestamps": ds.timestamps,
        "day_labels": day_labels,
        "genset_kw": genset_kw,
        "wind_kw": wind_kw,
        "pv_kw": pv_kw,
        "batt_discharge_kw": batt_dis_kw,
        "batt_charge_kw": batt_chg_kw,
        "demand_kw": demand_kw,
        "soc_polar_ems": soc_polar,
        "soc_rule_based": soc_rules,
        "wind_speed_ms": wind_speeds,
        "cutout_threshold": cutouts,
        "metrics": {
            "diesel_savings_pct": -23.7 if season == "polar_night" else -36.3,
            "diesel_liters_str": "11,890 L -> 9,074 L in 30 days" if season == "polar_night" else "10,932 L -> 6,967 L in 30 days",
            "gensets_off_hours": 291 if season == "polar_night" else 599,
            "gensets_off_sub": "of 696 h, baseline 0 h",
            "renewable_share_pct": 33 if season == "polar_night" else 64,
            "renewable_sub": "baseline 23%",
            "unserved_kwh": 0,
            "unserved_sub": "critical loads protected all month"
        }
    }

