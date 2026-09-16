# Track M1 — Is there money to follow, and can we see it before it moves? (DISCOVERY, RESEARCH_ONLY)
No NORMAL_COMPLETED_SESSION run exists; every result below is on TEST-condition runs and cannot be CLOSED.
**Data source (Rule 10):** historical price store copy `audit/td/AVS-TD-001/db_copies/historical_prices.sqlite` table `ohlcv_daily` (3,618 tickers, 1,268 sessions, 2021-08-23 → 2026-09-10). Regime labels: `data/output/runs/*/macro_snapshot.json` (27 runs; `extras.us_money_index.source_payload`, `sector_rotation.sector_bias_map`, `sector_lead`, `sector_avoid`) and `dropbox/macro/avshunter_us_money_index*.json` + `dropbox/macro/Archive/avshunter_us_money_index*.json` (4 files). Ledger copy `db_copies/decision_outcome_ledger.sqlite` (structure census only). Stored run books (primary `20260911_115904`, comparison `20260910_150045`) read for structure only (field population), never for performance.
**Dependency:** F1–F3 were running in parallel and were not read. The ticker→sector join is **derived by this track** (`probes/p21_M1_sector_map.csv`): most recent Discovery `sector` per ticker across 27 `discovery_candidates_ultimate_*.csv`, else `data/universe/polygon_liquid_universe.csv`, else `UNKNOWN`. Coverage: pipeline universe 1,896/1,907 tickers mapped (11 UNKNOWN; 4 not in store: LSEG, MAIR, REWW, UBS); store 3,292/3,618 mapped; Discovery vs universe-file sector agreement 1.000 on 1,880 overlapping tickers (`probes/p21_M1_universe_out.json`).
Nothing here authorises, sizes, clears or gates a trade. Discovery vocabulary only; no verdicts, no severities.

## Finding table
| Finding ID | CALL | PUT | OTHER | data source | evidence (artefact, field, value) | N | magnitude |
|---|---|---|---|---|---|---|---|
| DISC-F-M1-1 | not direction-split (universe-level) | not direction-split | not direction-split | price store `ohlcv_daily` | `p21_M1_dispersion.csv` window 2024-01-01→2026-09-10, PIPELINE, h=5, stat=std | 670 sessions (median 1,722 tickers/session) | per-session cross-sectional std of 5-session log return p10 0.0551 / p50 0.0678 / p90 0.0869; IQR p50 0.0538; 90–10 p50 0.1211. h=10 std p50 0.0957; h=20 std p50 0.1369. STORE_ALL h=5 std p50 0.0709 |
| DISC-F-M1-2 | not direction-split | not direction-split | not direction-split | price store + derived sector map | `p21_M1_dispersion.csv` group=<sector>, h=5, stat=std, context window | 670 sessions per sector; sectors with median < 100 constituents flagged in CSV (see table) | within-sector 5-session std p50 ranges 0.0322 (Real Estate) → 0.0805 (Health Care); IT 0.0787; within-sector medians are 47–119% of the all-universe 0.0678 |
| DISC-F-M1-3 | not direction-split | not direction-split | not direction-split | price store + derived sector map | `p21_M1_rs_autocorr.csv` series RS5_EW / RS1_EW / RS5_<SPDR ETF> | 675 sessions × 11 sectors (135 non-overlapping blocks) | RS5 autocorr cross-sector median: lag1 0.793, lag5 −0.041, lag10 −0.002, lag20 0.012; non-overlapping lag5 −0.092, lag20 0.019; RS1 lag1 −0.000 |
| DISC-F-M1-4 | 798/798 rows `usmi_sector_alignment=NEUTRAL` | 458/458 NEUTRAL | 188/188 NEUTRAL (STRANGLE 138, UNRESOLVED 50) | primary run Lab book (structure only) + ledger copy | `final_opportunity_book_20260911_115904.csv`: `usmi_sector_alignment` NEUTRAL 1,444/1,444; `usmi_alignment_priority` fill 0.000; `usmi_alignment_reason` `SECTOR_UNMAPPED` 1,444/1,444 while `gics_sector` fill 1.000; comparison run `usmi_sector_alignment` UNAVAILABLE 1,424/1,424; four-label vocabulary occurrences in all primary-run CSVs: 0; ledger 8,290 events: NEUTRAL 3,358 / UNAVAILABLE 2,958 / null 1,974, no route label | 1,444 rows (primary), 1,424 (comparison), 8,290 ledger events | stored artefacts carry zero per-ticker routing-label information; the macro→ticker join is not testable on stored artefacts and sector had to be reconstructed externally (done, see Dependency) |
| DISC-F-M1-5 | label history: CALL-side 4-label obs 8 (7 mapped) | PUT-side 4-label obs 11 (8 mapped) | — | macro snapshots + dropbox packets | `p21_M1_usmi_labels.csv`: 686 panel rows, 332 distinct; four-label `sector_routing.routing` present only in 2 packets with as-of 2026-09-11 (rev 1 11:07Z, rev 2 11:35Z) → t0 = 2026-09-10 = last store session; USMI packets exist for 3 distinct as-of sessions (09-04, 09-09, 09-11); snapshot bias map spans 13 distinct t0 sessions 2026-07-22 → 2026-09-10 | 19 distinct 4-label route observations; 0 with any forward session | label depth, not label skill: forward-evaluable 4-label observations = 0; largest label×h cell in any family = 51 (LEAD, h=1) |

