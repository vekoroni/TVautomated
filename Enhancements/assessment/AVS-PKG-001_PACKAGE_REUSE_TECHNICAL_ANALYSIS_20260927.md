# AVS-PKG-001 — Per-ticker package files: what they hold, how they are built, whether they can be reused

**Status:** technical analysis, 27 September 2026; read-only. No pipeline change proposed for activation here; options are listed for ACK's decision.

**Evidence:** the three retained package sets (runs `20260924_085940`, `20260925_061649`, `20260926_173730`; 1,641 common tickers, 60-ticker random sample, script `.claude_scratch/int001/package_analysis.py`), the builder and patch scripts, and the readers found by grep.

## 1. Lifecycle of a package in one Evening run

| Step | Script / phase | Writes into `packages/<TICKER>.package.json` |
|---|---|---|
| Build | `scripts/build_packages_from_discovery.py` | `discovery` row, `macro.payload` (whole macro snapshot), `macro_snapshot` (the same object), `regime_snapshot`, `macro_quant_packet`, `truth_packet`, empty bar slots, `index.json` |
| Macro injection | `scripts/inject_macro_into_packages.py` | re-stamps `macro.payload`, `macro.source_path`, `macro.ingested_utc`, `regime_snapshot` |
| History backfill | `scripts/backfill_timeseries_into_packages.py` | bars from `data/canonical/historical_prices.sqlite` (Polygon only with `--allow-polygon`), written to **four** keys: `ohlcv_daily`, `ohlcv`, `daily_df`, `timeseries.ohlcv_daily` (+ `returns_daily`) |
| Vanguard | `scripts/run_vanguard_from_packages.py` | reads bars through a six-alias fallback chain, `macro.payload`, `regime_snapshot` |
| Phase 5.5 | `avshunter_trap_engine.py` | patches `tle` |
| Phase 8.5 | actuarial enrichment | patches `actuarial` |
| Trigger layer | `trigger_layer.patch_run_packages` | patches `triggers`, `eligible_for_trade` |
| Post-hoc | `inject_actuarial_into_eil_csv` | reads `actuarial` back out |

Other readers: `scripts/data_contract_validator.py` (resolves bars from any alias, requires `regime_snapshot`), `desk_card.py`, `scripts/build_completed_market_profiles.py`, `scripts/avshunter_options_intelligence.py`, `contracts/lab_control.py`, `contracts/interpreter_handoff_materializer.py`, QA scripts.

**Answer to "are they built every run with new data":** yes, rebuilt from scratch every Evening. Every package carries the run's `run_id` and `as_of_utc`, so no file is byte-identical between runs. But almost none of the bytes are new information.

## 2. What is actually inside (latest run, mean 2.31 MB per package)

| Block | Share | Nature |
|---|---|---|
| `macro` (payload = whole macro snapshot) | 36.2 % | run-level, identical in all 1,660 packages |
| `macro_snapshot` (same object again) | 19.7 % | run-level, identical in all packages |
| `truth_packet` | 9.7 % | per-row provenance; changes every run |
| `macro_quant_packet` | 8.6 % | run-level, identical in all packages |
| `timeseries.ohlcv_daily` + `returns_daily` | 8.2 % | 5-year daily bars |
| `daily_df` | 5.7 % | the same bars |
| `ohlcv_daily` | 5.5 % | the same bars |
| `ohlcv` | 5.5 % | the same bars |
| `discovery`, `actuarial`, market profile, `options_contract`, `tle`, `triggers`, flags | ≈ 1 % | the ticker-specific content of the run |

Measured facts behind the table:

