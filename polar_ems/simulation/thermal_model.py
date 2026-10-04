"""Combined Heat & Power (CHP) and Thermal Management Engine for Polar Research Stations.

Addresses the critical critique:
"Diesel generators produce waste heat for habitat heating and snow melting.
When gensets are switched off in renewable/battery mode, what heats the station?
Needs thermal balance, heat recovery, and boiler fuel modeling."

Physics Model:
1. Station Thermal Demand (Q_demand):
   Q_demand = UA * (T_indoor - T_ambient) + Q_snowmelt
   - UA: Building overall heat loss coefficient (kW/°C)
   - T_indoor: Station comfort setpoint (+18°C)
   - Q_snowmelt: Constant thermal draw for drinking/utility water production from snow (~8 kW_th)

2. Genset Waste Heat Recovery (Q_recovered):
   Q_recovered = P_genset * eta_chp_rec
   - eta_chp_rec: Heat recovery efficiency from jacket water + exhaust gas (~1.35 kW_th / kW_elec)

3. Auxiliary Oil-Fired Boiler / Electric Heater:
   When Q_recovered < Q_demand (e.g. during diesel-off renewable periods):
   - Q_deficit = Q_demand - Q_recovered
   - Auxiliary boiler supplies Q_deficit
   - Boiler fuel consumption = Q_deficit / (LHV_diesel * eta_boiler)
   - Polar diesel LHV ≈ 10.0 kWh/L, eta_boiler ≈ 84% -> ~0.118 Litres / kWh_th

4. Net Fuel Analysis:
   Total Fuel = Genset Electrical Fuel + Auxiliary Boiler Fuel
"""

import math
from dataclasses import dataclass
from typing import Dict, Any, List

@dataclass
class ThermalConfig:
    indoor_temp_target_c: float = 18.0
    station_ua_kw_per_c: float = 1.25     # Well-insulated modular polar station
    snowmelt_thermal_kw: float = 8.0      # Continuous snow melting for potable water
    chp_recovery_ratio: float = 1.35      # kW_th per kW_elec (jacket water + exhaust)
    boiler_efficiency: float = 0.84       # Auxiliary polar oil-fired boiler efficiency
    diesel_lhv_kwh_per_l: float = 10.0    # Lower heating value of polar-grade diesel
    
    @property
    def boiler_fuel_litres_per_kwh_th(self) -> float:
        return 1.0 / (self.diesel_lhv_kwh_per_l * self.boiler_efficiency)

class PolarThermalEngine:
    def __init__(self, config: ThermalConfig = ThermalConfig()):
        self.cfg = config
        
    def calculate_thermal_demand(self, ambient_temp_c: float) -> float:
        """Calculates station heating and snow-melting thermal requirement (kW_th)."""
        temp_diff = max(0.0, self.cfg.indoor_temp_target_c - ambient_temp_c)
        building_loss = self.cfg.station_ua_kw_per_c * temp_diff
        return building_loss + self.cfg.snowmelt_thermal_kw
        
    def calculate_heat_recovery(self, genset_total_kw: float) -> float:
        """Calculates recovered thermal energy from genset jacket water and exhaust (kW_th)."""
        if genset_total_kw <= 0.0:
            return 0.0
        return genset_total_kw * self.cfg.chp_recovery_ratio

    def step(self, genset_kw: float, ambient_temp_c: float) -> Dict[str, Any]:
        """Calculates thermal balance for a 1-hour time step.
        
        Returns:
            demand_kw_th: Required heating power
            recovered_kw_th: Heat recovered from active gensets
            surplus_kw_th: Excess heat dumped via radiator
            deficit_kw_th: Heat required from auxiliary boiler
            boiler_fuel_l: Fuel consumed by auxiliary boiler
            boiler_active: Boolean indicating if boiler fired
        """
        demand = self.calculate_thermal_demand(ambient_temp_c)
        recovered = self.calculate_heat_recovery(genset_kw)
        
        if recovered >= demand:
            surplus = recovered - demand
            deficit = 0.0
            boiler_fuel = 0.0
            boiler_active = False
        else:
            surplus = 0.0
            deficit = demand - recovered
            boiler_fuel = deficit * self.cfg.boiler_fuel_litres_per_kwh_th
            boiler_active = True
            
        return {
            "demand_kw_th": round(demand, 2),
            "recovered_kw_th": round(recovered, 2),
            "surplus_kw_th": round(surplus, 2),
            "deficit_kw_th": round(deficit, 2),
            "boiler_fuel_l": round(boiler_fuel, 2),
            "boiler_active": boiler_active,
            "ambient_temp_c": round(ambient_temp_c, 1)
        }

    def simulate_dispatch_series(
        self,
        genset_kw_series: List[float],
        ambient_temp_series: List[float],
        genset_fuel_series: List[float]
    ) -> Dict[str, Any]:
        """Runs thermal simulation across a full time series and evaluates net fuel impact."""
        total_elec_fuel = sum(genset_fuel_series)
        total_boiler_fuel = 0.0
        total_thermal_demand = 0.0
        total_heat_recovered = 0.0
        boiler_run_hours = 0
        hourly_records = []
        
        for g_kw, t_amb, g_fuel in zip(genset_kw_series, ambient_temp_series, genset_fuel_series):
            res = self.step(g_kw, t_amb)
            res["genset_fuel_l"] = round(g_fuel, 2)
            res["net_fuel_l"] = round(g_fuel + res["boiler_fuel_l"], 2)
            
            total_boiler_fuel += res["boiler_fuel_l"]
            total_thermal_demand += res["demand_kw_th"]
            total_heat_recovered += res["recovered_kw_th"]
            if res["boiler_active"]:
                boiler_run_hours += 1
            hourly_records.append(res)
            
        net_fuel_total = total_elec_fuel + total_boiler_fuel
        
        return {
            "total_elec_fuel_l": round(total_elec_fuel, 2),
            "total_boiler_fuel_l": round(total_boiler_fuel, 2),
            "total_net_fuel_l": round(net_fuel_total, 2),
            "total_thermal_demand_kwh_th": round(total_thermal_demand, 2),
            "total_heat_recovered_kwh_th": round(total_heat_recovered, 2),
            "boiler_run_hours": boiler_run_hours,
            "total_hours": len(genset_kw_series),
            "hourly_records": hourly_records
        }
