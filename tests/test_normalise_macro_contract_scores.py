from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.normalise_macro_contract import normalise  # noqa: E402


def test_normaliser_preserves_authoritative_scores(tmp_path: Path) -> None:
    path = tmp_path / "macro.json"
    expected = {
        "net_liquidity_score": 0.58,
        "vix_regime_score": 0.82,
        "gex_regime_score": 0.75,
        "macro_momentum_score": 0.48,
    }
    payload = {
        **expected,
        "liquidity_pulse": "STABLE",
        "vix_spot": 14.899,
        "macro_conviction": 0.63,
        "as_of_utc": "2026-08-09T19:00:00+00:00",
        "extras": {"gex": {"regime": "POSITIVE"}},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert normalise(path) is True
    result = json.loads(path.read_text(encoding="utf-8"))
    for field, value in expected.items():
        assert result[field] == value


def test_missing_gex_is_not_imputed_neutral(tmp_path: Path) -> None:
    path = tmp_path / "macro.json"
    path.write_text(json.dumps({
        "net_liquidity_score": 0.5,
        "vix_regime_score": 0.8,
        "macro_momentum_score": 0.5,
        "as_of_utc": "2026-08-09T19:00:00+00:00",
    }), encoding="utf-8")

    assert normalise(path) is True
    result = json.loads(path.read_text(encoding="utf-8"))
    assert "gex_regime_score" not in result
