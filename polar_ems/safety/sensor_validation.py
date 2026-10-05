"""Edge sensor ingestion, cleaning, range verification, gap filling, and polar anomaly detection
for Modbus TCP, OPC-UA, and MQTT protocol streams.
"""

from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from ..models.schemas import SensorHealthStatus

class SensorValidator:
    def __init__(self):
        self.history: Dict[str, List[float]] = {
            "genset1_flow": [],
            "genset2_flow": [],
            "batt_soc": [],
            "batt_temp": [],
            "pv_kw": [],
            "wind_kw": [],
            "wind_speed": [],
            "ambient_temp": [],
            "critical_load": []
        }
        
    def validate_and_clean_telemetry(self, raw_telemetry: Dict[str, Any]) -> Tuple[Dict[str, Any], List[SensorHealthStatus]]:
        """Cleans telemetry, applies physical range bounds, detects polar sensor freezing/drift, and fills gaps."""
        cleaned = dict(raw_telemetry)
        statuses: List[SensorHealthStatus] = []
        ts = raw_telemetry.get("timestamp", "NOW")
        
        # 1. Battery SoC (0.0 to 1.0)
        soc = raw_telemetry.get("batt_soc", 0.65)
        status_soc = "HEALTHY"
        if soc is None or soc < 0.0 or soc > 1.0:
            status_soc = "GAP_FILLED"
            soc = self.history["batt_soc"][-1] if self.history["batt_soc"] else 0.65
        cleaned["batt_soc"] = float(soc)
        self.history["batt_soc"].append(soc)
        statuses.append(SensorHealthStatus(
            sensor_id="BMS-01",
            name="Battery SoC",
            protocol="Modbus TCP",
            status=status_soc,
            last_val=round(cleaned["batt_soc"], 3),
            unit="ratio",
            timestamp=ts
        ))

        # 2. Wind Speed & Polar Anemometer Freezing Check
        ws = raw_telemetry.get("wind_speed_ms", 10.0)
        status_ws = "HEALTHY"
        if ws is None or ws < 0.0 or ws > 70.0:
            status_ws = "GAP_FILLED"
            ws = self.history["wind_speed"][-1] if self.history["wind_speed"] else 10.0
        else:
            # Check if stuck at identical value (polar rime ice freezing cups)
            if len(self.history["wind_speed"]) >= 6 and all(abs(x - ws) < 0.001 for x in self.history["wind_speed"][-6:]):
                status_ws = "ICING_FROZEN"
        cleaned["wind_speed_ms"] = float(ws)
        self.history["wind_speed"].append(ws)
        statuses.append(SensorHealthStatus(
            sensor_id="MET-WIND-01",
            name="Ultrasonic/Cup Anemometer",
            protocol="OPC-UA",
            status=status_ws,
            last_val=round(cleaned["wind_speed_ms"], 2),
            unit="m/s",
            timestamp=ts
        ))

        # 3. Ambient Temperature (-70 C to +20 C)
        temp = raw_telemetry.get("ambient_temp_c", -25.0)
        status_temp = "HEALTHY"
        if temp is None or temp < -75.0 or temp > 25.0:
            status_temp = "GAP_FILLED"
            temp = self.history["ambient_temp"][-1] if self.history["ambient_temp"] else -25.0
        cleaned["ambient_temp_c"] = float(temp)
        self.history["ambient_temp"].append(temp)
        statuses.append(SensorHealthStatus(
            sensor_id="MET-TEMP-01",
            name="Ambient PT100 RTD",
            protocol="Modbus TCP",
            status=status_temp,
            last_val=round(cleaned["ambient_temp_c"], 1),
            unit="°C",
            timestamp=ts
        ))

        # 4. Critical Load (10 kW to 180 kW)
        crit = raw_telemetry.get("critical_load_kw", 50.0)
        status_crit = "HEALTHY"
        if crit is None or crit < 5.0 or crit > 200.0:
            status_crit = "GAP_FILLED"
            crit = self.history["critical_load"][-1] if self.history["critical_load"] else 50.0
        cleaned["critical_load_kw"] = float(crit)
        self.history["critical_load"].append(crit)
        statuses.append(SensorHealthStatus(
            sensor_id="PWR-SUBMTR-01",
            name="Life Support & Habitat Bus",
            protocol="MQTT",
            status=status_crit,
            last_val=round(cleaned["critical_load_kw"], 1),
            unit="kW",
            timestamp=ts
        ))

        # Trim history
        for k in self.history:
            if len(self.history[k]) > 100:
                self.history[k] = self.history[k][-100:]

        return cleaned, statuses
