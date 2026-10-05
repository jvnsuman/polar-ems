"""Run with: python -m pytest tests -q   (or: python tests/test_executor.py)"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from polar_ems.config import DEFAULT_STATION_CONFIG
from polar_ems.simulation.executor import execute_hour
from polar_ems.simulation.microgrid import PolarMicrogridSimulator

SIM = PolarMicrogridSimulator(DEFAULT_STATION_CONFIG)


def _case(rng):
    on = [rng.random() < 0.5, rng.random() < 0.3]
    return dict(
        planned_g_kw=[rng.uniform(24, 80) if on[0] else 0.0, rng.uniform(24, 80) if on[1] else 0.0],
        planned_g_on=on, planned_chg_kw=rng.uniform(0, 60), planned_dis_kw=rng.uniform(0, 60),
        planned_def_kw=rng.uniform(0, 25), critical_kw=rng.uniform(30, 160), wind_kw=rng.uniform(0, 100),
        pv_kw=rng.uniform(0, 80), soc=rng.uniform(0.2, 0.95), ambient_temp_c=rng.uniform(-40, 5),
        prev_g_on=[True, False],
    )


def test_energy_balance_and_limits():
    rng = random.Random(1)
    for _ in range(5000):
        kw = _case(rng)
        r = execute_hour(SIM, **kw)
        supply = sum(r.g_kw) + (kw["wind_kw"] + kw["pv_kw"] - r.curtailed_kw) + r.dis_kw
        demand = kw["critical_kw"] + r.deferrable_kw + r.chg_kw - r.unserved_kw
        assert abs(supply - demand) < 1e-9
        assert 0.2 - 1e-9 <= r.soc <= 0.95 + 1e-9
        for i in (0, 1):
            assert (not r.g_on[i]) or 24.0 - 1e-9 <= r.g_kw[i] <= 80.0 + 1e-9
        assert r.unserved_kw >= 0 and r.curtailed_kw >= 0


def test_unserved_only_after_every_other_source_is_exhausted():
    kw = dict(planned_g_kw=[0.0, 0.0], planned_g_on=[False, False], planned_chg_kw=0.0, planned_dis_kw=0.0,
              planned_def_kw=0.0, critical_kw=400.0, wind_kw=0.0, pv_kw=0.0, soc=0.2,
              ambient_temp_c=-30.0, prev_g_on=[False, False])
    r = execute_hour(SIM, **kw)
    assert r.g_on == [True, True] and r.g_kw == [80.0, 80.0]
    assert abs(r.unserved_kw - 240.0) < 1e-9


if __name__ == "__main__":
    test_energy_balance_and_limits()
    test_unserved_only_after_every_other_source_is_exhausted()
    print("executor tests passed")