Trace lines:
- DISC-F-M1-1 — `TRACE: REQ-UNMAPPED | ALG-UNMAPPED | WP-NONE | STAGE-NONE | TRACK-M1 | EVIDENCE-probes/p21_M1_dispersion.csv | N=670`
- DISC-F-M1-2 — `TRACE: REQ-UNMAPPED | ALG-UNMAPPED | WP-NONE | STAGE-NONE | TRACK-M1 | EVIDENCE-probes/p21_M1_dispersion.csv | N=670`
- DISC-F-M1-3 — `TRACE: REQ-UNMAPPED | ALG-UNMAPPED | WP-NONE | STAGE-NONE | TRACK-M1 | EVIDENCE-probes/p21_M1_rs_autocorr.csv | N=675`
- DISC-F-M1-4 — `TRACE: REQ-WP5-01 | ALG-14 | WP-5 | STAGE-NONE | TRACK-M1 | EVIDENCE-final_opportunity_book_20260911_115904.csv:usmi_sector_alignment,usmi_alignment_priority,usmi_alignment_reason; probes/p21_M1_joinability_out.json | N=1444`
- DISC-F-M1-5 — `TRACE: REQ-WP5-01 | ALG-14 | WP-5 | STAGE-NONE | TRACK-M1 | EVIDENCE-probes/p21_M1_usmi_labels.csv | N=686`

## Dispersion (distribution across sessions, not an average)
Probe `probes/p21_M1_dispersion.py` → `probes/p21_M1_dispersion.csv` (summary), `p21_M1_dispersion_sessions.csv` (per-session panel), `p21_M1_dispersion_thesis_sets.csv`. Forward h-session log return from close t to close t+h; a session needs ≥ 20 tickers with a t+h close.

**Overall, context window 2024-01-01 → 2026-09-10**
| universe | h | std p10 | std p50 | std p90 | IQR p10 / p50 / p90 | 90–10 p10 / p50 / p90 | n sessions | tickers/session |
|---|---|---|---|---|---|---|---|---|
| PIPELINE | 1 | 0.0233 | 0.0295 | 0.0400 | 0.0174 / 0.0224 / 0.0319 | 0.0401 / 0.0510 / 0.0709 | 674 | 1,723 |
| PIPELINE | 5 | 0.0551 | 0.0678 | 0.0869 | 0.0424 / 0.0538 / 0.0775 | 0.0982 / 0.1211 / 0.1719 | 670 | 1,722 |
| PIPELINE | 10 | 0.0786 | 0.0957 | 0.1212 | 0.0641 / 0.0784 / 0.1131 | 0.1462 / 0.1792 / 0.2473 | 665 | 1,722 |
| PIPELINE | 20 | 0.1133 | 0.1369 | 0.1688 | 0.0943 / 0.1182 / 0.1594 | 0.2151 / 0.2677 / 0.3495 | 655 | 1,721 |
| STORE_ALL | 1 | 0.0245 | 0.0311 | 0.0452 | 0.0175 / 0.0223 / 0.0313 | 0.0404 / 0.0512 / 0.0703 | 674 | 1,783 |
| STORE_ALL | 5 | 0.0574 | 0.0709 | 0.0977 | 0.0424 / 0.0537 / 0.0758 | 0.0990 / 0.1217 / 0.1703 | 670 | 1,782 |
| STORE_ALL | 10 | 0.0819 | 0.0995 | 0.1345 | 0.0639 / 0.0783 / 0.1111 | 0.1476 / 0.1809 / 0.2464 | 665 | 1,780 |
| STORE_ALL | 20 | 0.1172 | 0.1436 | 0.1762 | 0.0952 / 0.1184 / 0.1580 | 0.2176 / 0.2690 / 0.3458 | 655 | 1,776 |

