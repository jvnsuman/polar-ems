"""Configuration parameters for Polar EMS station microgrid assets and environment."""

from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class GensetConfig:
    name: str
    rated_kw: float = 80.0
    min_kw: float = 24.0             # 30% minimum load to avoid wet stacking
    min_runtime_hours: int = 3       # 3 h minimum run to prevent thermal shock
    fuel_intercept_l_per_h: float = 4.5   # Base idle fuel consumption (L/h)
    fuel_slope_l_per_kwh: float = 0.235   # Marginal fuel burn (L/kWh)
    start_cost_fuel_equivalent_l: float = 3.5  # Cold start penalty (equivalent L)
    co2_kg_per_l_diesel: float = 2.68    # 2.68 kg CO2 per liter of polar diesel burned

@dataclass
class BatteryConfig:
    nominal_capacity_kwh: float = 300.0
    max_charge_kw: float = 100.0
    max_discharge_kw: float = 100.0
    min_soc: float = 0.20           # 20% DoD threshold to preserve cell health
    max_soc: float = 0.95           # 95% max charge limit
    initial_soc: float = 0.65       # 65% initial SoC
    base_charge_eff: float = 0.96   # 96% charge one-way efficiency
    base_discharge_eff: float = 0.96 # 96% discharge one-way efficiency
    wear_cost_per_kwh: float = 0.015 # Degradation penalty per kWh throughput
    cold_derate_ref_temp_c: float = 15.0 # Optimal ambient temp
    cold_capacity_loss_per_c: float = 0.008 # 0.8% loss per degree below 15C
    cold_min_effective_ratio: float = 0.60 # Max cold derate cap (60% capacity floor)

@dataclass
class WindConfig:
    rated_kw: float = 100.0
    cut_in_speed_ms: float = 3.0
    rated_speed_ms: float = 11.5
    cut_out_speed_ms: float = 25.0   # Blizzard cut-out safety shutdown
    icing_derate_max: float = 0.15   # 15% generation loss during severe riming/icing

@dataclass
class SolarPVConfig:
    peak_kw: float = 80.0
    bifacial_albedo_gain: float = 0.15  # 15% extra yield from polar snow/ice reflectance
    temp_coefficient_per_c: float = -0.0035 # Slight efficiency improvement in extreme cold

@dataclass
class DeferrableLoadConfig:
    name: str = "Snow-Melt & Water Maker"
    daily_energy_kwh: float = 100.0  # 100 kWh/day
    max_kw: float = 25.0
    deadline_hour: int = 24         # Complete within rolling 24h window

@dataclass
class StationConfig:
    station_id: str = "BHARATI-ANTARCTICA"
    station_name: str = "Bharati Polar Research Station"
    latitude: float = -69.41        # Larsemann Hills, East Antarctica
    longitude: float = 76.19
    elevation_m: float = 35.0
    gensets: List[GensetConfig] = field(default_factory=lambda: [
        GensetConfig(name="Genset-1 (Primary)"),
        GensetConfig(name="Genset-2 (Secondary)")
    ])
    battery: BatteryConfig = field(default_factory=BatteryConfig)
    wind: WindConfig = field(default_factory=WindConfig)
    solar: SolarPVConfig = field(default_factory=SolarPVConfig)
    deferrable: DeferrableLoadConfig = field(default_factory=DeferrableLoadConfig)
    
    # Reserve requirement weights
    reserve_load_fraction: float = 0.12     # 12% load reserve
    reserve_pv_fraction: float = 0.25       # 25% solar reserve
    reserve_wind_fraction_base: float = 0.30 # 30% baseline wind reserve
    reserve_wind_fraction_high: float = 0.70 # 70% storm/blizzard approach wind reserve
    blizzard_warning_wind_ms: float = 21.0  # Wind speeds >= 21 m/s trigger storm reserve

DEFAULT_STATION_CONFIG = StationConfig()
