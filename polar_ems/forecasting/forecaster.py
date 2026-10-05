"""Polar Load, Solar PV, and Wind Generation Forecaster using Gradient Boosting (scikit-learn)
and physical weather conversion models (power curves, blizzard cut-out, solar geometry).
"""

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from typing import List, Tuple, Dict, Any, Optional
from ..simulation.microgrid import PolarMicrogridSimulator
from ..config import StationConfig, DEFAULT_STATION_CONFIG

class PolarForecaster:
    def __init__(self, config: StationConfig = DEFAULT_STATION_CONFIG):
        self.cfg = config
        self.sim = PolarMicrogridSimulator(config)
        self.load_model = HistGradientBoostingRegressor(
            max_iter=150,
            learning_rate=0.08,
            max_leaf_nodes=31,
            random_state=42
        )
        self.is_trained = False

    def train_load_forecaster(self, hours: List[int], temps: List[float], loads: List[float]):
        """Trains the load forecasting model on historical load and temperature readings."""
        X, y = [], []
        # Construct feature matrix
        # Features: [hour_of_day, temp_c, lag_24h, lag_1h, rolling_24h_mean]
        n = len(loads)
        for i in range(24, n):
            h_day = hours[i] % 24
            t_curr = temps[i]
            lag24 = loads[i - 24]
            lag1 = loads[i - 1]
            roll_mean = float(np.mean(loads[max(0, i - 24):i]))
            X.append([h_day, t_curr, lag24, lag1, roll_mean])
            y.append(loads[i])
            
        if len(X) > 24:
            self.load_model.fit(np.array(X), np.array(y))
            self.is_trained = True

    def forecast_horizon(
        self,
        current_hour: int,
        horizon_hours: int,
        past_loads: List[float],
        forecast_temps: List[float],
        forecast_wind_speeds: List[float],
        forecast_irradiances: List[float],
        forecast_icing: Optional[List[bool]] = None
    ) -> Dict[str, List[float]]:
        """Forecasts electrical demand, PV, Wind, and Reserve requirements for the next H hours."""
        if forecast_icing is None:
            forecast_icing = [False] * horizon_hours
            
        pred_loads = []
        pred_pvs = []
        pred_winds = []
        pred_reserves = []
        blizzard_risks = []
        
        sim_loads = list(past_loads)
        
        for step in range(horizon_hours):
            abs_hour = current_hour + step
            h_day = abs_hour % 24
            t_fc = forecast_temps[step]
            w_speed = forecast_wind_speeds[step]
            irrad = forecast_irradiances[step]
            icing = forecast_icing[step]
            
            # 1. Load forecast via ML
            if self.is_trained and len(sim_loads) >= 24:
                lag24 = sim_loads[-24]
                lag1 = sim_loads[-1]
                roll_mean = float(np.mean(sim_loads[-24:]))
                feat = np.array([[h_day, t_fc, lag24, lag1, roll_mean]])
                l_pred = float(self.load_model.predict(feat)[0])
            else:
                # Fallback persistence with diurnal scaling
                base = sim_loads[-1] if sim_loads else 50.0
                l_pred = base + 5.0 * np.sin(2 * np.pi * (h_day - 8) / 24.0)
            
            l_pred = max(25.0, l_pred)
            pred_loads.append(l_pred)
            sim_loads.append(l_pred)
            
            # 2. PV forecast via physics
            pv_pred = self.sim.calculate_pv_power(irrad, t_fc)
            pred_pvs.append(pv_pred)
            
            # 3. Wind forecast via power curve with 25 m/s storm shutdown
            w_pred, cutout = self.sim.calculate_wind_power(w_speed, icing=icing)
            pred_winds.append(w_pred)
            blizzard_risks.append(cutout or (w_speed >= self.cfg.blizzard_warning_wind_ms))
            
            # 4. Reserve calculation
            res = self.sim.calculate_reserve_requirement(l_pred, pv_pred, w_pred, w_speed)
            pred_reserves.append(res)
            
        return {
            "forecast_load_kw": pred_loads,
            "forecast_pv_kw": pred_pvs,
            "forecast_wind_kw": pred_winds,
            "forecast_reserves_kw": pred_reserves,
            "blizzard_risks": blizzard_risks
        }
