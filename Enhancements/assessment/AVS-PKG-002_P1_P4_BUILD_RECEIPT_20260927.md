# AVS-PKG-002 — build receipt for P1 to P4 (27 September 2026)

**Status:** P1, P2 and P3 committed (`1a06988`, `ed2e8b9`, `913b8ce`); P4 **TESTED_UNCOMMITTED**. Every slice was built test-first, proven offline, and regression-tested; none has had live proving (an ACK-started normal completed-session Evening and Morning), so the programme as a whole is **IMPLEMENTED_PENDING_LIVE_ACCEPTANCE**. No pipeline run, provider call or broker action was made. The stored run `20260926_173730` was read, never modified, except for the addition of its `canonical_manifest.json`.

## What each slice delivered

| Slice | Owner touched | Failing test first | Gate passed | Commit |
|---|---|---|---|---|
| P1 run input manifest | `avshunter/c0_run/canonical_manifest.py`, `scripts/build_canonical_manifest.py`, non-critical hook in `run_vanguard_pipeline` | citation by hash, typed per-ticker history verdicts against the evidence session, determinism, worklist/dedupe, typed missing sources, hook placement | manifest verdicts equal the data-contract validator over each package's actual bars for all 1,666 tickers (1,616 VALID, 50 STALE_DATA = the backfill's failed set) | `1a06988` |
| P2 Vanguard by reference | `avshunter/c0_run/thin_package.py`; `inject_macro_into_package` and `attach_canonical_bars` extracted in place; runner `--input-mode` / `--output-dir` | thin package == stored package except declared stamps and post-Vanguard patches; runner default `packages`; manifest cites CDS-3 input, runtime macro and its `ingested_utc` | packages mode over Vanguard-time-reset packages == manifest mode at the same moment (25 tickers): rows and rejects identical except Vanguard's two timestamp columns | `ed2e8b9` |
| P3 enrichment ledgers | `contracts/enrichment_ledger.py`; trap engine, trigger layer, actuarial pass write; Options, EIL map, post-hoc injection, eligibility mirror read | ledger round-trip, run identity refusal, last-record-wins; each reader returns the same facts with `packages/` deleted | 5/5; 568-test regression | `913b8ce` |
| P4 package-free Evening | `vanguard_input_mode()` (default `manifest`, `packages` = rollback); package phases moved to `_run_package_input_phases`; manifest build critical; trap/trigger/actuarial from manifest + Vanguard CSV; Options macro contexts from the run reference; `latest.json` gated on the manifest; profile lister tolerant | 9 rules: default mode, phase skipping and abort, rollback path, each stage without packages, pointer, profiles | 9/9; regression 934 passed across the 92 test files touching the orchestrator and the changed modules (one P1 hook test re-pointed to the P4 rule); full-population manifest-mode Vanguard run on `20260926_173730` in progress at commit time, result appended in section "Full-population run" when available | committed after regression |

## Findings recorded on the way (none fixed here; all typed, none hidden)

- **PKG-F1** — every stored package carries `data_contract.dcv_valid=False / NO_OHLCV` and `data_failure=True` stamped before backfill and never re-annotated, although 1,616 hold 1,279 bars. Vanguard re-validates at load so it does not gate; the manifest computes its verdict from canonical bars instead.
- **PKG-F2** — Vanguard's rows are not reproducible from a run's packages across days: a packages-mode rerun one day later differs from the stored Evening rows on about 100 columns (Layer-2 actuarial expectancies from the live `actuarial_cache_v7.parquet`, Layer-1 profile POC/value areas, beta, volume). This is an R7 gap in Vanguard itself, outside this programme; the P2 gate therefore compares the two input modes at the same moment.
- The backfill withholds stale canonical bars, so a package cannot distinguish "no history" from "too old"; the manifest says STALE_DATA with the date. In manifest mode the thin package applies the same freshness rule so Vanguard's reject reason is byte-identical.

## The two approved behaviour changes (ACK, 27 Sep)

1. **Provider refresh owner.** In manifest mode the backfill's in-run `--allow-polygon` path no longer runs. Canonical history is refreshed by Discovery's write-through before the run; a ticker still stale at the evidence session is a typed `STALE_DATA` rejection in the manifest and a `DATA_FAILURE` reject in Vanguard, never a silent mid-run refetch. Provider spend is therefore visible in the run plan's estimate.
2. **CDS-3 enforcement.** `AVSHUNTER_STAGE_GATING_ENFORCED` already defaults to `1` in the orchestrator's main; `prepare_cds3_governed_package_input` runs before the input-mode branch and fails closed on a missing, duplicate or unexpected worklist ticker. The manifest cites the governed `discovery_candidates_cds3_<run>.csv` (`governed_input=True`).

## Rollback

`AVSHUNTER_VANGUARD_INPUT_MODE=packages` restores the pre-P4 Evening: the three package phases run, the manifest is written non-critically beside them, and every reader falls back to the package files. Frozen history is untouched by either mode.

## What live proving must show (ACK-started, not automated)

- Evening: `Build Canonical Manifest` critical and green; no `packages/` folder written; Vanguard pass/reject counts and reject reasons reconcile with the manifest's coverage; trap, trigger and actuarial ledgers present with the full population; Options and EIL log ledger-sourced contexts; `latest.json` written; final manifest and Lab book reconcile as before.
- Morning: unchanged (it never read packages), but must complete against the manifest-built Evening.
- Runtime: the three removed phases took 64 minutes on 26 Sep; the Evening should be shorter by about that.

## Full-population run (appended 27 Sep, 22:00)

Manifest-mode Vanguard over the complete retained run `20260926_173730`, output to a temporary folder, the real run untouched:

| Measure | Manifest mode (27 Sep) | Stored Evening from packages (26 Sep) |
|---|---|---|
| PASS rows | 1,616 | 1,616 |
| Rejects | 50, all `DATA_FAILURE_NO_OHLCV` | 50, all `DATA_FAILURE_NO_OHLCV` |
| Unique `state_hash` | 131 / 1,616 | n/a |
| Vanguard wall-clock | 98 min (5,883 s) | 44 min |

Coverage and reject reasons are identical to the stored Evening. The wall-clock figure is an **upper bound**, not a like-for-like: for most of the run a runaway single-threaded Python process (a stray from this session, since killed) held one core at ~90 %, and a 92-file regression batch ran concurrently. Even so, per-ticker cost in manifest mode is higher than reading a pre-built file, because each package is built in memory (builder, truth packet, macro injection, canonical bars from SQLite). Net Evening effect is still expected to be positive (the three removed phases took 64 min on 26 Sep), but it must be **measured in live proving**, and the in-memory build is the first optimisation candidate (**finding PKG-F3**): the truth packet is rebuilt twice per ticker (builder and injector) and the SQLite read is per ticker; a single ordered read and a once-per-run truth-packet prefix would remove most of it.

## Not done

P5 (delete the package readers/writers, retire the three scripts and the `packages` mode, update docs and the field owner matrix) follows live proving of P4, not before. The S0 import-closure test still fails on three untracked TEV-001 modules imported by the orchestrator's foreign working-tree edits (not part of this programme).
