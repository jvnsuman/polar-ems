"""Deterministic rule-based fallback controller for Polar EMS.
Activated automatically if AI models, solver, or satellite link fails, ensuring 0 kWh unserved critical energy.
"""

from typing import Dict, Tuple, List
from ..config import StationConfig, DEFAULT_STATION_CONFIG
from ..simulation.microgrid import PolarMicrogridSimulator

class RuleBasedFallbackController:
    def __init__(self, config: StationConfig = DEFAULT_STATION_CONFIG):
        self.cfg = config
        self.sim = PolarMicrogridSimulator(config)
        self.g1_run_hours = 0
        self.g1_is_on = True
        self.g2_is_on = False

    def dispatch_step(
        self,
        critical_load_kw: float,
        deferrable_load_kw: float,
        pv_kw: float,
        wind_kw: float,
        wind_speed_ms: float,
        current_soc: float,
        ambient_temp_c: float
    ) -> Dict[str, float]:
        """Calculates instantaneous deterministic setpoints prioritizing critical life-support loads."""
        total_demand = critical_load_kw + deferrable_load_kw
        net_demand = total_demand - (pv_kw + wind_kw)
        
        effective_bess_kwh, chg_eff, dis_eff = self.sim.get_effective_battery_capacity(ambient_temp_c)
        r_req = self.sim.calculate_reserve_requirement(critical_load_kw, pv_kw, wind_kw, wind_speed_ms)
        
        max_dis = self.cfg.battery.max_discharge_kw
        max_chg = self.cfg.battery.max_charge_kw
        
        g1 = self.cfg.gensets[0]
        g2 = self.cfg.gensets[1]
        
        # State machine
        # Safe diesel-off condition: High renewables, SoC >= 45%, wind not near blizzard cut-out
        safe_to_shut_diesel = (
            net_demand <= 0.0 and 
            current_soc >= 0.45 and 
            wind_speed_ms < self.cfg.blizzard_warning_wind_ms and
            self.g1_run_hours >= g1.min_runtime_hours
        )
        
        if safe_to_shut_diesel:
            self.g1_is_on = False
            self.g2_is_on = False
            self.g1_run_hours = 0
            
            # Surplus charges battery
            surplus = abs(net_demand)
            p_chg = min(max_chg, surplus)
            p_dis = 0.0
            p_g1 = 0.0
            p_g2 = 0.0
            p_curt = surplus - p_chg
            p_uns = 0.0
        else:
            # Must run generators
            if net_demand <= 0:
                # Renewable surplus with genset running at minimum load
                self.g1_is_on = True
                self.g2_is_on = False
                p_g1 = g1.min_kw
                p_g2 = 0.0
                total_surplus = abs(net_demand) + p_g1
                p_chg = min(max_chg, total_surplus)
                p_dis = 0.0
                p_curt = total_surplus - p_chg
                p_uns = 0.0
                self.g1_run_hours += 1
            else:
                # Deficit exists
                # Check if battery can cover deficit while maintaining reserve
                usable_batt_power = min(max_dis, (current_soc - self.cfg.battery.min_soc) * effective_bess_kwh)
                
                if usable_batt_power >= (net_demand + r_req) and not self.g1_is_on:
                    # Battery covers load in diesel-off mode
                    p_dis = min(max_dis, net_demand)
                    p_chg = 0.0
                    p_g1 = 0.0
                    p_g2 = 0.0
                    p_curt = 0.0
                    p_uns = 0.0
                else:
                    # Generator must run
                    self.g1_is_on = True
                    self.g1_run_hours += 1
                    
                    if net_demand <= g1.rated_kw:
                        p_g1 = max(g1.min_kw, net_demand)
                        p_g2 = 0.0
                        p_dis = 0.0
                        p_chg = max(0.0, p_g1 - net_demand)
                        p_curt = 0.0
                        p_uns = 0.0
                    elif net_demand <= (g1.rated_kw + max_dis):
                        # G1 at full power + battery assist
                        p_g1 = g1.rated_kw
                        p_g2 = 0.0
                        p_dis = net_demand - g1.rated_kw
                        p_chg = 0.0
                        p_curt = 0.0
                        p_uns = 0.0
                    else:
                        # G1 + G2 both running
                        self.g2_is_on = True
                        p_g1 = g1.rated_kw
                        rem = net_demand - g1.rated_kw
                        p_g2 = max(g2.min_kw, min(g2.rated_kw, rem))
                        rem2 = rem - p_g2
                        p_dis = min(max_dis, max(0.0, rem2))
                        p_chg = 0.0
                        p_curt = 0.0
                        p_uns = max(0.0, rem2 - p_dis)

        fuel = self.sim.calculate_genset_fuel(p_g1, self.g1_is_on, genset_idx=0) + \
               self.sim.calculate_genset_fuel(p_g2, self.g2_is_on, genset_idx=1)
               
        return {
            "genset1_kw": p_g1,
            "genset2_kw": p_g2,
            "genset1_on": self.g1_is_on,
            "genset2_on": self.g2_is_on,
            "batt_charge_kw": p_chg,
            "batt_discharge_kw": p_dis,
            "curtailment_kw": p_curt,
            "unserved_kw": p_uns,
            "fuel_l": fuel,
            "diesel_off": not self.g1_is_on and not self.g2_is_on
        }
