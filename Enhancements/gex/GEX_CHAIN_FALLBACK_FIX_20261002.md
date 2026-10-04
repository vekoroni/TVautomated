# GEX chain resolution — permanent fallback fix

Date: 2 Oct 2026. Branch `avs-fix-001`. Brief: `scripts/CLAUDE.md`.

## Root cause (verified in code, not inferred)

`scripts/build_local_gex.py` passed `--session` straight to
`PhantomOptionChainRepository.read`, which queries `chain_snapshots` by
`quote_date` (`canonical_data/gamma_exposure_store.py`). A missing snapshot
raised `chain unavailable for SPY/YYYY-MM-DD`; `main()` returned **exit 2** and
`scripts/refresh_macro_context.py` returned 2 with it, blocking the macro
refresh.

Two corrections to the brief's description of the mechanism:

1. **No expiry is derived anywhere.** A stored chain is one *snapshot session*
   spanning all expiries in `GammaExposureConfig.dte_min..dte_max` (7–56 DTE).
   The failure is session-keyed, so the fallback rolls the **snapshot session**.
   The failure modes the brief lists are real; "derived expiry" is not the
   mechanism.
2. **The output is a manifest**, not a per-ticker JSON: `avshunter_gex_proxy.csv`,
   `avshunter_gex_by_strike.csv` and `avshunter_gex_run_manifest.json`
   (contract `avshunter_local_gex_manifest_v1`). The sentinel is written to the
   manifest and carries the contract keys as well as the brief's keys, so
   `build_macro_json.py` and the overlay reader do not fail on a missing field.

Live confirmation: `--session latest-completed` on 2 Oct derived **2026-10-02**
(today, chain not settled). Pre-fix that was exit 2 every time.

## The fix

Governed window in `config/governed_constants_v1.json` → `gex_chain_resolution`
(`forward_roll_max_sessions: 5`, `backward_roll_max_sessions: 5`), loaded
fail-closed by `load_chain_resolution_policy`. No window literal in domain code.

`PhantomOptionChainRepository` gains `has_chain` and `resolve_session`, which
returns a `ChainResolution` (requested, resolved, direction, sessions rolled).
Resolution order: exact → forward (XNYS sessions, ≤5) → backward (≤5) → none.
A session counts only when **every** requested ticker has a chain there, so one
GEX snapshot never mixes sessions across tickers. The walk tolerates a weekend
or holiday anchor, which `advance_xnys_sessions` rejects.

`build_local_gex(fallback=True)` logs each roll at WARNING with both dates and
records `requested_session_date`, `fallback_used`, `fallback_direction` and
`sessions_rolled`. When nothing is in range it logs at ERROR and writes the
`GEX_UNAVAILABLE` sentinel, returning exit 0. `--no-fallback` restores exit 2.

### Labels say what was measured (R6)

The manifest's `session_date` stays the session **actually measured**;
the requested session is recorded separately. This matters:
`canonical_data/macro_gex_overlay.py` admits an overlay only when
`status == "COMPLETE"` **and** `session_date == required_session`. A rolled
chain is therefore correctly refused as CONFIRMED macro evidence and degrades
through `invalidate_gex_overlay`, while still serving the manual/CLI path.
The sentinel is refused by the same status check.

`orchestrator/completed_session_gex.py` now passes `fallback=False` explicitly.
That path proves the exact-session chains reached Phantom before building, and
the overlay admits only that session, so a rolled chain must never be
registered there. Behaviour is unchanged (the chain is guaranteed present); the
requirement is now stated rather than left to an upstream assertion.

Degradation never destroys evidence: the sentinel rewrites only the manifest,
so the last good proxy and by-strike CSVs survive, and the status check stops
any reader pairing them with the sentinel.

## Verification — all three layers on the live store

Run with `--output-dir` into a scratch directory so live `dropbox/market_data`
was not overwritten; the Phantom store is opened `mode=ro`, so reads are real.
Last stored SPY+QQQ common session: **2026-10-01**. Real gaps at 09-30, 09-28,
09-16 provided true forward-roll cases.

| Layer | Command | Result | Exit |
|---|---|---|---|
| 1 forward | `--session 20260930` | WARNING, rolled forward 1 → 2026-10-01, COMPLETE | 0 |
| 2 backward | `--session 20261006` | WARNING, rolled backward 3 → 2026-10-01, COMPLETE | 0 |
| 2 backward | `--session latest-completed` | derived 2026-10-02, rolled backward 1 → 2026-10-01 | 0 |
| 3 sentinel | `--session 20200101` | ERROR, GEX_UNAVAILABLE | 0 |
| 3 sentinel | `--session 20261015` | ERROR, GEX_UNAVAILABLE | 0 |
| legacy | `--session 20260930 --no-fallback` | `chain unavailable for SPY/2026-09-30` | 2 |

`--session 20261015` lands on layer 3, not layer 2 as the brief expected: it is
10 XNYS sessions past the last stored chain, beyond the governed 5-session
window. `fallback_used` is present in every manifest.

The em dash in the governed messages was mangled by the cp1252 console, so
`main()` reconfigures the streams to UTF-8 before logging.

## Tests

`tests/test_local_gex_chain_fallback.py` — 8 tests, written failing first:
exact session takes no roll; forward roll; backward roll; forward preferred over
backward; a session holding only SPY is not usable for an SPY/QQQ build;
sentinel is labelled; sentinel does not overwrite a prior good proxy; and a
characterisation test pinning the legacy hard fail behind `fallback=False`.

Regression, one file per process, failures counted explicitly: 164 passed, 0
failed, 0 errors across the GEX and governed-constants suites.

## Pre-existing failure, not from this change

`tests/test_ila_selected_contract_identity.py::test_fix_adds_only_the_two_identity_fields`
fails on this branch. The golden fixture `tests/fixtures/ila003_prefix_book_rows.json`
lacks `forecast_candidate_geometry_json`, `forecast_vanguard_reason`,
`thesis_structure_alignment` and other forecast/thesis fields. Those names
appear in **0** files in HEAD and in 2–4 files in the working tree, i.e. they
come from this branch's other uncommitted work (`contracts/lab_control.py` and
the test itself are modified). Unrelated to chain resolution; left for ACK as a
separate defect.
