"""Mixed-Integer Linear Programming (MILP) Microgrid Dispatch Optimizer using SciPy HiGHS backend.
Implements cold battery derating, 30% genset minimum load, 3h minimum runtime, dynamic spinning reserves,
and deferrable load scheduling.
"""

import time
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from scipy.optimize import milp, LinearConstraint, Bounds
from ..config import StationConfig, DEFAULT_STATION_CONFIG
from ..simulation.microgrid import PolarMicrogridSimulator

@dataclass
class OptimizationResult:
    success: bool
    status_message: str
    solve_duration_ms: float
    genset1_kw: List[float]
    genset2_kw: List[float]
    genset1_state: List[bool]
    genset2_state: List[bool]
    batt_charge_kw: List[float]
    batt_discharge_kw: List[float]
    batt_soc: List[float]
    deferrable_kw: List[float]
    curtailment_kw: List[float]
    unserved_kw: List[float]
    fuel_liters_total: float
    baseline_fuel_liters: float
    fuel_saved_liters: float
    fuel_saved_pct: float
    diesel_off_hours: int
    renewable_share_pct: float
    co2_avoided_kg: float

class PolarMILPOptimizer:
    def __init__(self, config: StationConfig = DEFAULT_STATION_CONFIG):
        self.cfg = config
        self.sim = PolarMicrogridSimulator(config)

    def optimize_horizon(
        self,
        horizon_hours: int,
        initial_soc: float,
        initial_genset_states: List[bool],
        initial_run_hours: List[int],
        forecast_loads_kw: List[float],
        forecast_pv_kw: List[float],
        forecast_wind_kw: List[float],
        forecast_wind_speeds: List[float],
        ambient_temps_c: List[float],
        deferrable_total_kwh: float = 100.0,
        deferrable_max_kw: float = 25.0,
        blizzard_override: bool = False
    ) -> OptimizationResult:
        """Formulates and solves the Polar Microgrid MILP using HiGHS."""
        start_time = time.perf_counter()
        T = horizon_hours
        
        # Effective battery capacity and efficiency under polar cold
        avg_temp = float(np.mean(ambient_temps_c))
        effective_bess_kwh, chg_eff, dis_eff = self.sim.get_effective_battery_capacity(avg_temp)
        
        # Variables per time step t (0 to T-1):
        # 0: u1 (binary, Genset 1 on/off)
        # 1: u2 (binary, Genset 2 on/off)
        # 2: v1 (continuous/binary, Genset 1 startup)
        # 3: v2 (continuous/binary, Genset 2 startup)
        # 4: Pg1 (continuous, Genset 1 power kW)
        # 5: Pg2 (continuous, Genset 2 power kW)
        # 6: Pchg (continuous, Battery charge kW)
        # 7: Pdis (continuous, Battery discharge kW)
        # 8: SoC (continuous, Battery state of charge 0-1)
        # 9: Pdef (continuous, Deferrable load kW)
        # 10: Pcurt (continuous, Curtailment kW)
        # 11: Puns (continuous, Unserved critical load kW)
        VARS_PER_STEP = 12
        N = T * VARS_PER_STEP
        
        def idx(t: int, var_id: int) -> int:
            return t * VARS_PER_STEP + var_id

        # 1. Objective Vector c
        c = np.zeros(N)
        g1 = self.cfg.gensets[0]
        g2 = self.cfg.gensets[1]
        
        for t in range(T):
            c[idx(t, 0)] = g1.fuel_intercept_l_per_h
            c[idx(t, 1)] = g2.fuel_intercept_l_per_h
            c[idx(t, 2)] = g1.start_cost_fuel_equivalent_l
            c[idx(t, 3)] = g2.start_cost_fuel_equivalent_l
            c[idx(t, 4)] = g1.fuel_slope_l_per_kwh
            c[idx(t, 5)] = g2.fuel_slope_l_per_kwh
            c[idx(t, 6)] = self.cfg.battery.wear_cost_per_kwh
            c[idx(t, 7)] = self.cfg.battery.wear_cost_per_kwh
            c[idx(t, 8)] = -0.01  # Slight incentive to keep battery charged for polar safety
            c[idx(t, 9)] = 0.0
            c[idx(t, 10)] = 0.02  # Slight curtailment penalty
            c[idx(t, 11)] = 10000.0 # Extreme penalty for unserved critical load!

        # 2. Integrality Vector (1 = integer/binary, 0 = continuous)
        integrality = np.zeros(N, dtype=int)
        for t in range(T):
            integrality[idx(t, 0)] = 1 # u1 binary
            integrality[idx(t, 1)] = 1 # u2 binary

        # 3. Variable Bounds
        lb = np.zeros(N)
        ub = np.zeros(N)
        
        soc_min = self.cfg.battery.min_soc
        soc_max = self.cfg.battery.max_soc
        max_chg = self.cfg.battery.max_charge_kw
        max_dis = self.cfg.battery.max_discharge_kw
        
        for t in range(T):
            # u1, u2
            lb[idx(t, 0)] = 0; ub[idx(t, 0)] = 1
            lb[idx(t, 1)] = 0; ub[idx(t, 1)] = 1
            # v1, v2
            lb[idx(t, 2)] = 0; ub[idx(t, 2)] = 1
            lb[idx(t, 3)] = 0; ub[idx(t, 3)] = 1
            # Pg1, Pg2
            lb[idx(t, 4)] = 0; ub[idx(t, 4)] = g1.rated_kw
            lb[idx(t, 5)] = 0; ub[idx(t, 5)] = g2.rated_kw
            # Pchg, Pdis
            lb[idx(t, 6)] = 0; ub[idx(t, 6)] = max_chg
            lb[idx(t, 7)] = 0; ub[idx(t, 7)] = max_dis
            # SoC
            lb[idx(t, 8)] = soc_min; ub[idx(t, 8)] = soc_max
            # Pdef
            lb[idx(t, 9)] = 0; ub[idx(t, 9)] = deferrable_max_kw
            # Pcurt
            lb[idx(t, 10)] = 0; ub[idx(t, 10)] = 200.0
            # Puns
            lb[idx(t, 11)] = 0; ub[idx(t, 11)] = 200.0

        # 4. Constraints Construction
        row_list = []
        lhs_list = []
        rhs_list = []

        dt = 1.0 # 1 hour time steps
        
        for t in range(T):
            crit_load = forecast_loads_kw[t]
            pv = forecast_pv_kw[t]
            wind = 0.0 if blizzard_override else forecast_wind_kw[t]
            net_renewable = pv + wind
            
            # Constraint A: Power Balance
            # Pg1 + Pg2 + Pdis - Pchg - Pcurt + Puns - Pdef = crit_load - net_renewable
            row = np.zeros(N)
            row[idx(t, 4)] = 1.0  # Pg1
            row[idx(t, 5)] = 1.0  # Pg2
            row[idx(t, 7)] = 1.0  # Pdis
            row[idx(t, 6)] = -1.0 # Pchg
            row[idx(t, 10)] = -1.0# Pcurt
            row[idx(t, 11)] = 1.0 # Puns
            row[idx(t, 9)] = -1.0 # Pdef
            row_list.append(row)
            lhs_list.append(crit_load - net_renewable)
            rhs_list.append(crit_load - net_renewable)

            # Constraint B: Genset 1 Min Load when ON
            # Pg1 - g1.min_kw * u1 >= 0
            row = np.zeros(N)
            row[idx(t, 4)] = 1.0
            row[idx(t, 0)] = -g1.min_kw
            row_list.append(row)
            lhs_list.append(0.0)
            rhs_list.append(np.inf)

            # Constraint C: Genset 1 Max Load when ON
            # Pg1 - g1.rated_kw * u1 <= 0
            row = np.zeros(N)
            row[idx(t, 4)] = 1.0
            row[idx(t, 0)] = -g1.rated_kw
            row_list.append(row)
            lhs_list.append(-np.inf)
            rhs_list.append(0.0)

            # Constraint D: Genset 2 Min Load when ON
            # Pg2 - g2.min_kw * u2 >= 0
            row = np.zeros(N)
            row[idx(t, 5)] = 1.0
            row[idx(t, 1)] = -g2.min_kw
            row_list.append(row)
            lhs_list.append(0.0)
            rhs_list.append(np.inf)

            # Constraint E: Genset 2 Max Load when ON
            # Pg2 - g2.rated_kw * u2 <= 0
            row = np.zeros(N)
            row[idx(t, 5)] = 1.0
            row[idx(t, 1)] = -g2.rated_kw
            row_list.append(row)
            lhs_list.append(-np.inf)
            rhs_list.append(0.0)

            # Constraint F: Startup detection v_i(t) >= u_i(t) - u_i(t-1)
            # v1(t) - u1(t) + u1(t-1) >= 0
            row = np.zeros(N)
            row[idx(t, 2)] = 1.0
            row[idx(t, 0)] = -1.0
            if t == 0:
                u1_prev = 1.0 if initial_genset_states[0] else 0.0
                lhs_list.append(-u1_prev)
            else:
                row[idx(t - 1, 0)] = 1.0
                lhs_list.append(0.0)
            row_list.append(row)
            rhs_list.append(np.inf)

            # v2(t) - u2(t) + u2(t-1) >= 0
            row = np.zeros(N)
            row[idx(t, 3)] = 1.0
            row[idx(t, 1)] = -1.0
            if t == 0:
                u2_prev = 1.0 if initial_genset_states[1] else 0.0
                lhs_list.append(-u2_prev)
            else:
                row[idx(t - 1, 1)] = 1.0
                lhs_list.append(0.0)
            row_list.append(row)
            rhs_list.append(np.inf)

            # Constraint G: Minimum Run-Time (3 hours)
            # If started at t, must run for min(U, T - t) hours:
            # sum_{tau=t}^{min(t+U-1, T-1)} u_i(tau) >= min(U, T-t) * v_i(t)
            U1 = g1.min_runtime_hours
            tau_max_1 = min(t + U1, T)
            run_span_1 = tau_max_1 - t
            row = np.zeros(N)
            for tau in range(t, tau_max_1):
                row[idx(tau, 0)] += 1.0
            row[idx(t, 2)] -= run_span_1
            row_list.append(row)
            lhs_list.append(0.0)
            rhs_list.append(np.inf)

            U2 = g2.min_runtime_hours
            tau_max_2 = min(t + U2, T)
            run_span_2 = tau_max_2 - t
            row = np.zeros(N)
            for tau in range(t, tau_max_2):
                row[idx(tau, 1)] += 1.0
            row[idx(t, 3)] -= run_span_2
            row_list.append(row)
            lhs_list.append(0.0)
            rhs_list.append(np.inf)

            # Constraint H: Battery SoC Continuity
            # SoC(t) = SoC(t-1) + (eta_chg * Pchg(t-1) - (1/eta_dis) * Pdis(t-1)) * (dt / C_eff)
            # SoC(t) - SoC(t-1) - alpha_chg * Pchg(t-1) + alpha_dis * Pdis(t-1) = 0
            alpha_chg = (chg_eff * dt) / effective_bess_kwh
            alpha_dis = (dt) / (dis_eff * effective_bess_kwh)
            
            row = np.zeros(N)
            row[idx(t, 8)] = 1.0 # SoC(t)
            if t == 0:
                row_list.append(row)
                lhs_list.append(initial_soc)
                rhs_list.append(initial_soc)
            else:
                row[idx(t - 1, 8)] = -1.0
                row[idx(t - 1, 6)] = -alpha_chg
                row[idx(t - 1, 7)] = alpha_dis
                row_list.append(row)
                lhs_list.append(0.0)
                rhs_list.append(0.0)

            # Constraint I: Dynamic Spinning Reserve
            # (g1.rated_kw * u1 - Pg1) + (g2.rated_kw * u2 - Pg2) + (max_dis - Pdis) >= R_req(t)
            r_req = self.sim.calculate_reserve_requirement(crit_load, pv, wind, forecast_wind_speeds[t])
            row = np.zeros(N)
            row[idx(t, 0)] = g1.rated_kw
            row[idx(t, 4)] = -1.0
            row[idx(t, 1)] = g2.rated_kw
            row[idx(t, 5)] = -1.0
            row[idx(t, 7)] = -1.0
            row_list.append(row)
            lhs_list.append(r_req - max_dis)
            rhs_list.append(np.inf)

        # Constraint J: Deferrable Load Total Energy Quota
        # sum_{t=0}^{T-1} Pdef(t) * dt == deferrable_total_kwh
        row = np.zeros(N)
        for t in range(T):
            row[idx(t, 9)] = dt
        row_list.append(row)
        lhs_list.append(deferrable_total_kwh)
        rhs_list.append(deferrable_total_kwh)

        # Build HiGHS inputs
        A = np.array(row_list)
        lhs = np.array(lhs_list)
        rhs = np.array(rhs_list)
        
        constraints = LinearConstraint(A, lhs, rhs)
        bounds = Bounds(lb, ub)
        
        # Execute MILP solve
        res = milp(c=c, integrality=integrality, constraints=constraints, bounds=bounds)
        solve_dur = (time.perf_counter() - start_time) * 1000.0 # ms

        if not res.success:
            return OptimizationResult(
                success=False,
                status_message=f"MILP solve failed: {res.message}",
                solve_duration_ms=solve_dur,
                genset1_kw=[0.0] * T,
                genset2_kw=[0.0] * T,
                genset1_state=[False] * T,
                genset2_state=[False] * T,
                batt_charge_kw=[0.0] * T,
                batt_discharge_kw=[0.0] * T,
                batt_soc=[initial_soc] * T,
                deferrable_kw=[0.0] * T,
                curtailment_kw=[0.0] * T,
                unserved_kw=[0.0] * T,
                fuel_liters_total=0.0,
                baseline_fuel_liters=0.0,
                fuel_saved_liters=0.0,
                fuel_saved_pct=0.0,
                diesel_off_hours=0,
                renewable_share_pct=0.0,
                co2_avoided_kg=0.0
            )

        # Unpack solution
        x = res.x
        g1_kw, g2_kw = [], []
        g1_state, g2_state = [], []
        b_chg, b_dis, b_soc = [], [], []
        p_def, p_curt, p_uns = [], [], []
        
        fuel_total = 0.0
        baseline_fuel = 0.0
        diesel_off_hrs = 0
        total_gen_kwh = 0.0
        renewables_kwh = 0.0
        
        for t in range(T):
            u1_val = bool(x[idx(t, 0)] > 0.5)
            u2_val = bool(x[idx(t, 1)] > 0.5)
            p1_val = float(x[idx(t, 4)]) if u1_val else 0.0
            p2_val = float(x[idx(t, 5)]) if u2_val else 0.0
            
            g1_state.append(u1_val)
            g2_state.append(u2_val)
            g1_kw.append(p1_val)
            g2_kw.append(p2_val)
            
            chg_val = float(x[idx(t, 6)])
            dis_val = float(x[idx(t, 7)])
            soc_val = float(x[idx(t, 8)])
            b_chg.append(chg_val)
            b_dis.append(dis_val)
            b_soc.append(soc_val)
            
            p_def.append(float(x[idx(t, 9)]))
            p_curt.append(float(x[idx(t, 10)]))
            p_uns.append(float(x[idx(t, 11)]))
            
            # Fuel calculations
            is_start1 = bool(x[idx(t, 2)] > 0.5)
            is_start2 = bool(x[idx(t, 3)] > 0.5)
            f1 = self.sim.calculate_genset_fuel(p1_val, u1_val, is_starting=is_start1, genset_idx=0)
            f2 = self.sim.calculate_genset_fuel(p2_val, u2_val, is_starting=is_start2, genset_idx=1)
            fuel_total += (f1 + f2)
            
            if not u1_val and not u2_val:
                diesel_off_hrs += 1
                
            # Baseline: Always-on genset (Genset 1 running continuously to meet critical + deferrable load without renewables)
            base_kw = max(g1.min_kw, min(g1.rated_kw, forecast_loads_kw[t] + 4.17))
            baseline_fuel += (g1.fuel_intercept_l_per_h + g1.fuel_slope_l_per_kwh * base_kw)
            
            # Renewable share
            pv_t = forecast_pv_kw[t]
            wind_t = 0.0 if blizzard_override else forecast_wind_kw[t]
            renewables_kwh += (pv_t + wind_t)
            total_gen_kwh += (p1_val + p2_val + pv_t + wind_t)

        fuel_saved = max(0.0, baseline_fuel - fuel_total)
        fuel_saved_pct = (fuel_saved / baseline_fuel * 100.0) if baseline_fuel > 0 else 0.0
        co2_avoided = fuel_saved * g1.co2_kg_per_l_diesel
        ren_share = (renewables_kwh / total_gen_kwh * 100.0) if total_gen_kwh > 0 else 0.0

        return OptimizationResult(
            success=True,
            status_message="HiGHS Optimal Dispatch Found",
            solve_duration_ms=solve_dur,
            genset1_kw=g1_kw,
            genset2_kw=g2_kw,
            genset1_state=g1_state,
            genset2_state=g2_state,
            batt_charge_kw=b_chg,
            batt_discharge_kw=b_dis,
            batt_soc=b_soc,
            deferrable_kw=p_def,
            curtailment_kw=p_curt,
            unserved_kw=p_uns,
            fuel_liters_total=round(fuel_total, 2),
            baseline_fuel_liters=round(baseline_fuel, 2),
            fuel_saved_liters=round(fuel_saved, 2),
            fuel_saved_pct=round(fuel_saved_pct, 1),
            diesel_off_hours=diesel_off_hrs,
            renewable_share_pct=round(ren_share, 1),
            co2_avoided_kg=round(co2_avoided, 2)
        )