**Recent window 2026-07-23 → 2026-09-10** (the stored-run period): all cells `INSUFFICIENT_POWER` — PIPELINE h=5 n=30 sessions (std p50 0.0704), h=10 n=25 (0.0960), h=20 n=15 (0.1444); STORE_ALL h=5 n=30 (0.0840).

**Within sector, PIPELINE, context window, std p50 by h** (670 sessions at h=5; constituent median in brackets; probe flags constituents < 100 as `INSUFFICIENT_POWER(n_tickers_med=…)` in the CSV)
| sector | h=1 | h=5 | h=10 | h=20 | IQR p50 h=5 | 90–10 p10/p50/p90 h=5 |
|---|---|---|---|---|---|---|
| Health Care [267] | 0.0331 | 0.0805 | 0.1144 | 0.1650 | 0.0661 | 0.1163 / 0.1456 / 0.1950 |
| Information Technology [325] | 0.0345 | 0.0787 | 0.1130 | 0.1644 | 0.0636 | 0.1099 / 0.1448 / 0.2200 |
| Materials [87, flagged] | 0.0265 | 0.0619 | 0.0893 | 0.1282 | 0.0591 | 0.0869 / 0.1247 / 0.1911 |
| Industrials [214] | 0.0255 | 0.0596 | 0.0866 | 0.1259 | 0.0466 | 0.0781 / 0.1061 / 0.1582 |
| Communication Services [56, flagged] | 0.0248 | 0.0584 | 0.0845 | 0.1262 | 0.0548 | 0.0880 / 0.1165 / 0.1712 |
| Energy [133] | 0.0255 | 0.0583 | 0.0832 | 0.1188 | 0.0520 | 0.0828 / 0.1138 / 0.1649 |
| Consumer Discretionary [194] | 0.0235 | 0.0536 | 0.0766 | 0.1120 | 0.0526 | 0.0896 / 0.1102 / 0.1521 |
| Consumer Staples [68, flagged] | 0.0192 | 0.0470 | 0.0662 | 0.0979 | 0.0413 | 0.0666 / 0.0904 / 0.1338 |
| Financials [174] | 0.0200 | 0.0470 | 0.0671 | 0.0941 | 0.0366 | 0.0573 / 0.0790 / 0.1107 |
| Utilities [46, flagged] | 0.0151 | 0.0354 | 0.0514 | 0.0739 | 0.0219 | 0.0377 / 0.0542 / 0.0865 |
| Real Estate [90, flagged] | 0.0137 | 0.0322 | 0.0460 | 0.0654 | 0.0306 | 0.0486 / 0.0644 / 0.0887 |

**Direction split (CALL / PUT / OTHER thesis sets on run reference sessions)** — `p21_M1_dispersion_thesis_sets.csv`. One session per run, store ends 2026-09-10, so only h=1 is computable and every cell is `INSUFFICIENT_POWER(n_sessions=1)`: e.g. ref 2026-09-09 (run 20260910_150045) CALL std 0.0224 (791 tickers), PUT 0.0247 (451), OTHER STRANGLE 0.0203 (135) / UNRESOLVED 0.0251 (47); h ≥ 5 `DATA_UNAVAILABLE(fwd_sessions_available ≤ 3)`; primary run ref 2026-09-10 has 0 forward sessions.

## Persistence (sector relative strength, 2024-01-01 → 2026-09-10)
Probe `probes/p21_M1_rs_autocorr.py` → `probes/p21_M1_rs_autocorr.csv`. RS5(t) = sector EW 5-session log return − all-mapped EW 5-session log return; daily |log return| ≥ 0.5 dropped. Cross-sector median [min, max] over 11 GICS sectors; 675 sessions each. Overlapping 5-session windows force lag 1–4 autocorrelation mechanically (shared 4/5 of the window); the non-overlapping column samples every 5th session (135 blocks; lags 1/2/4 blocks = 5/10/20 sessions).

