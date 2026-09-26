"""The pipeline's data contract gate may not depend on pytest import order."""

from pathlib import Path
from datetime import date, timedelta
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_production_stages_load_the_real_validator_in_a_fresh_process() -> None:
    code = (
        "import sys; sys.path.insert(0, 'scripts'); "
        "from scripts import backfill_timeseries_into_packages as h, "
        "build_packages_from_discovery as b, "
        "run_vanguard_from_packages as v, "
        "avshunter_superbrain_layer as s; "
        "from scripts.data_contract_validator import DataContractValidator as D; "
        "assert all(m.DCV is D and m._DCV_AVAILABLE "
        "for m in (h, b, v, s))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_package_build_repairs_prices_but_does_not_invent_regime() -> None:
    from scripts.build_packages_from_discovery import enforce_data_contract

    bars = [
        {
            "date": (date.today() - timedelta(days=59 - index)).isoformat(),
            "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5,
            "volume": 1000,
        }
        for index in range(60)
    ]
    package = enforce_data_contract({"timeseries": {"ohlcv_daily": bars}})
    assert package["ohlcv"] is bars
    assert package["data_contract"]["build_repair"] == "REPAIRED_FROM_TIMESERIES"
    assert package["data_contract"]["dcv_valid"] is False
    assert package["data_contract"]["dcv_reason"] == "MISSING_REGIME"
