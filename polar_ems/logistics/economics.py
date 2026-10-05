"""Fuel logistics, illustrative economics and days-of-autonomy calculator.

EVERYTHING FINANCIAL HERE IS AN ILLUSTRATIVE ASSUMPTION, NOT A RESULT.
Unsourced constants: the delivered fuel cost (335 INR/L) and its four-part
breakdown, the hardware cost (3.5 lakh INR), the 60,000 L tank and the 15-day
reserve. Annual fuel volumes are extrapolated from the two synthetic benchmark
months (x 365/60), which are not a year of station operation. Savings are shown
against two references: the always-on genset (a weak baseline) and the rule
controller (the more honest one). Replace the constants with NCPOR figures before
quoting any rupee value.
"""

from dataclasses import dataclass
from typing import Dict, Any, List

@dataclass
class PolarEconomicsConfig:
    delivered_fuel_cost_inr_per_l: float = 335.0  # ₹/L delivered in Antarctica
    delivered_fuel_cost_usd_per_l: float = 4.02   # $/L delivered
    co2_kg_per_l_diesel: float = 2.68             # IPCC emission factor for marine diesel
    edge_hardware_capex_inr: float = 350000.0     # Rugged industrial PC + gateways
    edge_hardware_capex_usd: float = 4200.0
    bulk_fuel_tank_capacity_l: float = 60000.0    # Bharati / Maitri bulk fuel storage
    blizzard_safety_reserve_days: int = 15        # Minimum autonomy required for blizzard isolation

class PolarLogisticsEngine:
    def __init__(self, config: PolarEconomicsConfig = PolarEconomicsConfig()):
        self.cfg = config
        
    def calculate_cost_breakdown(self) -> Dict[str, Any]:
        """Provides the Antarctic delivered fuel cost breakdown."""
        return {
            "base_polar_diesel_inr": 85.0,
            "chartered_icebreaker_transport_inr": 160.0,
            "antarctic_offloading_and_sled_traverse_inr": 75.0,
            "environmental_monitoring_and_protocol_inr": 15.0,
            "total_delivered_cost_inr_per_l": self.cfg.delivered_fuel_cost_inr_per_l,
            "total_delivered_cost_usd_per_l": self.cfg.delivered_fuel_cost_usd_per_l
        }
        
    def calculate_annualized_roi(
        self,
        baseline_annual_diesel_l: float = None,
        polar_ems_annual_diesel_l: float = None,
        reference: str = "rule",
        weather_mode: str = "persistence",
    ) -> Dict[str, Any]:
        """Annualized savings, payback and CO2 against `reference` ('rule' or 'always_on').

        When the annual volumes are not given they are extrapolated from the benchmark
        results (two synthetic 30-day months x 365/60), using the conservative
        'persistence' weather mode unless told otherwise."""
        if baseline_annual_diesel_l is None or polar_ems_annual_diesel_l is None:
            from ..results import load_results
            c = load_results()["modes"][weather_mode]["combined"]
            key = "rule_fuel_l" if reference == "rule" else "always_on_fuel_l"
            baseline_annual_diesel_l = c[key] * 365.0 / 60.0
            polar_ems_annual_diesel_l = c["polar_ems_fuel_l"] * 365.0 / 60.0
        annual_saved_l = baseline_annual_diesel_l - polar_ems_annual_diesel_l
        saved_pct = (annual_saved_l / baseline_annual_diesel_l) * 100.0
        
        annual_saved_inr = annual_saved_l * self.cfg.delivered_fuel_cost_inr_per_l
        annual_saved_usd = annual_saved_l * self.cfg.delivered_fuel_cost_usd_per_l
        
        daily_saved_inr = annual_saved_inr / 365.0
        payback_days = self.cfg.edge_hardware_capex_inr / daily_saved_inr
        
        # 5-Year Life Cycle Net Benefit
        five_year_savings_inr = (annual_saved_inr * 5.0) - self.cfg.edge_hardware_capex_inr
        five_year_savings_usd = (annual_saved_usd * 5.0) - self.cfg.edge_hardware_capex_usd
        five_year_roi_pct = (five_year_savings_inr / self.cfg.edge_hardware_capex_inr) * 100.0
        
        # Environmental impact
        annual_co2_tonnes_avoided = (annual_saved_l * self.cfg.co2_kg_per_l_diesel) / 1000.0
        five_year_co2_tonnes = annual_co2_tonnes_avoided * 5.0
        
        return {
            "illustrative": True,
            "reference": reference,
            "baseline_annual_diesel_l": round(baseline_annual_diesel_l, 0),
            "polar_ems_annual_diesel_l": round(polar_ems_annual_diesel_l, 0),
            "annual_diesel_saved_l": round(annual_saved_l, 0),
            "annual_fuel_reduction_pct": round(saved_pct, 1),
            "annual_cost_savings_inr": round(annual_saved_inr, 2),
            "annual_cost_savings_inr_crores": round(annual_saved_inr / 1e7, 3),
            "annual_cost_savings_usd": round(annual_saved_usd, 2),
            "capex_inr": self.cfg.edge_hardware_capex_inr,
            "capex_usd": self.cfg.edge_hardware_capex_usd,
            "payback_period_days": round(payback_days, 1),
            "five_year_net_benefit_inr_crores": round(five_year_savings_inr / 1e7, 3),
            "five_year_roi_pct": round(five_year_roi_pct, 1),
            "annual_co2_tonnes_avoided": round(annual_co2_tonnes_avoided, 1),
            "five_year_co2_tonnes_avoided": round(five_year_co2_tonnes, 1)
        }

    def calculate_days_of_autonomy(
        self,
        current_fuel_tank_l: float,
        daily_consumption_history_l: List[float]
    ) -> Dict[str, Any]:
        """Calculates dynamic station days-of-autonomy and safety margins."""
        if not daily_consumption_history_l:
            daily_burn_rate = 265.0  # placeholder when no history is given
        else:
            daily_burn_rate = float(sum(daily_consumption_history_l[-7:]) / len(daily_consumption_history_l[-7:]))
            
        days_remaining = current_fuel_tank_l / max(10.0, daily_burn_rate)
        tank_fill_pct = (current_fuel_tank_l / self.cfg.bulk_fuel_tank_capacity_l) * 100.0
        
        # Risk assessment for polar blizzard supply cutoff
        if days_remaining < self.cfg.blizzard_safety_reserve_days:
            risk_level = "CRITICAL_LOW_RESERVE"
            advice = f"Autonomy ({days_remaining:.1f} days) is BELOW 15-day blizzard safety cutoff! Trigger fuel conservation mode."
        elif days_remaining < 30.0:
            risk_level = "MODERATE_RESERVE"
            advice = f"Autonomy is {days_remaining:.1f} days. Maintain renewable prioritization."
        else:
            risk_level = "SECURE_RESERVE"
            advice = f"Autonomy is {days_remaining:.1f} days. Fuel stock is ample."
            
        return {
            "current_tank_l": round(current_fuel_tank_l, 1),
            "tank_capacity_l": self.cfg.bulk_fuel_tank_capacity_l,
            "tank_fill_pct": round(tank_fill_pct, 1),
            "daily_burn_rate_l_per_day": round(daily_burn_rate, 1),
            "days_of_autonomy": round(days_remaining, 1),
            "blizzard_cutoff_margin_days": round(days_remaining - self.cfg.blizzard_safety_reserve_days, 1),
            "risk_level": risk_level,
            "operational_advice": advice
        }
