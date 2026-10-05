# POLAR EMS: advisory energy management for polar station microgrids

Smart India Hackathon 2026 | Problem statement SIH26061 | Team ByteForce (Team ID 118717)

> **Status: research prototype on synthetic data.** Nothing here has been validated against a real station, real
> weather or real hardware. Every number below comes from `python run_simulation.py` and
> `python run_ablation_study.py`, which you can re-run. Read [docs/EVALUATION.md](docs/EVALUATION.md) before quoting a result.

POLAR EMS plans diesel genset, battery and deferrable-load schedules for a station microgrid (2 x 80 kW gensets,
300 kWh battery, 100 kW wind, 80 kWp PV, 100 kWh/day flexible load). It forecasts load, wind and PV, solves a 24 h
mixed-integer dispatch every 6 h with SciPy/HiGHS, and keeps a rule-based fallback controller. It is advisory first:
nothing is sent to station controllers.

Docs: [Architecture](docs/ARCHITECTURE.md) | [Evaluation, limits and known failure modes](docs/EVALUATION.md) | [Pipeline diagram](docs/assets/polar-ems-flow.svg)

## Results (60 synthetic days: 30 summer + 30 polar night)

Plans are executed hour by hour against the **actual** load, wind and PV by a simple re-balancing policy
([executor.py](polar_ems/simulation/executor.py)), so forecast error costs fuel or unserved energy. The repository has no
weather forecast model, so the optimizer is run with two weather inputs that bracket a real forecast.

| | Always-on | Rule-based | POLAR EMS, true weather (upper bound) | POLAR EMS, persistence weather (naive bound) |
| :-- | --: | --: | --: | --: |
| Summer, 30 days (L diesel) | 12,457 | 6,605 | 2,421 | 3,748 |
| Polar night, 30 days (L) | 15,836 | 10,563 | 9,560 | 11,078 |
| Combined 60 days (L) | 28,292 | 17,168 | 11,981 | 14,827 |
| Combined vs always-on | n/a | -39.3% | -57.7% | -47.6% |
| Combined vs rule-based | n/a | n/a | -30.2% | -13.6% |
| Summer vs rule-based | n/a | n/a | -63.3% | -43.2% |
| Polar night vs rule-based | n/a | n/a | -9.5% | +4.9% |
| CO2 avoided vs always-on (t) | n/a | 29.8 | 43.7 | 36.1 |
| Unserved energy, realized (kWh) | 1,277 (cannot exceed 80 kW) | 0.0 | 0.0 | 0.0 |
| Genset starts, 60 days | 1 | 150 | 87 | 175 |
| MILP solves (mean solve time) | n/a | n/a | 243 (461 ms) | 243 (469 ms) |

How to read this:

- **The weather forecast is the main dependency.** With true weather POLAR EMS uses 30.2% less diesel than the rule controller over the 60 days;
  with naive persistence weather it uses 13.6% less, and in polar night 4.9% *more* than the rule controller.
  A real numerical forecast would land between these bounds. Measuring where is the main open task.
- **Most of the saving versus always-on is renewable use, and always-on is a weak baseline.** It never uses wind or PV, and it runs a single
  genset, so it cannot meet load peaks above 80 kW (1,277 kWh unserved, shown in the table). The rule controller is a fallback, not a tuned station controller.
- **Unserved energy is realized, not planned,** and is zero for POLAR EMS in all runs here; any shortfall after re-balancing would show up in that row.
  The executor often starts a genset the plan did not (81 unplanned starts in polar night with true weather, 216 with persistence weather),
  which means the plans under-provide generation relative to actual conditions.
- Synthetic data, one series per season, no confidence intervals. Repeat runs differ by about 0.1%.

## Forecast ablation (7-day windows, same controllers on identical data)

Summer:

| Configuration | Fuel (L) | Starts | Unserved (kWh) | Load MAPE |
| :-- | --: | --: | --: | --: |
| 1. Rule controller (no forecast) | 1,267 | 21 | 0.0 | n/a |
| 2. MILP, persistence forecasts | 603 | 13 | 0.0 | 5.49% |
| 3. MILP, persistence load, true weather | 378 | 5 | 0.0 | 5.49% |
| 4. MILP, ML load, true weather | 368 | 3 | 0.0 | 8.14% |
| 5. MILP, perfect information | 360 | 5 | 0.0 | 0.0% |

