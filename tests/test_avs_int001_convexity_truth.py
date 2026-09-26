"""Unqualified option convexity is not a trader-facing measured value."""

import importlib.util
from pathlib import Path

from contracts.lab_control import opportunity_book_row


ROOT = Path(__file__).resolve().parents[1]


def _signal(**overrides):
    value = {
        "ticker": "TEST", "pipeline_mode": "EOD", "direction": "CALL",
        "signal_price": 100.0, "target_price": 110.0,
        "invalidation_price": 90.0, "invalidation_state": "AVAILABLE",
        "convexity_score": 3.0, "convexity_campaign": "CORE_CAMPAIGN",
    }
    value.update(overrides)
    return value


def test_unqualified_convexity_number_is_not_published_as_available():
    row = opportunity_book_row(_signal(), "20260925_061649", 1)
    assert row["convexity_data_state"] == "UNVERIFIED_SOURCE"
    assert row["convexity_score"] in (None, "")
    assert row["convexity_score_source"] in (None, "")


def test_source_qualified_score_keeps_its_scale_and_owner():
    row = opportunity_book_row(_signal(
        convexity_score=5.0,
        convexity_score_max=8,
        convexity_score_source="SUPERBRAIN_8_CONDITION",
    ), "20260925_061649", 1)
    assert row["convexity_data_state"] == "AVAILABLE"
    assert row["convexity_score"] == 5.0
    assert row["convexity_score_max"] == 8
    assert row["convexity_score_source"] == "SUPERBRAIN_8_CONDITION"


def test_verdict_encoded_score_cannot_be_relabelled_as_convexity():
    row = opportunity_book_row(_signal(
        convexity_score_source="CAMPAIGN_VERDICT", convexity_score_max=8,
    ), "20260925_061649", 1)
    assert row["convexity_data_state"] == "UNVERIFIED_SOURCE"
    assert row["convexity_score"] in (None, "")


def test_lab_display_does_not_reconstruct_convexity_from_unqualified_fallback():
    page = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    summary = page.split("function getConvexitySummary(s)", 1)[1].split("function getSelectedQuoteAskBreakeven", 1)[0]
    assert "s.sb_conv_score" not in summary
    assert "UNAVAILABLE · SOURCE NOT VERIFIED" in summary
    assert "['Conv_Score',      s => getConvexitySummary(s)]" in page


def test_legacy_numeric_match_does_not_create_an_options_calculation_source():
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("lab_int001_convexity_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    book = {"ticker": "TEST", "contract_symbol": "TEST990119C00100000", "convexity_score": 3.0}
    options = {"ticker": "TEST", "recommended_contract": book["contract_symbol"], "convexity_score": 3.0}
    module._project_convexity_basis(book, options)
    assert not book.get("convexity_score_source")
    assert not book.get("convexity_score_max")


def test_read_model_rejects_a_verdict_label_disguised_as_a_score_source():
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("lab_int001_convexity_source_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    book = {"convexity_score": 3.0, "convexity_score_max": 8,
            "convexity_score_source": "CAMPAIGN_VERDICT"}
    module._project_convexity_basis(book, {})
    assert book["convexity_score"] is None
    assert book["convexity_data_state"] == "UNVERIFIED_SOURCE"
