# POLAR EMS: AI-Driven Smart Energy Management System for Polar Research Stations

**AI-Driven Smart Energy Management for Polar Research Stations**  
*Smart India Hackathon 2026 · Problem Statement SIH26061 · Theme: Clean & Green Technology · Team ByteForce (Team ID 118717)*

[![SIH 2026](https://img.shields.io/badge/SIH-2026-blue.svg)](https://sih.gov.in)
[![PS](https://img.shields.io/badge/PS_ID-SIH26061-orange.svg)](#)
[![Theme](https://img.shields.io/badge/Theme-Clean_%26_Green_Technology-green.svg)](#)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-teal.svg)](LICENSE)
[![Architecture Docs](https://img.shields.io/badge/Docs-Architecture-blue.svg)](docs/ARCHITECTURE.md)
[![Evaluation Docs](https://img.shields.io/badge/Docs-Evaluation-green.svg)](docs/EVALUATION.md)

POLAR EMS is an **advisory-first, offline-first** energy management system built specifically for polar station microgrids: diesel gensets, solar PV, wind turbines, cold-derated battery energy storage, and deferrable life-support loads (snow-melting / water-maker). It is calibrated for Indian Antarctic research stations (**Bharati** at 69°24'S in the Larsemann Hills, **Maitri** at 70°45'S in the Schirmacher Oasis) and High Arctic station **Himadri** (78°55'N in Ny-Ålesund, Svalbard) under the National Centre for Polar and Ocean Research (NCPOR / MoES).

> 📖 **Deep Dive Documentation:**
> - 🏛️ **[System Architecture & 6-Stage Pipeline](docs/ARCHITECTURE.md)**: Physical boundary, sensor validation, runtime state, and HiGHS optimizer formulation.
> - 📊 **[Empirical Evaluation & Benchmarks](docs/EVALUATION.md)**: Slide 5 benchmark reproduction, open-loop shortfall analysis, and known edge constraints.
> - 🗺️ **[End-to-End Pipeline SVG Flow](docs/assets/polar-ems-flow.svg)**: Complete 4-layer architecture diagram.

---

## ❄️ Measured Impact & Benchmark Replication (Slide 3 & 5)

| Metric | Always-on Baseline | Tuned Rule-Based Controller | POLAR EMS (AI ML + HiGHS) | Perfect-Forecast Bound |
| :--- | :--- | :--- | :--- | :--- |
| **Combined 60-Day Diesel** | 22,822 L | 16,633 L (-27.1%) | **16,041 L (-29.7%)** | 15,396 L (-32.5%) |
| **Summer 30-Day Diesel** | 10,932 L | 7,338 L (-32.9%) | **6,967 L (-36.3%)** | 6,626 L (-39.4%) |
| **Polar-Night 30-Day Diesel** | 11,890 L | 9,295 L (-21.8%) | **9,074 L (-23.7%)** | 8,770 L (-26.2%) |
| **Unserved Critical Energy** | 0.0 kWh | 0.0 kWh | **0.0 kWh (Safety Guarantee)** | 0.0 kWh |
| **Genset Off-Hours (Winter)** | 0 h | ~260 h | **291 h / month** | 338 h / month |
| **CO2 Emissions Avoided** | 0.0 t | 16.6 t | **18.2 tonnes** | 19.9 tonnes |
| **MILP Solve Duration** | N/A | < 1 ms | **< 0.9s average (232 solves, 0 failures)** | < 0.9s |

---

## 🎯 Direct Response to Technical Review & Judge Critiques

To move from an initial pitch deck score of 43/60 to top-tier technical credibility (49–51+/60), this repository incorporates four targeted engineering enhancements:

### 1. 🔬 AI ML vs Persistence Ablation Study
> **Critique:** *"Thin justification for why AI specifically helps versus simpler rules. Need an ablation study to isolate AI's contribution: AI vs Rule-based vs Persistence."*

- **Controlled 4-Way Experiment:** Decouples the optimizer from the forecaster on identical 7-day data:
  1. `Persistence + Rule`: Naive day-ahead persistence ($y_{t+24} = y_t$) with rule controller $\rightarrow$ **1,267.4 L**, 21 starts.
  2. `Persistence + HiGHS MILP`: Naive persistence with MILP optimizer $\rightarrow$ **396.2 L**, 5 starts.
  3. `POLAR EMS (AI ML + HiGHS)`: HistGradientBoosting ML + MILP optimizer $\rightarrow$ **325.9 L**, 3 starts.
  4. `Perfect Oracle (Bound)`: Zero-error ground truth + MILP optimizer $\rightarrow$ **137.0 L**, 3 starts.
- **Empirical AI Attribution:** The ML forecaster saves an additional **70.3 Litres (17.7%)** in 7 days solely due to forecast accuracy, reduces load MAPE from **14.5% to 6.2%**, and eliminates 2 thermal shock generator starts.
- **CLI Runner:** `python run_ablation_study.py 7`

---

### 2. 🔥 Combined Heat & Power (CHP) & Auxiliary Hydronic Loop Engine
> **Critique:** *"Diesel generators produce waste heat for habitat heating and snow melting. When gensets are switched off in renewable mode, what heats the station? Needs thermal balance, heat recovery, and boiler fuel modeling."*

- **Physical Formulation:**
  - Station Thermal Demand: $Q_{\text{demand}} = UA \cdot (T_{\text{indoor}} - T_{\text{ambient}}) + Q_{\text{snowmelt}}$  
    ($T_{\text{indoor}} = +18^\circ\text{C}$, $UA = 1.25\text{ kW/}^\circ\text{C}$, $Q_{\text{snowmelt}} = 8.0\text{ kW}_{\text{th}}$ continuous potable water melt).
  - Genset Waste Heat Recovery: $Q_{\text{recovered}} = P_{\text{genset}} \times 1.35\text{ kW}_{\text{th}}/\text{kW}_{\text{elec}}$ (jacket water heat exchanger + exhaust economizer).
  - Auxiliary Oil-Fired Boiler: Fired during renewable diesel-off intervals when $Q_{\text{recovered}} < Q_{\text{demand}}$:
    $$F_{\text{boiler}} = \frac{Q_{\text{deficit}}}{\text{LHV}_{\text{diesel}} \cdot \eta_{\text{boiler}}} \approx 0.118\text{ L / kWh}_{\text{th}}$$
- **Net Fuel Balance Defense:** Even at $-35^\circ\text{C}$ in winter with gensets OFF, the auxiliary boiler burns **~8.8 L/h** of heating fuel, while turning off the genset saves **~20.0 L/h** of electrical diesel. **Net station fuel savings remain > 25%** even with full auxiliary boiler fuel accounted for!
- **CLI Runner:** `python run_thermal_simulation.py`

---

### 3. ❄️ Real Antarctic Station Weather Backtest
> **Critique:** *"The weakest part of almost every SIH idea is purely synthetic data. A real-weather backtest answers 'is this real?' with evidence."*

- **Meteorological Calibration:** Calibrated to real automatic weather stations (AWS) and ERA5 global reanalysis:
  - **Bharati Station** ($69^\circ 24'\text{S}, 76^\circ 11'\text{E}$, Larsemann Hills): Katabatic blizzards exceeding $36\text{ m/s}$ ($130\text{ km/h}$), $-44.9^\circ\text{C}$ winter lows, and $116\text{ hours}$ of active $25\text{ m/s}$ turbine cut-outs.
  - **Maitri Station** ($70^\circ 45'\text{S}, 11^\circ 44'\text{E}$, Schirmacher Oasis): Inland ice edge with $-38^\circ\text{C}$ winter plateaus.
  - **Himadri Station** ($78^\circ 55'\text{N}, 11^\circ 56'\text{E}$, Ny-Ålesund, Svalbard, Arctic).
- **Resilience Proof:** 100% life-support reliability ($0.0\text{ kWh}$ unserved) across all 720 hours of polar storm conditions, automatic turbine feathering at $25\text{ m/s}$, and dynamic battery cold derating.
- **CLI Runner:** `python run_real_weather_backtest.py Bharati`

---

### 4. 💰 Antarctic Fuel Logistics Economics & Days-of-Autonomy
> **Critique:** *"Missing economic / annualized analysis (annual diesel cost savings, logistics cost per liter at Antarctic stations ~₹250-400/L or $3-5/L, carbon payback, ROI, days of autonomy)."*

- **Delivered Polar Fuel Cost Breakdown:**
  - Base bulk polar diesel (DMA / Jet A-1 cold-flow): **₹85.0 / L**
  - Chartered icebreaker voyage (*MV Vasiliy Golovnin* from Cape Town): **₹160.0 / L**
  - Fast-ice hose pumping & PistenBully tracked sled traverse: **₹75.0 / L**
  - Environmental protocol compliance & sampling: **₹15.0 / L**
  - **Total Landed Fuel Cost in Antarctica:** **₹335 / Litre ($4.02 / L)**.
- **Financial Return & Payback:**
  - Annual Diesel Saved: **41,600 Litres / station / year**.
  - Annual Cost Savings: **₹1.39 Crore / year ($167,000 / year)**.
  - Edge Hardware CAPEX (Rugged DIN-rail industrial PC + Modbus gateways): **₹3.50 Lakh ($4,200)**.
  - **Capital Payback Period:** **9.2 Days (< 1 month)**!
  - 5-Year Life Cycle Net Benefit: **₹6.93 Crores ($835,000)** + **557 tonnes CO2 avoided**.
- **Days-of-Autonomy Engine:** Tracks bulk fuel storage (60,000 L capacity), dynamic daily burn rates, and alerts operators if autonomy approaches the 15-day emergency blizzard traverse cutoff margin.

---

## 🛠️ Complete Technical Stack

| Domain | Technology / Library | Purpose & Implementation |
| :--- | :--- | :--- |
| **Runtime** | Python 3.12 (Venv) | Isolated, cross-platform virtual environment |
| **MILP Optimizer** | `scipy.optimize.milp` (HiGHS backend) | Solves 24h rolling-horizon unit commitment & dispatch in < 0.9s |
| **Machine Learning** | `scikit-learn` (`HistGradientBoostingRegressor`) | Multi-feature load & weather forecaster with lag-24h features |
| **Physical Modeling** | NumPy & Python Math | Power curves, 25 m/s blizzard cut-out, cold battery derating |
| **Thermal / CHP Engine** | Pure Python Module (`polar_ems/simulation/thermal_model.py`) | Jacket water heat recovery, station heating balance, boiler fuel |
| **Real Weather Engine** | Pure Python Module (`polar_ems/simulation/real_weather.py`) | Bharati & Maitri station AWS / ERA5 meteorological backtest |
| **Logistics Engine** | Pure Python Module (`polar_ems/logistics/economics.py`) | ₹335/L delivered cost, payback calculator, days-of-autonomy |
| **Edge Backend** | FastAPI, Uvicorn, AsyncIO, WebSockets | Asynchronous offline edge server running locally on station PC |
| **Edge Storage** | SQLite 3 with Write-Ahead Logging (WAL) | Crash-resilient local time-series and operator audit log |
| **Telemetry Ingestion** | Modbus TCP, OPC-UA, MQTT Simulator | Gap-filling, range validation, and anemometer rime-ice detection |
| **Operator Dashboard** | HTML5, CSS3, Pure SVG Visualization | Multi-tab SCADA dashboard replicating Slide 2 & 3 prototype view |

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

Where $F_{0,i} = 4.5\text{ L/h}$, $k_i = 0.235\text{ L/kWh}$, $C_{start} = 3.5\text{ L-eq}$, $C_{deg} = 0.015$.

### 3. Key Polar Physical Constraints
- **Power Balance:**  
  $$\sum_{i=1}^2 P_{g,i}(t) + P_{wind}(t) + P_{pv}(t) + P_{dis}(t) - P_{chg}(t) - P_{def}(t) - P_{curt}(t) + P_{uns}(t) = P_{crit}(t)$$
- **Minimum Genset Loading:** $P_{g,i}(t) \ge 24 \cdot u_i(t)$ (30% load prevents wet stacking / carbon soot)
- **Minimum Run-Time:** $\sum_{\tau=t}^{\min(t+2, T-1)} u_i(\tau) \ge 3 \cdot v_i(t)$ (3 hours minimum run to avoid thermal shock)
- **Cold Battery Derating:** $C_{eff}(T) = C_{nom} \cdot \max(0.60, 1.0 - 0.008 \cdot \max(0, 15 - T_{ambient}))$
- **Dynamic Blizzard Reserve:** $R_{req}(t) = 0.12 P_{crit}(t) + 0.25 P_{pv}(t) + \alpha_{wind}(v_{wind}) P_{wind}(t)$, where $\alpha_{wind} \in [0.30, 0.70]$
- **Blizzard Safety Cut-Out:** $P_{wind}(v) = 0\text{ kW}$ when $v_{wind} \ge 25\text{ m/s}$ (turbines lock & feather)

---

## 🚀 Quick Start Guide

### 1. Launch the Edge Server & SCADA Dashboard
Starts the local edge service and serves the interactive dashboard:
```powershell
& 'D:\Polar EMS\venv\Scripts\python.exe' -u start_edge_server.py
```
Open your browser to:
- **Operator SCADA Dashboard:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive OpenAPI Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 2. Reproduce the Slide 5 Benchmarks
```powershell
& 'D:\Polar EMS\venv\Scripts\python.exe' run_benchmark_slides.py
```

### 3. Run the AI ML vs Persistence Ablation Study
```powershell
& 'D:\Polar EMS\venv\Scripts\python.exe' run_ablation_study.py 7
```

### 4. Run the Combined Heat & Power (CHP) Thermal Simulation
```powershell
& 'D:\Polar EMS\venv\Scripts\python.exe' run_thermal_simulation.py
```

### 5. Run the Real Antarctic Weather Backtest (Bharati Station)
```powershell
& 'D:\Polar EMS\venv\Scripts\python.exe' run_real_weather_backtest.py Bharati
```

---

## 📂 Project Directory Structure

```
D:\Polar EMS\
├── docs/                            # Deep Technical Documentation & Architecture
│   ├── assets/
│   │   └── polar-ems-flow.svg       # End-to-end pipeline flow diagram
│   ├── ARCHITECTURE.md              # 6-stage pipeline, component map & runtime state
│   └── EVALUATION.md                # Benchmarks, deck replication & failure modes
├── polar_ems/                       # Core Polar EMS Engine Package
│   ├── api/                         # FastAPI Edge REST & WebSocket Routes
│   │   ├── main.py                  # App entrypoint and static file mounting
│   │   └── routes.py                # Status, dispatch, ablation, thermal, economics APIs
│   ├── forecasting/                 # Machine Learning & Ablation Engine
│   │   ├── forecaster.py            # HistGradientBoosting load & renewable forecaster
│   │   └── ablation.py              # AI ML vs Persistence 4-way ablation engine
│   ├── logistics/                   # Logistics & Economics Package
│   │   └── economics.py             # Polar fuel economics, payback & days of autonomy
│   ├── models/                      # Pydantic schemas and data contracts
│   ├── optimizer/                   # SciPy HiGHS MILP Rolling Optimizer
│   │   └── milp_solver.py           # Unit commitment, cold derating, blizzard reserves
│   ├── safety/                      # Supervisory Safety & Fallback Layer
│   │   ├── fallback_controller.py   # Deterministic rule-based backup controller
│   │   └── sensor_validation.py     # Modbus/OPC-UA telemetry validator & rime-ice detector
│   ├── simulation/                  # Physics Engine & Real Weather
│   │   ├── microgrid.py             # Cold battery derating, genset curve, 25 m/s cut-out
│   │   ├── synthetic_data.py        # 60-day Slide 5 summer & polar-night benchmark generator
│   │   ├── real_weather.py          # Bharati & Maitri real AWS / ERA5 meteorological backtest
│   │   └── thermal_model.py         # CHP waste heat recovery & auxiliary boiler engine
│   ├── storage/                     # Local Edge Persistence
│   │   └── db.py                    # SQLite with WAL mode & operator audit logs
│   └── config.py                    # Microgrid asset sizing & operating constraints
├── static/                          # Operator SCADA Dashboard (Frontend)
│   ├── index.html                   # Multi-tab SCADA interface (Slide 2 Box 4)
│   ├── style.css                    # Polar industrial dark mode styling
│   └── app.js                       # SVG rendering, multi-tab switching, live telemetry
├── run_benchmark_slides.py          # Slide 5 benchmark reproduction runner
├── run_ablation_study.py            # 4-way ablation comparison runner
├── run_thermal_simulation.py        # Combined Heat & Power hydronic loop runner
├── run_real_weather_backtest.py     # Bharati/Maitri real weather backtest runner
├── run_simulation.py                # 60-day end-to-end simulation runner
└── start_edge_server.py             # Uvicorn server launcher
```

---

## 📜 Compliance with Antarctic Environmental Protocols

POLAR EMS operates in strict accordance with:
- **The Antarctic Treaty (1959)** & the **Protocol on Environmental Protection to the Antarctic Treaty (Madrid Protocol, 1991)**: Minimizes fossil fuel combustion, reduces soot/black carbon deposition on polar glaciers, and mitigates maritime fuel transfer spill hazards.
- **National Centre for Polar and Ocean Research (NCPOR)** station autonomy mandates: 100% offline-first edge deployment on rugged industrial PCs with sovereign operator override capabilities.

---
**Developed by Team ByteForce (Team ID 118717) for Smart India Hackathon 2026 · Problem Statement SIH26061.**
