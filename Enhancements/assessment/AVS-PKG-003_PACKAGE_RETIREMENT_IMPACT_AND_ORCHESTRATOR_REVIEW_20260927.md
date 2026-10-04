# AVS-PKG-003 — Impact of retiring the package process on the rest of the pipeline, and orchestrator review

**Status:** assessment for ACK, 27 September 2026; read-only. Companion to AVS-PKG-001 (what packages hold) and AVS-PKG-002 (retirement proposal).

## 1. Is this a "mini data lake"?

No. It is the missing last step of a decision already taken. `docs/AVSHUNTER_CANONICAL_DATA_SYSTEM_SOLUTION_DESIGN_v1.md` §1 states: *"AVSHUNTER will use one governed logical source of truth for market data. Every stage will obtain data through a canonical data gateway."* Its §4.1 defines that source of truth as five things, four of which exist today:

| §4.1 element | Exists | Where |
|---|---|---|
| Registry / control plane (SQLite, WAL) | yes | `data/canonical/control_plane.sqlite`, 22 tables incl. `run_registry`, `stage_worklist`, `dataset_registry`, `api_request_ledger`, `projection_outbox` |
| Daily market history | yes | `data/canonical/historical_prices.sqlite` via `canonical_data.history_bridge` |
| Option-chain snapshots | yes | `data/phantom/phantom_history.db`, `data/canonical/market_observations` |
| Live validation snapshots | yes | `data/canonical/live_options`, `market_observations/exact_option_quote` |
| **`runs/<run_id>/canonical_manifest.json` — immutable list of dataset IDs and hashes consumed by a run** | **no** | run root today holds `run_meta.json`, `truth_packet_run.json`, `cds3_discovery_publication_*.json`, `macro_snapshot.json`; no per-run dataset manifest |

The packages are what a run consumes *instead of* that manifest: a materialised copy of the sources, made before the canonical stores existed. The design's own principles (§3.1 capture once, compute many; §3.3 superset reuse; §3.8 reproducibility before optimisation) describe the proposed manifest exactly. Nothing new is stored; one existing store gains a per-run citation record, and the copy step goes.

The CDS-3 stage (`prepare_cds3_governed_package_input`) already publishes the Packages ticker worklist from `stage_worklist` in the control plane. It runs in shadow mode (`stage_gating_enforced` off), returning `None`. Enforcing it is the natural first half of the manifest: the ticker set is governed, and the manifest adds the dataset citations.

## 2. Orchestrator map: who touches packages

Evening (`evening_workflow`, 2,200 lines from 5240) in execution order; **bold** = touches packages.

