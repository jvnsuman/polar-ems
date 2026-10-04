"""Physics model of the Polar Microgrid components: Diesel Gensets, Battery with cold derating,
Wind Turbine with blizzard cut-out and icing, Solar PV with polar albedo, and Deferrable loads.
"""

import math
import numpy as np
from typing import Dict, Tuple, Optional
from ..config import StationConfig, DEFAULT_STATION_CONFIG

class PolarMicrogridSimulator:
    def __init__(self, config: StationConfig = DEFAULT_STATION_CONFIG):
        self.cfg = config
        self.genset_cfg = config.gensets
        self.battery_cfg = config.battery
        self.wind_cfg = config.wind
        self.pv_cfg = config.solar
        self.deferrable_cfg = config.deferrable
        
        # State variables
        self.current_soc = self.battery_cfg.initial_soc
        self.genset_run_hours = [0, 0] # Consecutive hours running
        self.genset_state = [False, False] # True if ON

    def get_effective_battery_capacity(self, ambient_temp_c: float) -> Tuple[float, float, float]:
        """Calculates effective capacity and charge/discharge efficiencies derated by polar cold."""
        loss_ratio = max(0.0, (self.battery_cfg.cold_derate_ref_temp_c - ambient_temp_c) * self.battery_cfg.cold_capacity_loss_per_c)
        effective_capacity_ratio = max(self.battery_cfg.cold_min_effective_ratio, 1.0 - loss_ratio)
        effective_kwh = self.battery_cfg.nominal_capacity_kwh * effective_capacity_ratio
        
        # Internal resistance increase lowers round-trip efficiency in deep freeze
        eff_loss = max(0.0, (self.battery_cfg.cold_derate_ref_temp_c - ambient_temp_c) * 0.0025)
        chg_eff = max(0.85, self.battery_cfg.base_charge_eff - eff_loss)
        dis_eff = max(0.85, self.battery_cfg.base_discharge_eff - eff_loss)
        return effective_kwh, chg_eff, dis_eff

    def calculate_wind_power(self, wind_speed_ms: float, icing: bool = False) -> Tuple[float, bool]:
        """Computes wind turbine generation with 25 m/s blizzard cut-out and icing derate."""
        if wind_speed_ms < self.wind_cfg.cut_in_speed_ms:
            return 0.0, False
        if wind_speed_ms >= self.wind_cfg.cut_out_speed_ms:
            # Polar blizzard safety cut-out! High winds feather blades to prevent catastrophic structural failure.
            return 0.0, True
        
        if wind_speed_ms < self.wind_cfg.rated_speed_ms:
            fraction = (wind_speed_ms - self.wind_cfg.cut_in_speed_ms) / (self.wind_cfg.rated_speed_ms - self.wind_cfg.cut_in_speed_ms)
            p = self.wind_cfg.rated_kw * (fraction ** 3)
        else:
            p = self.wind_cfg.rated_kw
            
        if icing:
            p *= (1.0 - self.wind_cfg.icing_derate_max)
            
        return float(min(self.wind_cfg.rated_kw, max(0.0, p))), False

    def calculate_pv_power(self, irradiance_w_m2: float, ambient_temp_c: float) -> float:
        """Computes PV output incorporating polar bifacial snow/ice albedo gain and low-temp efficiency boost."""
        if irradiance_w_m2 <= 1.0:
            return 0.0
        # 1000 W/m2 is STC (Standard Test Conditions)
        base_kw = (irradiance_w_m2 / 1000.0) * self.pv_cfg.peak_kw
        # Bifacial snow albedo reflectance (Antarctic blue ice and snow gives high albedo boost)
        albedo_boost = 1.0 + self.pv_cfg.bifacial_albedo_gain
        # PV temperature coefficient (solar PV cells produce slightly higher voltage in extreme cold)
        temp_delta = ambient_temp_c - 25.0
        temp_factor = 1.0 + (self.pv_cfg.temp_coefficient_per_c * temp_delta)
        
        pv_output = base_kw * albedo_boost * temp_factor
        return float(max(0.0, pv_output))

    def calculate_genset_fuel(self, power_kw: float, is_on: bool, is_starting: bool = False, genset_idx: int = 0) -> float:
        """Computes diesel fuel consumption in Litres."""
        if not is_on or power_kw < 0.1:
            return 0.0
        g = self.genset_cfg[genset_idx]
        actual_kw = max(g.min_kw, min(g.rated_kw, power_kw))
        fuel_l = g.fuel_intercept_l_per_h + (g.fuel_slope_l_per_kwh * actual_kw)
        if is_starting:
            fuel_l += g.start_cost_fuel_equivalent_l
        return float(fuel_l)

    def calculate_reserve_requirement(self, load_kw: float, pv_kw: float, wind_kw: float, wind_speed_ms: float) -> float:
        """Dynamic spinning reserve sizing: 12% load + 25% PV + 30-70% wind (Slide 3)."""
        if wind_speed_ms >= self.cfg.blizzard_warning_wind_ms:
            wind_fraction = self.cfg.reserve_wind_fraction_high
        else:
            # Linear ramp from 30% to 70% as wind speed approaches blizzard cut-out
            ratio = max(0.0, (wind_speed_ms - 15.0) / (self.wind_cfg.cut_out_speed_ms - 15.0))
            wind_fraction = self.cfg.reserve_wind_fraction_base + ratio * (self.cfg.reserve_wind_fraction_high - self.cfg.reserve_wind_fraction_base)
            wind_fraction = min(self.cfg.reserve_wind_fraction_high, max(self.cfg.reserve_wind_fraction_base, wind_fraction))
            
        reserve = (self.cfg.reserve_load_fraction * load_kw) + (self.cfg.reserve_pv_fraction * pv_kw) + (wind_fraction * wind_kw)
        return float(reserve)