- `macro`, `macro_snapshot`, `macro_quant_packet` hash-identical across every sampled ticker within a run: about **1.49 MB × 1,660 ≈ 2.5 GB per run** of data that already exists once at `runs/<run>/macro_snapshot.json` and `macro_quant_packet.json`.
- The four bar blocks are equal to each other inside every file (`ohlcv == daily_df == ohlcv_daily == timeseries.ohlcv_daily`).
- Between consecutive runs the bar history is identical for all 1,278 overlapping sessions and gains one bar (2021-08-23 → 2026-09-23 / -24 / -25). The source of truth is `data/canonical/historical_prices.sqlite` (1.0 GB, all tickers, all history); the packages are a materialised copy of it, made 1,660 × 4 times per run.
- Ticker-specific run content is roughly 25 KB per package. The 2.3 MB file is therefore ~99 % replication.

## 3. Can they be reused?

**Across runs, as files: no.** A package is the run's pinned input record (`run_id`, `as_of_utc`, discovery row, macro of that session, truth packet), and design rule R7 (reproducible inputs) wants each run to state what it saw. Re-using yesterday's file would be a provenance lie.

**Their content: yes, by reference instead of copy.** Everything large in a package is either a run-level document that already exists once in the run folder, or canonical history that already exists in an immutable, fingerprinted store. Rule R2 (one owner per fact) points the same way: the owner of the macro snapshot is `macro_snapshot.json`; the owner of the bars is the canonical database. The package should reference them, not re-own them.

### Options, lowest risk first

| # | Change | Saving per run | Code touched | Risk |
|---|---|---|---|---|
| 0 | NTFS LZX compression on `data/output/runs/*/packages` (`compact /C /S /EXE:LZX`) | ~70–85 % on disk, no byte changes | none | Negligible; transparent to every reader; slightly slower first read. Immediate mitigation for the three retained sets. |
| A | Replace `macro`, `macro_snapshot`, `macro_quant_packet` in each package with `{path, sha256, as_of_utc}` references to the run-root files; the Vanguard adapter loads them once per run | ~65 % (≈ 2.5 GB) | `build_packages_from_discovery.py`, `inject_macro_into_packages.py`, `run_vanguard_from_packages.py` (macro payload / `regime_snapshot`), `data_contract_validator._has_regime`, `desk_card.py`, two macro QA scripts | Moderate: several readers; provenance stays explicit through the hash. |
| B | Write bars once (`ohlcv_daily`) and drop the `ohlcv`, `daily_df`, `timeseries.ohlcv_daily` aliases; keep `returns_daily` or compute on read | ~17 % | `backfill_timeseries_into_packages.py`; readers already fall back through the alias chain, DCV resolves any alias | Low; a characterisation test must pin which alias each reader lands on. |
| B′ | Do not embed bars at all: reference `{historical_prices.sqlite, dataset_fingerprint, last_bar_date, bar_count}` and let Vanguard read through `canonical_data.history_bridge` | ~24 % | as B plus the Vanguard bar loader | Moderate; requires the canonical store to be immutable per fingerprint (it already stamps `source_dataset_fingerprint`). |
| C | Content-addressed block store: each block (macro doc, bar series, truth packet) written once under its sha256, packages hold references; identical blocks dedupe within and across runs automatically | ~99 % of package bytes; history stored once and grows by one bar per session | new small store + the readers above | Highest engineering effort; the cleanest fit to R2/R7 and to the "reference by hash, never proximity" rule in INT-001 §3. |

Order that respects CLAUDE.md rule 4 (one defect at a time, test first): 0 now; then A with a parity test that Vanguard, trap, trigger and actuarial outputs are byte-identical from reference-only packages on run `20260926_173730` (the set retained for ACK's hypothesis test is the right fixture); then B; C only if A+B leave the per-run cost above what the retention window needs.

## 4. Two follow-ups outside this analysis

- `truth_packet` (224 KB per ticker, 9.7 %) was not opened here; if it re-embeds macro fields per row it belongs in option A.
- The 90-day run retention (`RUNS_RETENTION_DAYS = 90`) multiplies whatever per-run cost remains; with option A alone the retained window falls from ~110 GB to ~40 GB.

No file was modified by this analysis.
