"""Test-first contracts for AVS-SD-PI-LAB-001.

Pending xfails deliberately identify later slices; remove each marker when its
implementation lands. No provider, broker, run output, or database is touched.
"""

from __future__ import annotations

import pytest


RUN_ID = "20260922_000106"


def test_lab_discloses_unresolved_interpreter_attempts() -> None:
    from pathlib import Path

    control = (Path(__file__).resolve().parents[1] / "intelligence-lab" / "static"
               / "interpreter-desk-controls.js").read_text(encoding="utf-8")
    assert "require review. No automatic retry." in control


def test_lab_can_reopen_saved_interpreter_json_without_launching_provider() -> None:
    from pathlib import Path

    control = (Path(__file__).resolve().parents[1] / "intelligence-lab" / "static"
               / "interpreter-desk-controls.js").read_text(encoding="utf-8")
    assert "View saved reports" in control
    assert "interpreterRequest('saved_reports'" in control
    assert "interpreterRequest(path)" in control
    assert "showInterpreterReport(report)" in control


def _rows(count: int = 6) -> list[dict[str, str]]:
    return [
        {
            "run_id": RUN_ID,
            "ticker": f"T{i}",
            "final_action": "BLOCK" if i == 0 else "GO",
            "direction": "PUT" if i == 0 else "CALL",
        }
        for i in range(count)
    ]


def test_selection_preserves_human_order_and_does_not_retriage() -> None:
    from domain.interpreter_review_selection import select_review_batch

    selected = select_review_batch(_rows(), run_id=RUN_ID, tickers=["T2", "T0", "T1"])
    assert [item.ticker for item in selected] == ["T2", "T0", "T1"]
    assert [item.source_action for item in selected] == ["GO", "BLOCK", "GO"]
    assert all(item.run_id == RUN_ID for item in selected)


@pytest.mark.parametrize("tickers", [[], [f"T{i}" for i in range(6)], ["T1", "T1"]])
def test_selection_rejects_empty_oversized_or_duplicate_batch(tickers: list[str]) -> None:
    from domain.interpreter_review_selection import ReviewSelectionError, select_review_batch

    with pytest.raises(ReviewSelectionError):
        select_review_batch(_rows(), run_id=RUN_ID, tickers=tickers)


def test_selection_rejects_missing_ticker_mixed_run_and_duplicate_source_row() -> None:
    from domain.interpreter_review_selection import ReviewSelectionError, select_review_batch

    with pytest.raises(ReviewSelectionError):
        select_review_batch(_rows(), run_id=RUN_ID, tickers=["ABSENT"])
    mixed = _rows()
    mixed[1]["run_id"] = "OTHER_RUN"
    with pytest.raises(ReviewSelectionError):
        select_review_batch(mixed, run_id=RUN_ID, tickers=["T1"])
    duplicated = _rows()
    duplicated.append(dict(duplicated[1]))
    with pytest.raises(ReviewSelectionError):
        select_review_batch(duplicated, run_id=RUN_ID, tickers=["T1"])


def test_eod_bundle_retains_thesis_without_selected_option_contract() -> None:
    from contracts.interpreter_eod_review import build_eod_review_bundle

    bundle = build_eod_review_bundle(
        run_id=RUN_ID,
        source_manifest_sha256="a" * 64,
        row={"run_id": RUN_ID, "ticker": "T0", "direction": "PUT", "contract_symbol": ""},
        evidence_refs=[{"dataset_id": "EOD-PRICE-1", "sha256": "b" * 64}],
    )
    assert bundle["ticker"] == "T0"
    assert bundle["selected_contract_symbol"] is None
    assert bundle["authority"] == "ADVISORY_ONLY"
    assert bundle["source_manifest_sha256"] == "a" * 64


def test_eod_bundle_rejects_cross_run_identity() -> None:
    from contracts.interpreter_eod_review import EODReviewBundleError, build_eod_review_bundle

    with pytest.raises(EODReviewBundleError):
        build_eod_review_bundle(
            run_id=RUN_ID,
            source_manifest_sha256="a" * 64,
            row={"run_id": "OTHER_RUN", "ticker": "T0", "direction": "PUT"},
            evidence_refs=[{"dataset_id": "EOD-PRICE-1", "sha256": "b" * 64}],
        )


def test_eod_bundle_has_stable_identity_and_cannot_copy_execution_authority() -> None:
    from contracts.interpreter_eod_review import build_eod_review_bundle

    row = {
        "run_id": RUN_ID,
        "ticker": "T1",
        "direction": "CALL",
        "thesis_id": "THESIS-1",
        "final_action": "BUY_NOW",
        "capital_permission": "CAPITAL_ALLOWED",
        "contract_symbol": "T1261120C00100000",
        "invalidation_spot": 95.0,
        "target_price": 110.0,
    }
    kwargs = dict(
        run_id=RUN_ID,
        source_manifest_sha256="a" * 64,
        row=row,
        evidence_refs=[{"dataset_id": "EOD-PRICE-1", "sha256": "b" * 64}],
    )
    first = build_eod_review_bundle(**kwargs)
    second = build_eod_review_bundle(**kwargs)
    assert first == second
    assert first["bundle_id"] == second["bundle_id"]
    assert first["source_action"] == "BUY_NOW"
    assert first["authority"] == "ADVISORY_ONLY"
    assert "capital_permission" not in first
    assert row["capital_permission"] == "CAPITAL_ALLOWED"


@pytest.mark.parametrize(
    "change",
    [
        {"source_manifest_sha256": "not-a-sha"},
        {"evidence_refs": [{"dataset_id": "EOD-PRICE-1", "sha256": "bad"}]},
        {"row": {"run_id": RUN_ID, "ticker": "T0", "target_price": float("nan")}},
    ],
)
def test_eod_bundle_rejects_invalid_provenance_and_nonfinite_values(change: dict) -> None:
    from contracts.interpreter_eod_review import EODReviewBundleError, build_eod_review_bundle

    kwargs = dict(
        run_id=RUN_ID,
        source_manifest_sha256="a" * 64,
        row={"run_id": RUN_ID, "ticker": "T0", "direction": "PUT"},
        evidence_refs=[{"dataset_id": "EOD-PRICE-1", "sha256": "b" * 64}],
    )
    kwargs.update(change)
    with pytest.raises(EODReviewBundleError):
        build_eod_review_bundle(**kwargs)
