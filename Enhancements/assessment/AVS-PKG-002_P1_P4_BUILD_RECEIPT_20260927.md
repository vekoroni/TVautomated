# AVS-PKG-002 — build receipt for P1 to P4 (27 September 2026)

**Status:** P1–P4 committed (`1a06988`, `ed2e8b9`, `913b8ce`, `456ca63`, `03fd468`). **Evening live-proved 28 Sep 2026** on run `20260927_205123` (section "Live proving" below): package-free path held, one missed reader found (PKG-F4, fixed test-first as P4b, TESTED_UNCOMMITTED). Morning live proving and P5 remain. No pipeline run was started by Claude; ACK started the Evening.

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

## Live proving — Evening `20260927_205123` (ACK-started 27 Sep 21:51, completed 28 Sep 01:21)

First package-free Evening on the full population. ACK started it; Claude only watched the log. **No abort, no error, `EVENING WORKFLOW COMPLETE` at 01:21:07, process exited cleanly.**

| Check from "What live proving must show" | Result |
|---|---|
| `Build Canonical Manifest` critical and green | DONE in 63 s (22:11:28 → 22:12:31) |
| No `packages/` folder written | confirmed: run dir has `canonical_manifest.json`, no `packages/` |
| Vanguard counts reconcile with the manifest | 1,616 passed / 50 rejected, identical to the offline manifest-mode run and to the 26 Sep Evening |
| Trap, trigger, actuarial ledgers with the full population | `trap` 1,666, `actuarial` 1,666, `trigger` 1,616 records |
| Options and EIL log ledger-sourced contexts | Options loaded 1,666 TLE contexts; EIL loaded the 1,616-ticker actuarial map; post-hoc injection found `eil_enriched` already populated |
| `latest.json` written | 00:39:12 |
| Final manifest and Lab book reconcile | health 92, `NEEDS_MORNING_VALIDATION`, Interpreter EOD snapshot with book hash written |
| Archive without packages | 124 files in 17 s (26 Sep: 1,952 files in 2 min 35 s) |
| Runtime | 3 h 30 min start to completion (26 Sep Evening: 7 h 47 min). Vanguard itself ~44 min at full CPU, i.e. the in-memory per-ticker build (PKG-F3) cost nothing measurable against the 26 Sep 44 min from files once the machine was not contended |

### Degradations observed (typed, none hidden)

- **PKG-F4 (P4b gap, fixed test-first 28 Sep, uncommitted).** The FIX-ACTUARIAL-SEQ block inside `evening_workflow` that stamps actuarial facts into `superbrain_enriched` BEFORE EIL still required `packages/`; it skipped, set `actuarial_loaded_before_eil=False` and the run was labelled `PREP_DEGRADED_ACTUARIAL_MISSING` / `REVIEW_ONLY_ACTUARIAL_DEGRADED` although the ledger held 1,616 enriched tickers and EIL scored with them. Fix: the block is now `inject_actuarial_into_superbrain_pre_eil(run_id)` reading `load_actuarial_map` (ledger first, packages fallback) and returning a typed summary (`source`, `patched`, `fill_rate`, `loaded_before_eil`, `reason`); `tests/test_pre_eil_actuarial_injection_p4b.py` (4 rules) written failing first, then green. The P4 survey missed this reader because it globbed `*.package.json` inline rather than calling a package loader. Consequence for this run: review-only label only; EIL, Options, execution and the Lab book carry the actuarial facts.
- **Phantom 7.5 timed out after 1,200 s and was bypassed** (original options CSV used downstream). Pre-existing fragility (13 min on 26 Sep against a 20 min limit); not a P4 effect. Recorded for a separate RCA.
- **DOI ranked 55 families (26 Sep: 574).** Not a P4 effect: 505 assessed families were `existing lifecycle event conflicts with replay scope` because this Evening re-processed the same Friday 26 Sep session that the 26 Sep Evening had already written lifecycle events for; the 776 quote-identity exceptions equal the 26 Sep count.
- **Morning-manifest handoff shows zero filled contract Greeks / McMillan fields** — identical on 26 Sep; pre-existing, outside this programme.
- **Drop-off audit stage label `PENDING_PACKAGE_BUILD` (1,666 rows)** — a label that assumes packages; rename in P5.

**Morning run:** not yet run; it is ACK's to start. **P5** waits for it.

### P4b regression (28 Sep, after the Evening)

One file per process: P4b 4, P4 9, P3 5, P2 6, P1 8, archive 5, outcome maturation 14, C12 scoring 5, DDD session authority 9, empirical EV shadow 14, EV3 order 5, macro publication boundary 4 — **all green**. The P2 thin-package parity tests (AAPL, VST, XLF) first failed for a reason worth recording: the Evening's Discovery write-through recorded a Polygon **volume revision of the 25 Sep bar for 767 tickers** in `ohlcv_daily_revisions`, so live canonical history no longer equals the frozen 26 Sep package files on that one field. The pipeline is right (canonical history is corrected in place and the revision is ledgered, rule R12 fresh-or-flagged); the test was comparing a frozen artefact against a living source. It is now revision-aware: it brings the stored bars forward by the ledgered revisions recorded after the package was built and asserts the ledger explains every difference. The same-moment P2 gate (packages mode vs manifest mode) was unaffected.