| Order | Phase | Reads | Writes | Package dependency |
|---|---|---|---|---|
| 0 | Universe scanner consumer | scanner manifest, manual upload | augmented universe | none |
| 1 | Discovery | universe, canonical history | `discovery_candidates_ultimate_*.csv` | none |
| 1B | Macro publication, run-scoped copy, GEX sync, horizon router | Dropbox macro, control plane | `macro_snapshot.json`, `macro_quant_packet.json` | none |
| 4.6 / 4.7 | Actuarial cache build, transition matrix, regime screener | actuarial v7 parquet | `actuarial_cache_v7.parquet` | none (cache is *consumed by* build_packages) |
| CDS-3 | Governed package input | `stage_worklist` | `discovery_candidates_cds3_*.csv` | shadow today |
| **Vanguard pipeline** | | | | |
| **· Build Packages** | discovery, macro snapshot, actuarial cache, truth packet | **1,660 package files + index.json** | **producer** (critical) |
| **· Inject Macro** | macro snapshot | **rewrites all packages** | **producer** (critical) |
| **· Backfill Timeseries** | `historical_prices.sqlite`, Polygon on flag | **rewrites all packages (4 bar copies)** | **producer** (custom 5 % failure gate) |
| **· Build Completed Market Profiles** | **`packages/index.json` for the ticker list**, control plane | market_profile summary | **reader** (ticker list only) |
| **· run_vanguard_from_packages** | **packages: bars (6-alias chain), macro payload, regime_snapshot, quant packet** | `vanguard_signals.csv`, `vanguard_signals_enriched.csv`, `horizon_profile` | **primary reader** |
| **5.5 Trap engine** | **packages** | **patches `tle` into packages** | **reader + writer** |
| Catalyst truth (pre-options) | CSVs | CSV | none |
| **8a Options Intelligence** | discovery + Vanguard CSVs; **packages for macro-enrichment contexts and `tle` contexts** | `options_intelligence_*.csv` | **reader** (two loaders, lines 525 and 559) |
| 1B (again) | Horizon router | macro | horizon CSV | none |
| Catalyst truth (post-options) | CSVs | CSV | none |
| **8.5 Actuarial enrichment** | actuarial cache | **patches `actuarial` into packages** | **writer** |
| 7.5 Phantom scoring | Phantom DB | CSV | none |
| **8.6 Trigger layer** | EIL/Vanguard CSVs | **patches `triggers`, `eligible_for_trade` into packages** and enriches the CSV | **writer** (CSV already carries the same fields) |
| 8d SuperBrain passthrough, 8b catastrophe gate, wall-break scorer | Vanguard/options CSVs | `superbrain_enriched_*.csv` | none |
| **EIL (execution_intelligence_runner)** | `superbrain_enriched`; actuarial map "from packages" (fails in subprocess) | `eil_enriched_*.csv` | **reader, unreliable → workaround** |
| **`inject_actuarial_into_eil_csv`** | **packages `actuarial`** | patches `eil_enriched` | **reader** (the workaround) |
| 10a/10b GARCH | canonical history | l3 fields into `eil_enriched` | none |
| Catalyst truth (post-EIL) | CSVs | CSV | none |
| 10 EOD candidate engine | `eil_enriched`, Vanguard, WBS, discovery CSVs | EOD candidates, trades | none |
| Market-context diagnostics | CSVs | diagnostics | none |
| Final run manifest, Lab book, Interpreter handoff, outcome maturation | CSVs, manifests | `final_run_manifest.json`, Lab book | none |
| **`write_latest_json`** | **`packages/index.json` must exist** | `data/output/latest.json` | **gate** (latest pointer not written without index.json) |
| 10 Archive (now excludes packages), 10c prune | run dir | archive | none |

Morning (`premarket_workflow`, line 7535 → `morning_gate.run_morning_gate`, `morning_validation`, `morning_handoff_finalizer`): **no package reads**. Lab, Interpreter, WAR, C12 outcome scoring: **none**. Tests: 16 files mention packages, 5 test the four scripts directly. `desk_card.py` reads macro JSON and morning outputs, not packages.

So the blast radius is confined to the Evening segment between CDS-3 and EIL: three producers, two patchers, four readers, one gate, and the tests for them. Everything from SuperBrain onwards, the whole Morning, the Lab and the Interpreter are CSV/manifest-driven and untouched.

## 3. Impact per dependent, with its replacement and parity check

| Dependent | Impact of retirement | Replacement | Parity gate |
|---|---|---|---|
| Build / Inject / Backfill scripts | retired (64 min, 4.85 GB per run) | run input manifest written by run planning (`avshunter/c0_run`), fed by the CDS-3 worklist (enforced) | DCV verdict per ticker equals today's `data_contract` block on a frozen run; coverage ≥ today's 95 % gate |
| `run_vanguard_from_packages` | loader rewritten; adapter and all model code unchanged | bars via `history_bridge.read_canonical_history` checked against manifest bar count/last session; macro and quant packet loaded once from run root | `vanguard_signals*.csv` and rejects byte-identical on run `20260926_173730` |
| Build Completed Market Profiles | loses its ticker list source | manifest ticker list (or `stage_worklist`) | identical profile summary |
| Trap engine (`tle`) | stops patching packages | appends `enrichment/trap_<run>.csv` (run_id, ticker, version, input hash) | Options' `tle` contexts identical |
| Options Intelligence macro/tle loaders | two loaders re-pointed | macro enrichment contexts from `macro_snapshot.json` (one owner; today the package copy is a second owner of the same fact, an R2 violation); `tle` from the trap ledger | `options_intelligence_*.csv` identical |
| Actuarial Phase 8.5 + `inject_actuarial_into_eil_csv` | patch and workaround both retired | actuarial pass writes `enrichment/actuarial_<run>.csv`; EIL reads it directly (the failing in-subprocess package read disappears with the packages) | `eil_enriched` actuarial columns identical |
| Trigger layer `patch_run_packages` | package write dropped; `enrich_csv` kept | already the CSV path | `eil_enriched` trigger columns identical |
| `write_latest_json` | gate re-pointed | manifest presence and hash | `latest.json` written on every successful run |
| Backfill's Polygon rescue (`--allow-polygon`) and 5 % failure ratio | moves out of the run | canonical ingestion owner fetches missing ranges *before* the manifest (design §3.4); manifest DCV coverage becomes the gate | provider request count and worklist coverage in the run plan |
| Archive / prune / retention | simpler | nothing to exclude; run footprint tens of MB | none |
| Tests (16 files) | 5 script tests retired, others re-pointed at the manifest | manifest contract tests, loader parity tests | INT-001-style static import closure: no production module opens `packages/` |
| Research probes under `audit/td` | read packages for field census | read the manifest or are archived | n/a |

