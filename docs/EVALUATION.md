# Evaluation: how good is it, and how do we know?

Reproduce every number here:

```
python run_simulation.py          # about 4 min; results/benchmark_results.json
python run_ablation_study.py 7    # results/ablation_results.json
python -m pytest tests -q         # executor energy balance and limits
```

## What is measured

| Metric | How |
| :-- | :-- |
| Diesel burned | Litres from the fuel curve (4.5 L/h + 0.235 L/kWh per running genset), both gensets counted |
| Saving | Versus the always-on baseline and versus the rule-based controller |
| Unserved energy | Realized: after every planned hour is re-balanced against actual load, wind and PV (executor.py), or the fallback controller's shortfall |
| Deferrable energy | Delivered versus the 100 kWh/day requirement; shed energy is reported |
| Genset starts | Off-to-on transitions of either genset, including starts the plan did not ask for |
| CO2 avoided | (baseline litres minus POLAR EMS litres) x 2.68 kg/L |
| Load MAPE | Executed first 6 h of each plan, whole month |

Controllers: **always-on** (genset 1 every hour at clamp(load + 4.17, 24, 80) kW, wind and PV unused; it cannot meet peaks above 80 kW, 1,277 kWh unserved over the 60 days, so it is a weak baseline); **rule** (`RuleBasedFallbackController`,
reactive); **POLAR EMS** (forecast, 24 h MILP, replan every 6 h or on a blizzard flag, executed through executor.py).

## The data, and its limits (read before quoting a number)

- All data is synthetic (polar_ems/simulation/synthetic_data.py); no station logs, ERA5, BSRN or AWS data were used.
- No weather forecast model exists. 'true' gives the optimizer the true weather (upper bound); 'persistence' gives it yesterday's weather (naive bound).
- Plans are executed against actual load, wind and PV by a simple re-balancing policy (executor.py), not an optimum; unplanned genset starts are counted.
- The always-on baseline never uses wind or PV, so part of every saving vs always-on is simply using renewables. The rule controller is a fallback, not a tuned station controller.
- The load model trains on the first 96 h of the series it is then scored on.
- Single synthetic series per season and no confidence intervals; run-to-run solver differences are about 0.1%.

## Results

Weather given to the optimizer = **true** weather (upper bound):

| Season | Always-on (L) | Rule (L) | POLAR EMS (L) | vs always-on | vs rule | Unserved (kWh) | Deferrable shed (kWh) | Starts (rule) | Unplanned starts | Genset-off h (rule) | Load MAPE | Solves / mean time |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| summer | 12,457 | 6,605 | 2,421 | -80.6% | -63.3% | 0.0 | 0 | 29 (94) | 2 | 592 (132) | 5.0% | 120 / 573 ms |
| polar night | 15,836 | 10,563 | 9,560 | -39.6% | -9.5% | 0.0 | 0 | 58 (56) | 81 | 213 (92) | 5.1% | 123 / 350 ms |

Weather given to the optimizer = **persistence**, yesterday at the same hour (naive bound):

| Season | Always-on (L) | Rule (L) | POLAR EMS (L) | vs always-on | vs rule | Unserved (kWh) | Deferrable shed (kWh) | Starts (rule) | Unplanned starts | Genset-off h (rule) | Load MAPE | Solves / mean time |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| summer | 12,457 | 6,605 | 3,748 | -69.9% | -43.2% | 0.0 | 0 | 77 (94) | 115 | 492 (132) | 5.2% | 120 / 580 ms |
| polar night | 15,836 | 10,563 | 11,078 | -30.0% | +4.9% | 0.0 | 0 | 98 (56) | 216 | 110 (92) | 8.2% | 123 / 359 ms |

Combined 60 days: always-on 28,292 L, rule 17,168 L, POLAR EMS 11,981 L (true weather, -30.2% vs rule)
or 14,827 L (persistence weather, -13.6% vs rule). The polar-night month is the hard case: the optimizer needs a good weather forecast to beat the rule controller there.

## Forecast ablation (7-day windows)

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

Reading it: 4 vs 3 isolates the ML load model with weather held equal; 3 vs 2 is the value of knowing the weather (not ML skill: no weather forecast model exists here);
4 vs 5 is the fuel cost of the remaining load-forecast error; 2 vs 1 is the optimizer's contribution. The ML load model is not shown to help, and in the polar-night week it costs fuel.
One window per season, no confidence intervals.

## History: earlier claims that were withdrawn

An earlier version of this repository and of the idea deck quoted results the code did not produce: -29.7% vs always-on and -3.6% vs rules (the code gave
-61.0% and -35.7% with plans executed as written and true weather), 18.2 t CO2, "0 kWh unserved" taken from plan slack (3,668.6 kWh in an open-loop replay), wind NMAE 12-14%, an ablation whose
fuel counted genset 1 only and whose load MAPE figures were fallback constants, a "benchmark reproduction" script that printed the deck's numbers, and a "real weather backtest" that generated
data with a random number generator. They were removed; the deck now quotes the tables above.

## Known failure modes (what still goes wrong)

- **No weather forecast model.** Results are bracketed by true and persistence weather; the real value sits between them and is unmeasured.
- **Plans are often corrected by unplanned genset starts** (81 in polar night with true weather). Minimum run time is not carried across replans (`initial_run_hours` is unused) and is not enforced on unplanned starts.
- **The executor is a simple policy, not an optimum,** and ignores ramp rates and the daily 100 kWh deferrable requirement (shed energy is reported instead).
- **The ML load model is trained on the first 96 h of the series it is scored on,** and is not shown to beat persistence.
- **No terminal SoC constraint:** each plan drains the battery by its end.
- **Deferrable load** needs 100 kWh in every 24 h window and can be pushed to the end of each window.
- **Reserve ignores stored energy:** it counts full battery discharge power whatever the SoC.
- **Cold derating uses the horizon-average temperature,** which hides overnight lows.
- **Genset start wear** is only a fixed penalty; cold-start wear is not modelled.
- **Heating is not in the optimizer;** fuel totals are electrical genset fuel only.
- **Large curtailment in summer** (10,896 kWh with true weather): synthetic wind and PV are large relative to load.
- **Tests:** only the executor has tests; the optimizer, forecaster and API are untested.

## Ethics note

These metrics measure fuel and reserve behaviour in simulation. They say nothing about safety on a real station. No claim of life-support protection should be made until it is validated on station data with a shadow-mode pilot.
