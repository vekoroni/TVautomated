# AVS-PKG-002 — Retiring the package process: design proposal

**Status:** proposal for ACK's decision, 27 September 2026. No code change. Builds on `AVS-PKG-001` (what packages hold) and follows CLAUDE.md rule 4 (enhance the existing owners in place, test first, one defect at a time) and design rules R2 (one owner per fact), R7 (reproducible inputs), R9 (fewer owned components).

## 1. What the package process costs today

| Evening phase (26 Sep 2026 log) | Wall-clock | What it does |
|---|---|---|
| Build Packages from Discovery | 24 min | writes 1,660 JSON files, each with the whole macro snapshot pasted in three times |
| Inject Macro into Packages | 11 min | rewrites all 1,660 files to paste the macro in again |
| Backfill Timeseries into Packages | 29 min | copies 5-year history out of `historical_prices.sqlite` into each file, four times |
| Later patches (trap, actuarial, trigger) | minutes each | rewrite all files again to add ~1 KB of fields |

64 minutes and 4.85 GB per run, for about 25 KB of ticker-specific content per ticker. The actuarial pass then needs a second mechanism (`inject_actuarial_into_eil_csv`) because "the subprocess cannot reliably read the packages" (orchestrator comment, Phase 8.5), which is a symptom of using files as a shared mutable scratchpad across processes.

## 2. What the packages provide that must survive

1. **Per-run pinned inputs** (R7): what each stage saw for each ticker, replayable later.
2. **Stage handoff without coupling**: Vanguard, trap engine, actuarial pass and trigger layer run as separate processes and exchange per-ticker facts.
3. **Fail-closed per-ticker data contract**: DCV rejects a ticker with a typed reason before any model sees it.

## 3. Target shape: no package files

The four inputs already have owners with fingerprints: the discovery CSV, `runs/<run>/macro_snapshot.json` (+ `macro_quant_packet.json`), `data/canonical/historical_prices.sqlite` (via `canonical_data.history_bridge`, staleness-checked), and the actuarial v7 parquet (registry-fingerprinted). Nothing needs to be copied; it needs to be **cited** and **validated**.

**3.1 Run input manifest (replaces build + inject + backfill).** One file per run, `runs/<run>/run_inputs_manifest.json`, written by the existing run-planning owner (`avshunter/c0_run`), containing:

- run-level: `run_id`, `as_of_utc`, `evidence_session`, `macro_snapshot {path, sha256}`, `macro_quant_packet {path, sha256}`, `historical_prices {path, dataset_fingerprint, max_session}`, `actuarial {path, schema_fingerprint}`;
- per ticker (from the deduped discovery rows): `ticker`, `discovery_row_sha256`, `history {bar_count, first_session, last_session, dcv_verdict, dcv_reason, confidence}`, `regime_present`.

DCV moves from "validate the dict" to "validate the canonical read": `validate_price_history` runs against the bridge result at manifest time; the verdict is recorded once, not re-derived by each consumer. Expected cost: one pass over the sqlite for 1,660 tickers (seconds to a few minutes), one ~2 MB manifest instead of 4.85 GB.

**3.2 Vanguard reads by reference.** `scripts/run_vanguard_from_packages.py` keeps its adapter (`vanguard/integration/orchestrator_adapter.py`) but its loader changes from "open package, walk the six-alias chain" to "for each manifest ticker: bars = `read_canonical_history(ticker)` checked against the manifest's bar_count/last_session; macro payload and regime snapshot loaded once from the run root; `packet_from_package` fed from the run-level quant packet". Same adapter inputs, same outputs; the parity gate is byte-identical `vanguard_signals_enriched` and rejects on a frozen run.

**3.3 Stage facts go to a per-run enrichment ledger, not back into input files.** The trap engine, actuarial pass and trigger layer stop patching JSON. Each appends its rows to `runs/<run>/enrichment/<stage>_<run>.csv` (or a table in the run's ledger sqlite), keyed `run_id + ticker + stage + calculation_version + input_hash`. This is what they already do downstream (`enrich_csv`, `inject_actuarial_into_eil_csv`); the package write becomes redundant rather than removed by force. One owner per fact: a stage owns its own ledger and nobody else writes it.

**3.4 Replay.** A run is reproducible from the manifest alone: resolve each hash against the immutable stores (canonical history by fingerprint, archived macro packet by sha256, actuarial by schema fingerprint). This is stronger than the current copy, because a copied file cannot prove it matches its source; a hash can.

## 4. Sequence (test-first, one owner at a time, no parallel rebuild)

| Slice | Change | Red test first | Gate |
|---|---|---|---|
| P0 | Immediate: NTFS LZX compression on retained `packages` folders; archive already excludes packages | none | disk only |
| P1 | Add the run input manifest beside the packages (both written) | manifest pins every hash; DCV verdict equals the package's `data_contract` for every ticker of run `20260926_173730` | zero disagreement |
| P2 | Vanguard loader reads by reference when the manifest is present, else falls back to packages | `vanguard_signals_enriched` and rejects byte-identical from both paths on the frozen run | parity on one stored run + one live Evening (ACK-started) |
| P3 | Trap, actuarial and trigger write their ledgers; consumers (EIL injection, execution, Lab) read the ledgers | each stage's downstream CSV columns identical from ledger vs package source | parity |
| P4 | Stop writing packages: remove Build/Inject/Backfill phases and the alias chain; DCV runs at manifest time only | no reader imports a package path (static import closure test, like INT-001 S0) | clean-checkout import test, plan-only, one live Evening + Morning |
| P5 | Delete the package readers and the `packages/` retention from prune/archive logic; update `docs/` and the run manifest field owner matrix | | commit last |

Each slice keeps the old path callable behind a flag until its parity gate passes (INT-001 §7 rollback rule). Live proving of P2 and P4 is a normal completed-session Evening and Morning that ACK starts.

## 5. Expected result

- Evening run: about 60 minutes shorter (three phases removed, three rewrites removed).
- Disk: ~4.85 GB per run → ~10–20 MB (manifest + ledgers); the 90-day window from ~110 GB to under 2 GB; archive twins become trivially small.
- Fewer owned components (R9): three scripts and the alias chain retired; the `inject_actuarial_into_eil_csv` workaround becomes unnecessary once the actuarial ledger is the source.
- Provenance improves (R7): inputs pinned by hash against immutable stores rather than by copy.

## 6. Risks and what stays out of scope

- Readers outside the Evening chain (`desk_card.py`, audit probes under `audit/td`, `scripts/build_completed_market_profiles.py`, Options Intelligence's one package read) must be enumerated in P4's static closure test; the audit probes are research tools and can read the manifest or be archived.
- Any ticker whose canonical history is short or stale is today rescued by a Polygon fetch inside the backfill (`--allow-polygon`); in the target that rescue belongs to the canonical ingestion owner, run before the manifest, not inside a per-run copy step. Provider spend stays where run planning already estimates it.
- The Morning run reads the Evening run's packages only through the same consumers; no separate Morning path exists, but P2–P4 must be proven on a Morning as well.
- Not in scope: any change to direction, gating, ranking or authority. This is an input-plumbing change; outputs must be byte-identical at every gate.