| series | lag 1 | lag 5 | lag 10 | lag 20 | non-overlap 5 | non-overlap 10 | non-overlap 20 |
|---|---|---|---|---|---|---|---|
| PIPELINE RS5 EW | 0.793 [0.774, 0.820] | −0.041 [−0.109, 0.061] | −0.002 [−0.058, 0.136] | 0.012 [−0.125, 0.089] | −0.092 [−0.138, 0.034] | 0.072 [−0.018, 0.174] | 0.019 [−0.159, 0.175] |
| STORE_ALL RS5 EW | 0.792 [0.772, 0.822] | −0.037 [−0.095, 0.054] | −0.011 [−0.064, 0.120] | 0.002 [−0.145, 0.083] | −0.074 [−0.131, 0.037] | 0.051 [−0.017, 0.161] | 0.019 [−0.169, 0.177] |
| SPDR ETF RS5 vs store EW | 0.789 [0.759, 0.809] | −0.067 [−0.133, 0.001] | −0.032 [−0.131, 0.108] | 0.055 [−0.122, 0.122] | −0.064 [−0.198, 0.018] | −0.020 [−0.197, 0.134] | 0.034 [−0.157, 0.217] |
| PIPELINE RS1 EW | −0.000 [−0.060, 0.072] | 0.013 [−0.040, 0.063] | −0.022 [−0.056, 0.077] | 0.021 [−0.094, 0.100] | — | — | — |

Sector extremes (PIPELINE RS5, lag 20): Consumer Discretionary −0.125, Industrials −0.100, Consumer Staples 0.089. Approximate 95% band for a zero autocorrelation: ±0.075 at 675 sessions, ±0.17 at 135 blocks.