Authority axes (INT-001 §3) are untouched: no direction, gate, score, rank or capital logic reads a package; every gate above is byte-identical output.

## 4. Orchestrator review (beyond packages)

Observed in `intelligent_orchestrator.py` (8,175 lines, one process, subprocess fan-out):

1. **Stage handoff by mutable files with post-hoc patches.** Three phases rewrite 1,660 files to add ~1 KB each; EIL cannot read them reliably in its subprocess, so `inject_actuarial_into_eil_csv` exists as a "safety net" that re-reads them in-process. This is the design smell the manifest-plus-ledger removes: a stage should own an append-only output, not edit another stage's input.
2. **Two owners of the macro fact inside a run.** `macro_snapshot.json` at the run root and `pkg["macro"]["payload"]` in every package; Options reads the package copy. R2 (one owner per fact) is violated today and repaired by retirement.
3. **Phase numbering no longer reflects order.** Sequence is 0, 1, 1B, 4.6, 4.7, Vanguard, 5.5, 8a, 1B (again), 8.5, 7.5, 8.6, 8d, 8b, EIL, 10a/10b, 10, with 9.5/9B/9C commented out. Harmless functionally, costly for anyone reasoning about dependencies; the phase table in §2 should become the documented order.
4. **`latest.json` depends on `packages/index.json`.** The pointer that everything downstream uses to find "the current run" is gated on an artefact of the copy step. It should be gated on the run manifest.
5. **Critical flags are uneven.** Build/Inject are `critical=True`; Backfill has its own 5 % failure-ratio gate; market profiles are non-critical with a "Vanguard will receive NOT_EVALUATED" warning. Under the manifest these collapse to one DCV coverage gate at manifest time.
6. **Archive twin and 90-day retention of 5 GB runs.** Fixed this weekend for the twin; retention size is solved by the same change.
7. **Not a target for restructuring now.** CLAUDE.md rule 4 says enhance in place; the monolith is not the defect. The package retirement removes three subprocess phases, two patch phases and one workaround from it, which is the largest simplification available without a rewrite. A later split of phases into modules would be a separate governed decision.

## 5. What we should be aware of before starting

- The Polygon rescue inside the backfill is the only place today where a short or stale canonical history gets repaired during a run. Moving it to canonical ingestion is a behaviour change in *when* provider spend happens (before the run, under the run plan's estimate) and must be visible in the run plan; without it, a ticker with stale canonical history becomes a typed DCV rejection instead of a silent refetch.
- Enforcing CDS-3 (`stage_gating_enforced`) changes a shadow gate into a fail-closed one; a missing or duplicate worklist ticker aborts the Vanguard stage instead of logging. That is the intended fail-closed behaviour, but it needs one live proving Evening.
- The parity gates require the retained package set for run `20260926_173730`; do not delete it until P2 and P3 have passed.
- Live proving (ACK-started normal completed-session Evening and Morning) is required at P2 and P4; no automated run.

No file was modified by this assessment.