## Live proving — Morning on `20260927_205123` (28 Sep, first attempt 14:51–15:07 FAILED CLOSED; not a P4 effect)

**Finding LIVE-M1 (option liquidity lifecycle store, fixed test-first 28 Sep, uncommitted).** The Morning gate failed closed on FA: `OptionLifecycleConflict: contract quote identity already has different immutable content`. Mechanism: the Evening persists the selected contract's EOD quote under identity thesis+run+contract+provider quote timestamp, WITHOUT bid/ask sizes (none of the 1,192 Evening rows hold them). This Monday morning FA's contract had not quoted since Friday's close, so MarketData returned the same quote timestamp with identical bid/ask/IV/delta; the Morning re-quote mapped to the same identity but carried sizes, and the store's replay check treated "missing on one side" as a different value. 204 tickers with fresh Monday timestamps had already persisted; FA was the first stale one. Fix (one rule in `canonical_data/option_liquidity_lifecycle.py`): a field one capture never held is an added fact, not contradicting content; content both captures hold that differs still fails closed. Pinned by `test_morning_requote_of_an_unchanged_eod_quote_adds_sizes_the_eod_capture_never_held` in `tests/test_option_liquidity_lifecycle.py` (failed before, 18/18 after). Latent since the store's replay rule was written; exposed by a quiet-Friday-close thin name.

**Re-run safety of a second Morning pass on the same run (assessed before ACK restarted it):** the failed pass stopped inside the gate, before `morning_validated_trades`, the handoff finaliser, the Lab rebuild and the Interpreter sync, so no completion artefact exists to be doubled. Everything it did write is replay-safe: contract observations are identity-keyed (same stale quote → replay; fresh quote → a new, correct observation), Morning thesis/selection events are keyed on the evidence hash including fetch time (append-only, version+1), `stage_worklist` is INSERT OR IGNORE, `ticker_lifecycle` appends version+1, and the Catalyst Truth pre-patch drops its own columns before re-merging. Provider spend: 1,334 MarketData requests on the first pass against a 100,000 daily budget. The earlier incident ACK recalls (adverse data effect from running the Morning twice) concerned a second pass after a COMPLETED Morning, which re-finalises; it does not apply to a first completion after a failed gate.

## Finding PKG-F5 — completed market profiles lost in manifest mode (found 28 Sep 16:18, Morning second pass failed at the handoff finaliser)

**Severity: high. Cause: this programme (P2 and P4).** The Morning's second pass cleared the gate (488 GO / 323 FLAG / 739 BLOCK) and failed in the handoff finaliser: `Execution Gate -> Intelligence Lab authority reconciliation failed: ETN:ACTION_BUY_NOW_EXPECTED_GO_GOT_BLOCKED; ...`. The Lab book locks every row with `RUN_FATAL:COMPLETED_MARKET_PROFILE_MISSING_OR_UNUSABLE` because the run's `completed_profile_summary` reports `input_count=0, completed=0`. Two defects, both mine:

1. `scripts/build_completed_market_profiles.py` takes its ticker worklist from `packages/index.json` and its ATR14 from each package's daily bars, and patches `market_profile_evidence` (+ dataset id, state, quality) INTO the package file before Vanguard. P4 made `_package_paths` return `[]` without an index ("tolerant") instead of sourcing the worklist from the manifest, so the Evening built 0 profiles in 3 s (26 Sep: 1,480 profiles, 798 provider requests, 39 min). The run-level fatal flag then blocks every Lab row, correctly.
2. Vanguard reads the completed-profile evidence FROM the package (`run_vanguard_from_packages.py` → `market_profile_evidence` → Layer-1 auction synthesizer; absence = NOT_EVALUATED by design, never fabricated). The thin package never carried it. P2 classified `market_profile_` as a post-Vanguard patch prefix (wrong: the builder runs BEFORE Vanguard), so the P2 gate reset those fields on both sides and could not see the loss; the full-population comparison did show Layer-1 profile differences, misattributed to PKG-F2. Live effect on Evening `20260927_205123`: `layer1__auction_state=NOT_EVALUATED` on all 1,616 rows, `layer1__profile__poc` / value areas empty (26 Sep: 1,480 evaluated, 968 INSIDE_VALUE / 263 ABOVE / 249 BELOW).

**Consequences.** Today's Morning (28 Sep) is not execution-grade: the Lab's block is the correct outcome of the guard, and the underlying Vanguard rows lack Layer-1 auction context. The receipt's 3 h 30 min runtime included skipping the 39-minute profile build, so the like-for-like Evening gain is smaller than stated. The 26 Sep profiles for session 2026-09-25 remain in the canonical profile store; nothing was deleted.