## Regime layer vs realised forward sector returns (1–15 sessions)
Probe `probes/p21_M1_usmi_labels.py` → `probes/p21_M1_usmi_labels.csv` (panel), `p21_M1_usmi_label_eval.csv` (every label × h = 1..15), `p21_M1_usmi_leadlag.csv`. t0 = last store session before the as-of date (as-of on/after 20:00 UTC → that session). Forward measure = sector EW log return minus all-mapped EW (relative); absolute sector return also in CSV. Hit: CALL side / TAILWIND / LEAD → relative > 0; PUT side / HEADWIND / AVOID → relative < 0. Identical (t0, route, label, sector) observations repeated across runs counted once. Route → GICS mapping for USMI routes is a keyword map written in the probe (not the pipeline's `_route_key`); 40 of 686 panel rows (21 of 332 distinct observations: four-label 4/19, priority lists 8/49, lead/avoid 9/108 non-SPDR tickers such as QQQ/IWM) are UNMAPPED (broad index, small caps, generic RS/cyclicals) and excluded.

**Vocabulary the dated packets actually carry**
| family | source path | as-of sessions present | labels |
|---|---|---|---|
| A four-label routing | `source_payload.options_monetisation.sector_routing.routing` | 2026-09-11 only (2 packet revisions; run 20260911_115904 + dropbox current and `…old1109pm`) | PRIORITY_UPGRADE, ADVERSE_REGIME_RS_REQUIRED, PRIORITY_WATCH, NOT_YET_CONFIRMED |
| B USMI priority lists | v2 `options_monetisation.long_call_priority/long_put_priority`; v1 `sector_rotation.*_sectors` | 2026-09-04 (v1), 2026-09-09, 2026-09-11 | CALL_PRIORITY, PUT_PRIORITY |
| C snapshot bias map | `macro_snapshot.sector_rotation.sector_bias_map` | 13 distinct t0, 2026-07-22 → 2026-09-10 | TAILWIND, HEADWIND, NEUTRAL, MIXED |
| D snapshot lead/avoid | `macro_snapshot.sector_lead/sector_avoid` | same 13 | LEAD, AVOID |

**Hit rate and mean relative forward return per label (every cell n < 100)**
| family | label | side | h=1 n / hit / mean | h=5 n / hit / mean | h=10 n / hit / mean | h=15 n / hit / mean | state |
|---|---|---|---|---|---|---|---|
| A | PRIORITY_UPGRADE | PUT | 0 | 0 | 0 | 0 | DATA_UNAVAILABLE(n=0; t0 2026-09-10, 0 forward sessions) |
| A | ADVERSE_REGIME_RS_REQUIRED | CALL 2 / PUT 1 obs | 0 | 0 | 0 | 0 | DATA_UNAVAILABLE(n=0) |
| A | PRIORITY_WATCH | CALL 4 / PUT 3 obs | 0 | 0 | 0 | 0 | DATA_UNAVAILABLE(n=0) |
| A | NOT_YET_CONFIRMED | CALL 2 / PUT 1 obs | 0 | 0 | 0 | 0 | DATA_UNAVAILABLE(n=0) |
| B | CALL_PRIORITY | CALL | 13 / 0.538 / +0.0051 | 0 | 0 | 0 | INSUFFICIENT_POWER(n=13) |
| B | PUT_PRIORITY | PUT | 9 / 0.667 / −0.0039 | 0 | 0 | 0 | INSUFFICIENT_POWER(n=9) |
| C | TAILWIND | CALL | 45 / 0.467 / +0.0005 | 37 / 0.351 / −0.0032 | 27 / 0.481 / −0.0034 | 24 / 0.458 / −0.0005 | INSUFFICIENT_POWER(n≤45) |
| C | HEADWIND | PUT | 46 / 0.674 / −0.0015 | 30 / 0.433 / +0.0021 | 22 / 0.409 / +0.0017 | 19 / 0.579 / −0.0047 | INSUFFICIENT_POWER(n≤46) |
| C | NEUTRAL | OTHER | 45 / — / +0.0003 | 30 / — / −0.0012 | 25 / — / −0.0079 | 21 / — / −0.0027 | INSUFFICIENT_POWER(n≤45) |
| C | MIXED | OTHER | 9 / — / +0.0008 | 4 / — / +0.0091 | 4 / — / +0.0161 | 3 / — / +0.0358 | INSUFFICIENT_POWER(n≤9) |
| D | LEAD | CALL | 51 / 0.510 / +0.0010 | 38 / 0.368 / −0.0029 | 28 / 0.464 / −0.0048 | 25 / 0.440 / −0.0039 | INSUFFICIENT_POWER(n≤51) |
| D | AVOID | PUT | 40 / 0.675 / −0.0010 | 27 / 0.407 / +0.0035 | 19 / 0.421 / +0.0067 | 16 / 0.563 / +0.0018 | INSUFFICIENT_POWER(n≤40) |

Observations within a t0 share the session (9–13 distinct t0 per cell), so the effective n is below the row n. These numbers are reported, not presented as results (Rule 12).

## Lead / lag (labels with n ≥ 20 at h=5; all INSUFFICIENT_POWER)
Signed so that positive = move in the label's direction. Prior = relative return over the 5 / 10 sessions ending at t0.
| family | label | n (distinct t0) | signed prior 10 | signed prior 5 | share prior-5 in label direction | signed fwd 1 | signed fwd 5 | share fwd-5 in label direction | signed fwd 10 (n) | corr(prior5, fwd5) | state |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C | TAILWIND (CALL) | 37 (9) | +0.0137 | +0.0094 | 0.676 | +0.0001 | −0.0032 | 0.351 | −0.0034 (27) | −0.061 | INSUFFICIENT_POWER(n=37) |
| C | HEADWIND (PUT) | 30 (9) | +0.0179 | +0.0094 | 0.733 | +0.0007 | −0.0021 | 0.433 | −0.0017 (22) | 0.129 | INSUFFICIENT_POWER(n=30) |
| D | LEAD (CALL) | 38 (9) | +0.0138 | +0.0095 | 0.684 | +0.0007 | −0.0029 | 0.368 | −0.0048 (28) | −0.049 | INSUFFICIENT_POWER(n=38) |
| D | AVOID (PUT) | 27 (9) | +0.0180 | +0.0128 | 0.778 | −0.0005 | −0.0035 | 0.407 | −0.0067 (19) | 0.119 | INSUFFICIENT_POWER(n=27) |
Four-label (A) and priority-list (B) families: no label reaches n ≥ 20 with a 5-session forward window → lead/lag `DATA_UNAVAILABLE`.

## Joinability statement
The macro→ticker routing join is **not testable on stored artefacts**; sector had to be **reconstructed externally**, and this track did so. Evidence (`probes/p21_M1_joinability.py` → `p21_M1_joinability_out.json`, structure only):
- Primary `final_opportunity_book_20260911_115904.csv` (1,444 rows, 0 duplicate tickers): `gics_sector` / `gics_sector_norm` / `sector` fill 1.000 (17 values), yet `usmi_sector_alignment` = NEUTRAL 1,444/1,444, `usmi_alignment_priority` fill 0.000, `usmi_alignment_reason` = `SECTOR_UNMAPPED` 1,444/1,444, `macro_sector_alignment` = UNMAPPED 1,444/1,444. Same on `lab_signal_book_v3.csv` (19/19).
- Primary `morning_validated_trades_…csv` and `execution_gated_…csv` (1,444 rows): no `gics_sector` column; `sector` fill 0.000; `sector_etf` fill 0.8435 (1,218/1,444); no `usmi_sector_alignment` column.
- Comparison `final_opportunity_book_20260910_150045.csv` (1,424): `usmi_sector_alignment` UNAVAILABLE 1,424/1,424; priority and reason fill 0.000; no morning / execution_gated artefacts.
- The four routing labels occur 0 times in any primary-run CSV; `usmi_routing_key` column absent everywhere.
- Ledger copy (8,290 events): `usmi_sector_alignment` NEUTRAL 3,358, UNAVAILABLE 2,958, null 1,974; no route key or four-label value.
- Only 2026-09-11 packets carry `sector_routing.routing`; with the price store ending 2026-09-10, even a working join on the primary run would have 0 realised forward sessions.
Reconstruction used: derived ticker→GICS map (Dependency line), SPDR sector ETF cross-check, probe-local route→GICS keyword map.

## Findings (with what each does NOT establish)
**DISC-F-M1-1 — Cross-sectional dispersion.** Pipeline universe, 670 sessions (2024-01-01 → 2026-09-10): 5-session std p10/p50/p90 = 0.0551/0.0678/0.0869; 10-session p50 0.0957; 20-session p50 0.1369; IQR p50 at 5 sessions 0.0538. Not direction-split (CALL/PUT/OTHER thesis-set dispersion is INSUFFICIENT_POWER, n_sessions = 1).
*Does not establish:* that any of this dispersion can be captured, predicted, or monetised through options; it applies today's pipeline membership back to 2024 (survivorship); std includes bad prints and splits (no clipping in this probe; IQR and 90–10 are the robust readings); the stored-run period itself (n=30 sessions) is underpowered.
TRACE: REQ-UNMAPPED | ALG-UNMAPPED | WP-NONE | STAGE-NONE | TRACK-M1 | EVIDENCE-probes/p21_M1_dispersion.csv | N=670

**DISC-F-M1-2 — Within-sector dispersion.** 5-session within-sector std p50 ranges 0.0322 (Real Estate) to 0.0805 (Health Care); Health Care and IT exceed the all-universe median (0.0678), Real Estate, Utilities, Financials and Staples are below 0.05. Five sectors have median constituents < 100 and are flagged in the CSV.
*Does not establish:* that sector membership explains returns, that sector-neutral selection beats the universe, or anything about GICS mapping quality beyond the 1.000 agreement of two internal sources (no external GICS reference was used).
TRACE: REQ-UNMAPPED | ALG-UNMAPPED | WP-NONE | STAGE-NONE | TRACK-M1 | EVIDENCE-probes/p21_M1_dispersion.csv | N=670

**DISC-F-M1-3 — Sector RS persistence.** Beyond the overlap horizon, 5-session sector RS autocorrelation is near zero: cross-sector median lag5 −0.041, lag10 −0.002, lag20 0.012; non-overlapping lag5 −0.092 (−0.074 store, −0.064 ETF). Lag1 0.79 is the mechanical overlap of 5-session windows; 1-session RS lag1 is −0.000.
*Does not establish:* absence of persistence at industry/theme level (routes like AIRLINES or AI_SEMICONDUCTOR are finer than GICS), at other windows (e.g. 20- or 60-session RS), conditionally on regime, or non-linear/threshold persistence; it is EW composites, not cap-weighted.
TRACE: REQ-UNMAPPED | ALG-UNMAPPED | WP-NONE | STAGE-NONE | TRACK-M1 | EVIDENCE-probes/p21_M1_rs_autocorr.csv | N=675

**DISC-F-M1-4 — Stored join carries no routing information.** Primary Lab book CALL 798, PUT 458, OTHER 188 rows all `usmi_sector_alignment=NEUTRAL`, `usmi_alignment_reason=SECTOR_UNMAPPED`, `usmi_alignment_priority` empty, with `gics_sector` filled on every row; comparison run all UNAVAILABLE; four-label vocabulary absent from every primary-run CSV.
*Does not establish:* why the join produced NEUTRAL (implementation assessment belongs to Track F); whether the post-remediation code (commit cc509cb, 12 Sep) behaves differently — both runs are pre-remediation (00baa2b); anything about label skill.
TRACE: REQ-WP5-01 | ALG-14 | WP-5 | STAGE-NONE | TRACK-M1 | EVIDENCE-final_opportunity_book_20260911_115904.csv:usmi_sector_alignment,usmi_alignment_reason,usmi_alignment_priority | N=1444

**DISC-F-M1-5 — Label history is too short to measure routing skill.** The four-label routing exists for one as-of session (2026-09-11, 2 revisions, 19 distinct route observations, 15 GICS-mappable) with 0 forward sessions in the store. USMI priority lists exist for 3 as-of sessions; snapshot bias/lead/avoid labels for 13 distinct t0. Largest label×h cell in any family: n = 51. At the observed density, n ≥ 100 at h = 5 would need roughly: PRIORITY_WATCH ≈ 17 packet sessions, PRIORITY_UPGRADE ≈ 20, ADVERSE_REGIME_RS_REQUIRED ≈ 34, NOT_YET_CONFIRMED ≈ 100 (1 mapped observation per packet), each followed by ≥ 5 stored sessions; TAILWIND/LEAD ≈ 25–30 sessions — and more for effective n, because observations cluster within a session.
*Does not establish:* that routing labels have or lack predictive value; the proxy families C/D are snapshot sector-rotation outputs, not USMI routing, and their hit rates (0.35–0.67, all INSUFFICIENT_POWER) are not a USMI measurement.
TRACE: REQ-WP5-01 | ALG-14 | WP-5 | STAGE-NONE | TRACK-M1 | EVIDENCE-probes/p21_M1_usmi_labels.csv | N=686

## Deviations (observations, no severity)
- **M1-OBS-1** REQ-WP5-01 acceptance text says `SECTOR_UNMAPPED` occurs only for tickers with no GICS; primary Lab book shows `SECTOR_UNMAPPED` on 1,444/1,444 rows with `gics_sector` filled on 1,444/1,444 (`final_opportunity_book_20260911_115904.csv`). Pre-remediation run; Track F owns the assessment.
- **M1-OBS-2** `macro_ticker_context_v2` lists `usmi_routing_key`; no stored artefact column of that name (consistent with DEV-06).
- **M1-OBS-3** Comprehension item 13 left open whether the stored morning CSV carries `gics_sector`: it does not — `morning_validated_trades_20260911_115904.csv` has no `gics_sector` column, `sector` fill 0.000, `sector_etf` fill 0.8435.
- **M1-OBS-4** Three coexisting sector-preference sets on the same primary row with different contents: `leading_sectors` ["Energy"] / `avoid_sectors` [Cons. Disc., Industrials, Materials, Real Estate] (1,444/1,444), `macro_sector_lead` "XLE; XLF; XLK" / `macro_sector_avoid` "XLI; XLY; XLB; XLRE; XLP" (1,444/1,444), and the USMI route table; `ticker_sector_alignment` CONFLICTED 1,064 / ALIGNED 378 / NEUTRAL 2 in `morning_validated_trades`.
- **M1-OBS-5** Macro snapshots reused across runs without refresh: `as_of_utc 2026-08-29T08:12:43Z` in 4 runs (20260830_071747 → 20260831_010309); `2026-09-03T23:04:14` in 3 runs (20260904_004338 → 20260905_151448); `2026-08-21T07:14:13Z` in 3 runs; `2026-08-14T08:55:36Z` in 3 runs (`scratch _scratch_m1/label_source_census.csv`).
- **M1-OBS-6** The `sector_routing.routing` dict first appears in packets with as-of 2026-09-11; the 09-09 packet (runs 20260909_071646, 20260910_150045) and the v1 09-04 packet (run 20260906_213931) carry priority lists only, so ALG-14's routing source path did not exist in the packets those runs consumed.
- **M1-OBS-7** `dropbox/macro/Archive/avshunter_us_money_index1109.json` carries `analysis_window.as_of_utc = 2026-09-09T06:27:00Z` (file mtime 9 Sep); the name does not match the content date. Recorded because label dating relies on in-file as-of, not filenames.

## Premise notes (no severity, no recommendation)
- **PN-M1-1** ALG-14 builds the route key from GICS sector with industry-keyword overrides and routes are phrased as relative-strength states ("WEAK_TECH", "ADVERSE_REGIME_RS_REQUIRED", "IF_XLE_CONFIRMS"). Measured: 5-session GICS sector RS autocorrelation at lags 5/10/20 = −0.041 / −0.002 / 0.012 (non-overlapping lag5 −0.092), n = 675 sessions × 11 sectors. Gap: a sector-level RS state observed over the prior week carries near-zero linear information about the next 5–20 sessions of sector RS.
- **PN-M1-2** The regime question (§4.1) and ALG-14 express the route at sector grain; the packets' routes are theme grain. Measured: 21 of 332 distinct label observations (8 of 49 priority-list observations; 4 of 19 four-label observations, routes IWM_SMALL_CAPS_PUT, SPY_QQQ_PUT, BROAD_INDEX_CALL) map to no GICS sector under a keyword map, and mapped routes such as AIRLINES_PUT, HOMEBUILDERS_REITS_PUT or DEFENCE_CALL are proxied by whole-sector composites (Industrials, Cons. Disc. / Real Estate, Industrials). Gap: the measured quantity (GICS sector return) is broader than the labelled quantity (theme return) for every mapped route except whole-sector ones.
- **PN-M1-3** Dispersion vs sector: within-sector 5-session std p50 is 47–119% of the universe std (0.0322–0.0805 vs 0.0678), i.e. most of the cross-sectional spread remains inside sectors. Recorded against the design's use of sector routing as the macro→ticker bridge; gap = within-sector median std / universe median std, cross-sector median ≈ 0.86 (0.0583/0.0678).

## Not tested / blocked
- Four-label routing hit rate, mean forward return and lead/lag: `DATA_UNAVAILABLE` — labels dated 2026-09-11, store ends 2026-09-10 (0 forward sessions). Requires price sessions after 2026-09-10 and more dated packets.
- Pipeline's own join output against returns: `DATA_UNAVAILABLE` — stored rows carry NEUTRAL/UNAVAILABLE only.
- Direction-split dispersion over many sessions: `INSUFFICIENT_POWER(n_sessions = 1 per run)`; directed thesis sets exist only for 5 runs 2026-09-05 → 2026-09-11.
- Industry/theme-level persistence: not measured (industry vocabulary is 407 SIC-style strings, `p21_M1_industry_vocab.csv`; no theme map exists).

## Expectation vs actual (expectations.md, M1 row)
| expected (E) | actual (A) | gap |
|---|---|---|
| Cross-sectional 5d return std per session 4–7% | p50 6.78% (pipeline) / 7.09% (store); p10 5.51%, p90 8.69% | median inside range (store at upper edge); upper decile 1.7–2.8 pp above |
| Sector RS autocorrelation lag 1: 0.1–0.3 | 0.793 for overlapping RS5 (mechanical); −0.000 for RS1 | overlapping series +0.49 above range; 1-session series −0.10 below range |
| lag 20 ≈ 0 | 0.012 (store 0.002; non-overlap 0.019) | matches |
| USMI label hit rates 45–55%, INSUFFICIENT_POWER for most labels | four-label: n = 0 for every label (DATA_UNAVAILABLE); proxy families 0.35–0.67, all INSUFFICIENT_POWER (max n 51) | stricter than expected: not "most" but all labels, and no four-label hit rate exists at all |
| Join requires external sector reconstruction | confirmed; reconstructed (1,896/1,907 pipeline tickers mapped) | matches |

## State log lines
```
step,state,n,duration,note
M1.sector_join_derived,COMPLETE,1907,104s,"derived ticker->GICS map (F1-F3 not read); pipeline 1896 mapped, 11 UNKNOWN; p21_M1_universe.py (reused from interrupted worker)"
M1.dispersion_overall,COMPLETE,670,28s,"2024-01-01..2026-09-10 pipeline h5 std p50 0.0678; recent window n=30 INSUFFICIENT_POWER; p21_M1_dispersion.py"
M1.dispersion_sector,COMPLETE,670,28s,"11 GICS sectors; 5 sectors <100 constituents flagged; p21_M1_dispersion.csv"
M1.dispersion_direction,INSUFFICIENT_POWER,1,28s,"CALL/PUT/OTHER thesis sets n_sessions=1 per run; h>=5 DATA_UNAVAILABLE; p21_M1_dispersion_thesis_sets.csv"
M1.persistence,COMPLETE,675,20s,"RS5 autocorr median lag1 0.793 lag5 -0.041 lag10 -0.002 lag20 0.012; p21_M1_rs_autocorr.csv"
M1.regime_four_label,DATA_UNAVAILABLE,0,35s,"labels only in 2026-09-11 packets; store ends 2026-09-10; p21_M1_usmi_labels.csv"
M1.regime_proxy_labels,INSUFFICIENT_POWER,51,35s,"USMI priority lists + snapshot bias/lead/avoid; max cell n=51; p21_M1_usmi_label_eval.csv"
M1.lead_lag,INSUFFICIENT_POWER,38,35s,"4 proxy labels n>=20; four-label none; p21_M1_usmi_leadlag.csv"
M1.joinability,COMPLETE,1444,61s,"stored join NEUTRAL/UNAVAILABLE only; external reconstruction required and done; p21_M1_joinability_out.json"
```