Optimizer vs rule controller (2 vs 1): 664 L. Knowing the weather vs persistence (3 vs 2): 225 L. ML load model vs persistence load (4 vs 3): 10 L (2.62%). Remaining gap to perfect information (4 vs 5): 8 L.

Polar night:

| Configuration | Fuel (L) | Starts | Unserved (kWh) | Load MAPE |
| :-- | --: | --: | --: | --: |
| 1. Rule controller (no forecast) | 1,955 | 14 | 0.0 | n/a |
| 2. MILP, persistence forecasts | 1,878 | 22 | 0.0 | 8.19% |
| 3. MILP, persistence load, true weather | 1,574 | 11 | 0.0 | 8.19% |
| 4. MILP, ML load, true weather | 1,751 | 17 | 0.0 | 8.1% |
| 5. MILP, perfect information | 1,488 | 6 | 0.0 | 0.0% |

Optimizer vs rule controller (2 vs 1): 77 L. Knowing the weather vs persistence (3 vs 2): 304 L. ML load model vs persistence load (4 vs 3): -178 L (-11.28%). Remaining gap to perfect information (4 vs 5): 263 L.

What this does and does not show: knowing the weather is worth far more than anything else here; the ML load model is
not shown to help (a small gain in the summer week, a loss of about 11% in the polar-night week); and
there is no weather forecast model in the repository, so configurations 3 to 5 are given true weather.

## Reproduce

```
pip install -r requirements.txt
python run_simulation.py               # about 4 min; writes results/benchmark_results.json
python run_ablation_study.py 7         # writes results/ablation_results.json
python run_thermal_simulation.py       # stand-alone heat and boiler-fuel snapshot
python run_station_weather_scenario.py Bharati   # describes a synthetic weather scenario
python -m pytest tests -q              # executor tests
python start_edge_server.py            # dashboard http://127.0.0.1:8000 , API docs at /docs
```

The dashboard and the `/api/benchmarks` and `/api/dispatch/week` endpoints read `results/benchmark_results.json`; if it is
missing they say so instead of showing numbers. `/api/dispatch/week?mode=true|persistence` picks the weather input
(default `persistence`, the conservative one).

## What is and is not in this repository

| Part | Status |
| :-- | :-- |
| MILP dispatch (HiGHS), cold-derated battery, 25 m/s cut-out, reserve | Built, runs |
| Gradient-boosting load forecast (scikit-learn) | Built; benefit not demonstrated |
| Wind and PV forecast | Power-curve and PV model applied to a weather input; no weather forecast model |
| Real-time execution against actual conditions | Built (simple policy) |
| Rule-based fallback controller | Built |
| FastAPI edge service, SQLite audit log, static dashboard | Built; replays a fixed day, no telemetry ingestion |
| Heat recovery and boiler fuel | Stand-alone calculation only; not inside the optimizer |
| Fuel logistics economics | Illustrative assumptions only (see below) |
| Modbus / OPC-UA / MQTT ingestion, hardware control, PostgreSQL/TimescaleDB, Docker | Not built |
| Real weather or station-log backtest | Not done. `station_weather.py` generates synthetic, climate-calibrated series |
| Feedback loop (forecast-versus-actual retraining) | Not built |

**Economics are illustrative.** The delivered fuel cost (335 INR/L) and its breakdown, the hardware cost, the tank size and
the reserve days are unsourced constants, and annual volumes are the two benchmark months extrapolated by 365/60.
`/api/economics/metrics` returns `"illustrative": true` and shows savings against both always-on and the rule controller.
Replace the constants with NCPOR figures before quoting any rupee value.

**Thermal model is stand-alone.** `run_thermal_simulation.py` uses assumed coefficients (UA 1.25 kW/C, 1.35 kW_th recovered
per kW_el, 84% boiler efficiency). The dispatch optimizer does not include heating, so fuel totals above are electrical genset fuel only.

## Mathematical formulation