**Immediate mitigation.** `AVSHUNTER_VANGUARD_INPUT_MODE=packages` (the P4 rollback) restores the full pre-P4 Evening including the profile build and patch; the ledgers, the P4b pre-EIL stamp (ledger-first with package fallback), the archive exclusion and the lifecycle-store fix all still apply in that mode.

**P4c design (test-first, offline until proven):** (a) builder worklist from `canonical_manifest.json` tickers when no package index, ATR14 from `HistoricalPriceDatabase.read(ticker, end_date=session)`, and per-ticker `market_profile_*` facts written to a `market_profile` enrichment ledger (P3 pattern) instead of package patches; (b) `ThinPackageFactory.build` attaches `market_profile_*` from that ledger (Vanguard input unchanged); (c) `market_profile_` removed from `POST_VANGUARD_PATCH_PREFIXES` so the P2 parity and same-moment gates must match on it; (d) offline proof on `20260926_173730`: Layer-1 fields identical between modes; (e) live proving on a later Evening.

## P4c — completed market profiles in manifest mode (built 28 Sep, test-first, TESTED_UNCOMMITTED)

| Owner touched | Change |
|---|---|
| `contracts/enrichment_ledger.py` | `market_profile` is a ledger stage; `load_market_profile_stamps(run_dir)` (ledger first, package files as fallback); `MARKET_PROFILE_KEYS` |
| `scripts/build_completed_market_profiles.py` | `_worklist`: package index while a run carries packages, else the manifest's tickers; `_atr14_from_canonical` over `HistoricalPriceDatabase.read(ticker, end_date=session)`; `_stamp`: ledger always, package patch while one exists. Summary, guard semantics and provider path unchanged |
| `avshunter/c0_run/thin_package.py` | step 4 of `build()`: attach the run's `market_profile_*` facts (ledger → canonical profile store for the evidence session → typed NOT_EVALUATED, never fabricated); `market_profile_` removed from `POST_VANGUARD_PATCH_PREFIXES`; `market_profile_quality` (per-fetch diagnostics) declared |
| Tests | `tests/test_market_profile_manifest_p4c.py` (6 rules, written failing first: manifest worklist + ledger, thin package ledger-first, store fallback, typed absence, pre-Vanguard classification, stage declared); P4 profile test replaced by the manifest-worklist rule; P2 gate helper no longer strips the profile stamps from packages mode |

**Offline proof on `20260926_173730`:** 60 sampled tickers, 60 matches — 54 profiled tickers reproduce the stored `market_profile_evidence`, dataset id and state exactly; 6 unprofiled carry the same typed reason (TICKER_INACTIVE ×5, INCOMPLETE_SESSION ×1). Regression, one file per process: P4c 6, P4 9, P2 parity 5/5 and the same-moment gate 1/1 after its helper stopped stripping the profile stamps from packages mode — the first time the gate has compared Layer-1 auction fields in both modes: packages-mode Vanguard over Vanguard-time packages WITH their profile evidence == manifest-mode Vanguard over thin packages carrying the same evidence (25 tickers, rows and rejects identical except Vanguard's two wall-clock columns), P3 5, P1 8, P4b 4, profile guard 7, dynamic-session phase 4 14, archive 5, lifecycle store 18 — all green.

**Not yet live-proved.** P4c has had no Evening. Until it has, Evenings run in `AVSHUNTER_VANGUARD_INPUT_MODE=packages` (ACK's decision).

**Real-scale proof of the P4c builder (28 Sep 17:43–17:49, on the written-off run `20260927_205123`, provider REFUSED by injected fetch so no spend):** worklist 1,666 tickers, all manifest-sourced (no packages); 1,406 profiles completed from the canonical five-minute bars stored on 26 Sep in 374 s; 260 typed `PROVIDER_UNAVAILABLE` (the refusal, expected: on 26 Sep those tickers were fetched live and the stage PASSED with 1,480 completed, 120 no-data deferrals, 16 partial, 50 hard exceptions). **All 1,406 completed profiles are identical (evidence dict) to the 26 Sep packaged build for the same session.** The stage's guard reported FAIL (`MIN_USABLE_RATIO`, usable 84.4% < 90%) purely because of the refused provider. Artefacts written into the dead run: `market_profile/completed_profile_summary_*.json` (this refused-provider result) and `enrichment/market_profile_*.jsonl`; neither changes that run's Vanguard rows.

**Readiness (28 Sep 18:00):** the manifest-mode Evening is ready to run without rollback subject to ACK's risk call. Untested delta tonight: the orchestrator invoking the (unchanged) script interface, and the live provider fetch for tickers without stored bars (unchanged provider code). Failure mode if the stage failed: identical to 27 Sep (Vanguard NOT_EVALUATED, run fatal for the Lab), visible in the stage summary about 40 min into the Evening, before Vanguard finishes.
