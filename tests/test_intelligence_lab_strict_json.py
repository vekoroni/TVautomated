from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAB_PATH = ROOT / "intelligence-lab" / "intelligence_lab.py"


def _load_lab_module():
    spec = importlib.util.spec_from_file_location("intelligence_lab_strict_json_test", LAB_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_strict_json_provider_converts_nested_nonfinite_values_to_null() -> None:
    lab = _load_lab_module()
    payload = {
        "system_date": math.nan,
        "signals": [{
            "ticker": "ABC",
            "catalyst_date": math.nan,
            "positive_infinity": math.inf,
            "negative_infinity": -math.inf,
            "valid_zero": 0.0,
        }],
    }

    encoded = lab.app.json.dumps(payload)
    decoded = json.loads(encoded)

    assert "NaN" not in encoded
    assert "Infinity" not in encoded
    assert decoded["system_date"] is None
    assert decoded["signals"][0]["catalyst_date"] is None
    assert decoded["signals"][0]["positive_infinity"] is None
    assert decoded["signals"][0]["negative_infinity"] is None
    assert decoded["signals"][0]["valid_zero"] == 0.0


def test_strict_json_provider_does_not_mutate_source_payload() -> None:
    lab = _load_lab_module()
    payload = {"value": math.nan, "nested": [math.inf]}

    lab.app.json.dumps(payload)

    assert math.isnan(payload["value"])
    assert math.isinf(payload["nested"][0])


def test_trigger_category_helper_preserves_explicit_none_without_score_fallback() -> None:
    lab = _load_lab_module()
    row = {"trigger_quality": "NONE", "trigger_score": 55.0}

    assert lab._first_trigger_signal_value(row, ["trigger_quality"]) == "NONE"
    assert lab._first_trigger_signal_value(row, ["missing_quality"]) == ""


def test_console_encoding_is_reconfigured_for_hidden_windows_processes() -> None:
    lab = _load_lab_module()

    class FakeStream:
        def __init__(self):
            self.call = None

        def reconfigure(self, **kwargs):
            self.call = kwargs

    stream = FakeStream()
    lab._configure_console_encoding(stream)

    assert stream.call == {"encoding": "utf-8", "errors": "backslashreplace"}


def test_priority_rank_csv_text_is_normalised_numerically() -> None:
    lab = _load_lab_module()

    assert lab._safe_int("10", 9999) == 10
    assert lab._safe_int("", 9999) == 9999
