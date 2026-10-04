"""Pydantic data models for Polar EMS telemetry, forecasts, optimization, and UI state."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class TelemetryRecord(BaseModel):
    timestamp: str
    station_id: str = "BHARATI-ANTARCTICA"
    genset1_kw: float
    genset2_kw: float
    fuel_flow_l_per_h: float
    batt_soc: float
    batt_kw: float       # Positive = discharge, Negative = charge
    batt_temp_c: float
    pv_kw: float
    wind_kw: float
    wind_speed_ms: float
    ambient_temp_c: float
    critical_load_kw: float
    deferrable_load_kw: float
    total_load_kw: float
    unserved_kw: float = 0.0
    curtailment_kw: float = 0.0
    diesel_off: bool = False
    system_status: str = "OPTIMAL_DISPATCH"

class ForecastRecord(BaseModel):
    hour: int
    timestamp: str
    forecast_load_kw: float
    forecast_pv_kw: float
    forecast_wind_kw: float
    forecast_wind_speed_ms: float
    forecast_temp_c: float
    reserve_required_kw: float
    blizzard_risk: bool = False

class DispatchPlanStep(BaseModel):
    hour_index: int
    timestamp: str
    genset1_kw: float
    genset2_kw: float
    genset_total_kw: float
    batt_charge_kw: float
    batt_discharge_kw: float
    batt_soc: float
    pv_kw: float
    wind_kw: float
    wind_speed_ms: float
    demand_kw: float
    deferrable_kw: float
    reserve_margin_kw: float
    diesel_off_mode: bool
    blizzard_cutout: bool = False

class DispatchPlan(BaseModel):
    plan_id: str
    station_id: str
    generated_at: str
    horizon_hours: int = 24
    steps: List[DispatchPlanStep]
    estimated_fuel_l: float
    baseline_fuel_l: float
    fuel_saved_l: float
    fuel_saved_pct: float
    estimated_co2_kg: float
    diesel_off_hours: int
    renewable_share_pct: float
    unserved_kwh: float = 0.0
    safety_check_passed: bool = True
    operator_approved: bool = False
    operator_notes: Optional[str] = None
    solve_duration_ms: float = 0.0

class KPIBenchmark(BaseModel):
    scenario_name: str
    duration_days: int
    total_diesel_liters: float
    always_on_baseline_liters: float
    fuel_saved_liters: float
    fuel_saved_pct: float
    diesel_vs_rule_based_pct: float
    genset_off_hours: int
    renewable_share_pct: float
    unserved_energy_kwh: float
    co2_avoided_tonnes: float
    avg_solve_time_s: float
    total_solves: int
    solve_failures: int = 0

class OperatorActionRequest(BaseModel):
    plan_id: str
    action: str  # "APPROVE" or "OVERRIDE" or "FALLBACK"
    override_genset1_kw: Optional[float] = None
    override_genset2_kw: Optional[float] = None
    notes: Optional[str] = None

class WhatIfScenarioRequest(BaseModel):
    scenario_type: str # "BLIZZARD_CUTOUT", "GENSET_FAULT", "POLAR_NIGHT", "EXPEDITION_SURGE", "BASE"
    parameter_override: Optional[Dict[str, Any]] = None

class SensorHealthStatus(BaseModel):
    sensor_id: str
    name: str
    protocol: str # "Modbus TCP", "OPC-UA", "MQTT"
    status: str   # "HEALTHY", "DRIFT_WARN", "ICING_FROZEN", "GAP_FILLED"
    last_val: float
    unit: str
    timestamp: str
