# ETF reliability: first increment status

Date: 14 November 2026. Status: **initial E1/E17 implementation tested offline; wider ETF work remains open**.

## Delivered

- Canonical read-only security-master adapter with explicit validity/knowledge dates, content hash, source, unknown and ambiguous states. Literal NAN/SYM retained. No aliases or legal wrappers guessed.
- Versioned, display-only review policy: macro advisory; canonical rank preserved; source-known special products and existing board risk groups labelled RESEARCH_ONLY. Current review policy is explicitly not a historical trading decision.
- Additive final-book and compact Lab identity fields, source lineage and card disclosure. No selector, expiry, Lane B, scores, direction, active gates or row inclusion changes.
- Offline reconciliation CLI with exclusive audit-file creation and duplicate-header rejection. No database access, provider clients or pipeline invocation.

## Saved evidence

Primary receipt: `ETF_IDENTITY_HANDOFF_INVENTORY_20261114_v2.json`.
Input: saved 12 November hand-off for completed run `20261111_231951`; 2,132 rows and unique tickers. All pre-existing values and row order were preserved by the identity projection.

| Saved hand-off assessment | Count |
|---|---:|
| Source-reported dated classification | 440 |
| Legacy classification dates absent; point-in-time identity unassessed | 1,682 |
| Classification requires review | 6 |
| No master row | 4 |
| Research-only review labels (overlaps the identity categories) | 8 |

The four missing master tickers are ARKG, GOOG, SQQQ and TQQQ. Board universe: 115 members, 42 without a master row. Combined saved-book/board universe: 2,194 unique tickers. These are identity/membership counts, **not missing option-chain counts**. No dated chain-coverage receipt was supplied, so chain availability is NOT_ASSESSED throughout.

QQQ/XOVR retain their reported ETF_OTHER type and a review warning. Legacy volatility labels retain their source type without asserting exact leverage or ETF/ETN legal wrapper. The source CSV was not edited; issuer/source-backed remediation remains open.

Earlier receipts are retained as audit history. `ETF_IDENTITY_INVENTORY_20261114.json` describes only the currently present four-row `lab_signal_book_v3.csv`, not the full book. `ETF_IDENTITY_HANDOFF_INVENTORY_20261114.json` predates the refined undated-classification reason and board-risk policy disclosure. Use v2 for current results.

The alternative 433 MB `final_opportunity_book_20261111_231951.csv` has duplicate header names (including usmi_sector_alignment); it was not used as an unambiguous complete-input proof or rewritten. The saved hand-off is the explicitly identified audit input. Do not mistake these inconsistent current artefacts for validated full publication coverage.

## Verification

- Tests first: initial seven identity tests failed because the adapter did not exist. The subsequent board-risk-policy test failed before its implementation.
- `tests/test_etf_identity_reliability.py`: **12 passed**, including real materializer characterization, unknown dates, risk-policy provenance, unchanged facts/order and projection round-trip.
- `tests/test_lab_review_projection_v1.py`: **21 passed**.
- `tests/test_lab_review_accuracy_v1.py`: **6 passed**.
- `tests/test_lab_review_sources_v1.py`: **15 passed**.
- `node tests/test_etf_identity_frontend.cjs`: PASS.
- `node tests/test_lab_contract_display_frontend.cjs`: PASS.
- Review-app JavaScript syntax check and tracked-patch whitespace check: PASS (Git reports the existing CRLF conversion warning).

Total: 54 passing Python tests across the recorded focused suites, plus two passing Node checks. The repo venv emitted `Failed to find real location of C:\Python314\python.exe` but completed the listed suites with exit 0. That runtime warning is recorded, not repaired by substituting an unapproved interpreter.

Saved-data inventory confirms no source-master edits, 0 provider calls and no pipeline run. No commit or push was requested or made. Historical Lab artefacts have not been republished. Browser/live-page verification and authorized forward-run evidence remain outstanding; code/test presence is not operational closure.

## Shared ownership and next work

The first increment already changed seven additive lines in `contracts/lab_control.py` before Claude's one-writer scenario coordination request arrived. Its diff only imports/exports identity fields and attaches disclosure after canonical ranking. `scripts/avshunter_options_intelligence.py` is untouched. Further edits to either shared file are paused for coordination; existing changes are preserved for the separate scenario reviewer to inspect. The v2 scenario review was withdrawn from this chat and is not being duplicated here.

Next approved increment: quote/session provenance, event freshness and the missing-IWM lineage trace, followed by independent measurements. Do not invent event-age N or measurement thresholds: source gaps and design parameters must be explicit. Context/holdings, dividend-model design, timing/probability audit and final cross-owner publication remain open in the previously approved order. Selection/expiry and all Lane B implementation stay with Claude.
