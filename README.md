# POLAR EMS: AI-Driven Smart Energy Management System for Polar Research Stations

[![SIH 2026](https://img.shields.io/badge/SIH-2026-blue.svg)](https://sih.gov.in)
[![Problem Statement](https://img.shields.io/badge/PS_ID-SIH26061-orange.svg)](#)
[![Theme](https://img.shields.io/badge/Theme-Clean_%26_Green_Technology-green.svg)](#)
[![Team](https://img.shields.io/badge/Team-ByteForce_(118717)-purple.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-teal.svg)](#)

POLAR EMS is an **Offline-First, Safety-Guaranteed, Explainable Advisory Microgrid Energy Management System** built for Antarctic and Arctic research stations (such as India's **Bharati**, **Maitri**, and Arctic station **Himadri** under NCPOR / MoES).

---

## ❄️ Key Achievements & Measured Impact (Slide 5 Replication)

| Metric | Always-on Baseline | Tuned Rule-Based Controller | POLAR EMS (Optimized) |
| :--- | :--- | :--- | :--- |
| **Combined 60-Day Diesel Fuel** | 22,822 L | 16,633 L (-27.1%) | **16,041 L (-29.7%)** |
| **Summer 30-Day Diesel** | 10,932 L | 7,338 L (-32.9%) | **6,967 L (-36.3%)** |
| **Polar-Night 30-Day Diesel** | 11,890 L | 9,295 L (-21.8%) | **9,074 L (-23.7%)** |
| **Unserved Critical Energy** | 0.0 kWh | 0.0 kWh | **0.0 kWh (Safety Guarantee)** |
| **Genset Off-Hours (Polar Night)** | 0 h | ~260 h | **291 h / month** |
| **CO2 Avoided** | 0.0 t | 16.6 t | **18.2 tonnes** |
| **MILP Average Solve Time** | N/A | < 1 ms | **< 0.9 seconds (HiGHS Backend)** |

---

## 🛠️ Complete Technical Stack

| Domain | Technology / Library | Purpose |
| :--- | :--- | :--- |
| **Runtime** | Python 3.12 (Venv) | Isolated, reproducible virtual environment |
| **MILP Optimizer** | `scipy.optimize.milp` with HiGHS Solver | Solves 24-hour unit commitment & economic dispatch in < 0.9s |
| **Machine Learning** | `scikit-learn` (`HistGradientBoostingRegressor`) | Polar load forecasting using hour, temperature, lag-24h, and rolling statistics |
| **Physical Modeling** | NumPy & Python Math | Bifacial solar geometry, wind turbine power curves with 25 m/s blizzard cut-out, cold battery derating |
| **Edge Backend** | FastAPI, Uvicorn, AsyncIO, WebSockets | Asynchronous edge service running locally on rugged fanless industrial PC |
| **Edge Persistence** | SQLite 3 with Write-Ahead Logging (WAL) | Crash-resilient local time-series and permanent operator audit log |
| **Telemetry Ingestion** | Modbus TCP, OPC-UA, MQTT Simulator | Gap-filling, range validation, and polar anemometer rime-icing detection |
| **Operator UI** | HTML5, CSS3, JavaScript, Chart.js | Real-time dark Antarctic dashboard replicating ByteForce's SIH Slide 2 & 3 |

---

## 📐 Mathematical Formulation

### 1. Decision Variables ($t \in \{0, \dots, T-1\}$)
- $u_i(t) \in \{0, 1\}$: Binary status of genset $i \in \{1, 2\}$ (1 = ON, 0 = OFF)
- $v_i(t) \in \{0, 1\}$: Startup detection ($v_i(t) \ge u_i(t) - u_i(t-1)$)
- $P_{g,i}(t) \in [0, 80]$: Active power output of genset $i$ (kW)
- $P_{chg}(t), P_{dis}(t) \in [0, 100]$: Battery charge/discharge power (kW)
- $SoC(t) \in [0.20, 0.95]$: Battery state of charge
- $P_{def}(t) \in [0, 25]$: Flexible load allocated to snow-melter/water-maker (kW)
- $P_{curt}(t), P_{uns}(t) \ge 0$: Curtailment and unserved slack variables

### 2. Objective Function
$$\min \sum_{t=0}^{T-1} \left[ \sum_{i=1}^2 \left( F_{0,i} u_i(t) + k_i P_{g,i}(t) + C_{start} v_i(t) \right) + C_{deg} (P_{chg}(t) + P_{dis}(t)) + 10000 P_{uns}(t) + 0.02 P_{curt}(t) \right]$$

### 3. Key Polar Constraints
- **Power Balance:**
  $$\sum_{i=1}^2 P_{g,i}(t) + P_{wind}(t) + P_{pv}(t) + P_{dis}(t) - P_{chg}(t) - P_{def}(t) - P_{curt}(t) + P_{uns}(t) = P_{crit}(t)$$
- **Minimum Genset Loading:** $P_{g,i}(t) \ge 24 \cdot u_i(t)$ (30% load prevents wet stacking)
- **Minimum Run-Time:** $\sum_{\tau=t}^{\min(t+2, T-1)} u_i(\tau) \ge 3 \cdot v_i(t)$ (3 hours minimum run to avoid thermal shock)
- **Cold Battery Derating:** $C_{eff}(T) = C_{nom} \cdot \max(0.60, 1.0 - 0.008 \cdot \max(0, 15 - T_{ambient}))$
- **Dynamic Blizzard Reserve:** $R_{req}(t) = 0.12 P_{crit}(t) + 0.25 P_{pv}(t) + \alpha_{wind}(v_{wind}) P_{wind}(t)$, where $\alpha_{wind} \in [0.30, 0.70]$
- **Blizzard Safety Cut-Out:** $P_{wind}(v) = 0\text{ kW}$ when $v_{wind} \ge 25\text{ m/s}$

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.12 (already installed and configured in `venv/`)
- Modern web browser (Chrome, Edge, Firefox)

### 2. Activate Virtual Environment
In PowerShell:
```powershell
.\venv\Scripts\Activate.ps1
```
*(Or invoke via `& 'D:\Polar EMS\venv\Scripts\python.exe'` directly)*

### 3. Run the 60-Day Full Benchmark Validation
Executes both 30-day Summer and 30-day Polar-Night simulations (237 MILP solves):
```powershell
& 'D:\Polar EMS\venv\Scripts\python.exe' -u run_simulation.py
```

### 4. Launch the Edge Service & Operator Dashboard
Starts the FastAPI edge server and serves the real-time UI:
```powershell
& 'D:\Polar EMS\venv\Scripts\python.exe' -u start_edge_server.py
```

Open your browser to:
- **Operator Dashboard:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive OpenAPI Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 📂 Project Structure

```
d:\Polar EMS\
├── venv\                          # Python 3.12 Virtual Environment
├── requirements.txt               # Frozen dependencies
├── README.md                      # Project documentation
├── start_edge_server.py           # Launch script for Edge Service & Dashboard
├── run_simulation.py              # 60-day summer & winter benchmark runner
├── polar_ems\
│   ├── __init__.py
│   ├── config.py                  # Station specs (Bharati, Maitri, Himadri)
│   ├── models\
│   │   ├── __init__.py
│   │   └── schemas.py             # Pydantic data schemas
│   ├── simulation\
│   │   ├── __init__.py
│   │   ├── microgrid.py           # Microgrid physics (Gensets, Cold Battery, Wind, PV)
│   │   └── synthetic_data.py      # 30-day polar dataset generator
│   ├── forecasting\
│   │   ├── __init__.py
│   │   └── forecaster.py          # HistGradientBoosting load and renewable forecaster
│   ├── optimizer\
│   │   ├── __init__.py
│   │   └── milp_solver.py         # SciPy HiGHS MILP mathematical dispatch solver
│   ├── safety\
│   │   ├── __init__.py
│   │   ├── fallback_controller.py # Rule-based deterministic backup controller
│   │   └── sensor_validation.py   # Modbus/MQTT sensor range, drift, gap-fill checks
│   ├── storage\
│   │   ├── __init__.py
│   │   └── db.py                  # SQLite WAL edge database & operator audit trail
│   └── api\
│       ├── __init__.py
│       ├── main.py                # FastAPI edge service, static files, WebSocket
│       └── routes.py              # REST endpoints (status, dispatch, what-if, approve, override)
└── static\
    ├── index.html                 # Polar dark operator dashboard (Slide 2 & 3 UI)
    ├── style.css                  # Antarctic UI styling
    └── app.js                     # Interactive charts, WebSocket streaming, scenario sandbox
```

---

## 🧪 Interactive What-If Scenarios Built-in
1. **🌪️ Katabatic Blizzard:** Simulates a 32 m/s storm shutting down wind turbines, triggering automated spinning reserve response.
2. **⚠️ Genset 1 Mechanical Trip:** Simulates primary generator failure with auto-failover to Genset-2 and battery peaking.
3. **🌑 Polar Night:** Enforces 0 W/m² solar irradiance and -38°C Antarctic freeze.
4. **🚢 Expedition Surge:** Simulates research ship arrival with +40% station power demand.
5. **☀️ Austral Summer:** Continuous 24h midnight sun operation with peak solar generation.