### Decision variables ($t \in \{0, \dots, T-1\}$)
- $u_i(t) \in \{0, 1\}$: Binary status of genset $i \in \{1, 2\}$ (1 = ON, 0 = OFF)
- $v_i(t) \in \{0, 1\}$: Startup detection ($v_i(t) \ge u_i(t) - u_i(t-1)$)
- $P_{g,i}(t) \in [0, 80]$: Active power output of genset $i$ (kW)
- $P_{chg}(t), P_{dis}(t) \in [0, 100]$: Battery charge/discharge power (kW)
- $SoC(t) \in [0.20, 0.95]$: Battery state of charge
- $P_{def}(t) \in [0, 25]$: Flexible load allocated to snow-melter/water-maker (kW)
- $P_{curt}(t), P_{uns}(t) \ge 0$: Curtailment and unserved slack variables

### Objective
$$\min \sum_{t=0}^{T-1} \left[ \sum_{i=1}^2 \left( F_{0,i} u_i(t) + k_i P_{g,i}(t) + C_{start} v_i(t) \right) + C_{deg} (P_{chg}(t) + P_{dis}(t)) + 10000 P_{uns}(t) + 0.02 P_{curt}(t) \right]$$

Where $F_{0,i} = 4.5\text{ L/h}$, $k_i = 0.235\text{ L/kWh}$, $C_{start} = 3.5\text{ L-eq}$, $C_{deg} = 0.015$.

### Key constraints
- **Power Balance:**  
  $$\sum_{i=1}^2 P_{g,i}(t) + P_{wind}(t) + P_{pv}(t) + P_{dis}(t) - P_{chg}(t) - P_{def}(t) - P_{curt}(t) + P_{uns}(t) = P_{crit}(t)$$
- **Minimum Genset Loading:** $P_{g,i}(t) \ge 24 \cdot u_i(t)$ (30% load prevents wet stacking / carbon soot)
- **Minimum Run-Time:** $\sum_{\tau=t}^{\min(t+2, T-1)} u_i(\tau) \ge 3 \cdot v_i(t)$ (3 hours minimum run to avoid thermal shock)
- **Cold Battery Derating:** $C_{eff}(T) = C_{nom} \cdot \max(0.60, 1.0 - 0.008 \cdot \max(0, 15 - T_{ambient}))$
- **Dynamic Blizzard Reserve:** $R_{req}(t) = 0.12 P_{crit}(t) + 0.25 P_{pv}(t) + \alpha_{wind}(v_{wind}) P_{wind}(t)$, where $\alpha_{wind} \in [0.30, 0.70]$
- **Blizzard Safety Cut-Out:** $P_{wind}(v) = 0\text{ kW}$ when $v_{wind} \ge 25\text{ m/s}$ (turbines lock & feather)

---


## Layout

```
polar_ems/
  optimizer/milp_solver.py        24 h unit commitment and dispatch (HiGHS)
  forecasting/forecaster.py       gradient-boosting load, physics wind and PV
  forecasting/ablation.py         five-controller ablation
  simulation/executor.py          executes a planned hour against actual conditions
  simulation/microgrid.py         battery derating, genset curve, wind cut-out
  simulation/synthetic_data.py    synthetic summer / polar-night series
  simulation/station_weather.py   synthetic station-climate scenarios (not observations)
  simulation/thermal_model.py     stand-alone heat and boiler calculation
  safety/                         rule-based fallback, sensor validation
  logistics/economics.py          illustrative economics, days of autonomy
  results.py                      reads results/benchmark_results.json
  api/, storage/, models/         FastAPI edge service, SQLite, schemas
static/                           dashboard (vanilla HTML/JS, hand-built SVG)
tests/test_executor.py            executor energy balance and limits
results/                          output of run_simulation.py and run_ablation_study.py
docs/                             ARCHITECTURE.md, EVALUATION.md, pipeline diagram
```

## Design intent

Advisory first, operator approval, rule-based fallback on any fault, existing PLC protection stays in place, offline-first
edge deployment, and an audit log of operator decisions. The prototype enforces none of this on real hardware. No claim of
life-support protection should be made until it is validated on station data in a shadow-mode pilot. Any link to the Antarctic
Treaty environmental protocol is a design aim, not a compliance claim.

MIT licence.
