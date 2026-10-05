"""SQLite-based Edge Time-Series and Operator Audit Database with WAL mode for rugged polar edge PCs."""

import sqlite3
import json
import os
from typing import List, Dict, Any, Optional

class PolarDatabase:
    def __init__(self, db_path: str = "polar_ems.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for high concurrency and crash resilience on edge flash storage
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            # 1. Telemetry table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    station_id TEXT,
                    genset1_kw REAL,
                    genset2_kw REAL,
                    fuel_flow_l_per_h REAL,
                    batt_soc REAL,
                    batt_kw REAL,
                    batt_temp_c REAL,
                    pv_kw REAL,
                    wind_kw REAL,
                    wind_speed_ms REAL,
                    ambient_temp_c REAL,
                    critical_load_kw REAL,
                    deferrable_load_kw REAL,
                    unserved_kw REAL,
                    diesel_off INTEGER,
                    system_status TEXT
                );
            """)

            # 2. Dispatch plans table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dispatch_plans (
                    plan_id TEXT PRIMARY KEY,
                    station_id TEXT,
                    generated_at TEXT,
                    horizon_hours INTEGER,
                    estimated_fuel_l REAL,
                    fuel_saved_pct REAL,
                    diesel_off_hours INTEGER,
                    renewable_share_pct REAL,
                    operator_approved INTEGER DEFAULT 0,
                    operator_notes TEXT,
                    plan_json TEXT
                );
            """)

            # 3. Operator audit log table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS operator_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    plan_id TEXT,
                    operator_user TEXT,
                    details TEXT
                );
            """)
            conn.commit()

    def log_telemetry(self, t: Dict[str, Any]):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO telemetry (
                    timestamp, station_id, genset1_kw, genset2_kw, fuel_flow_l_per_h,
                    batt_soc, batt_kw, batt_temp_c, pv_kw, wind_kw, wind_speed_ms,
                    ambient_temp_c, critical_load_kw, deferrable_load_kw, unserved_kw,
                    diesel_off, system_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t.get("timestamp"), t.get("station_id", "BHARATI"),
                t.get("genset1_kw", 0.0), t.get("genset2_kw", 0.0),
                t.get("fuel_flow_l_per_h", 0.0), t.get("batt_soc", 0.65),
                t.get("batt_kw", 0.0), t.get("batt_temp_c", -10.0),
                t.get("pv_kw", 0.0), t.get("wind_kw", 0.0),
                t.get("wind_speed_ms", 10.0), t.get("ambient_temp_c", -25.0),
                t.get("critical_load_kw", 50.0), t.get("deferrable_load_kw", 0.0),
                t.get("unserved_kw", 0.0), 1 if t.get("diesel_off") else 0,
                t.get("system_status", "OPTIMAL")
            ))
            conn.commit()

    def save_dispatch_plan(self, plan_dict: Dict[str, Any]):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO dispatch_plans (
                    plan_id, station_id, generated_at, horizon_hours,
                    estimated_fuel_l, fuel_saved_pct, diesel_off_hours,
                    renewable_share_pct, operator_approved, operator_notes, plan_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                plan_dict["plan_id"], plan_dict["station_id"], plan_dict["generated_at"],
                plan_dict["horizon_hours"], plan_dict["estimated_fuel_l"],
                plan_dict["fuel_saved_pct"], plan_dict["diesel_off_hours"],
                plan_dict["renewable_share_pct"], 1 if plan_dict.get("operator_approved") else 0,
                plan_dict.get("operator_notes"), json.dumps(plan_dict)
            ))
            conn.commit()

    def log_operator_action(self, action: str, plan_id: str, operator_user: str, details: str):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO operator_audit_log (timestamp, action, plan_id, operator_user, details)
                VALUES (datetime('now'), ?, ?, ?, ?)
            """, (action, plan_id, operator_user, details))
            if plan_id and action == "APPROVE":
                conn.execute("UPDATE dispatch_plans SET operator_approved = 1 WHERE plan_id = ?", (plan_id,))
            conn.commit()

    def get_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM operator_audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
