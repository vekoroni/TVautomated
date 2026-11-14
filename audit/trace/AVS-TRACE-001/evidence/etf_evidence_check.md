# AVS-TRACE-001: ETF fix package (section 4) evidence check

Written 14 Nov 2026. Read-only review. No code, config or data changed; no pipeline, Lab or provider call. Databases opened with `mode=ro`. `data\journal\trade_journal.db` not opened.

Verdicts: CONFIRMED / CORRECTED / PARTLY / NOT FOUND. Missing evidence is not a pass.

## Method used throughout: how ETFs were identified

- The decision ledger has no ETF flag (63 columns, none for asset type).
- ETF set used here = `data\universe\polygon_liquid_universe_security_master_v1.csv`, column `instrument_type` containing "ETF" (85 tickers), plus ARKG, SQQQ, TQQQ (scanner-added tickers that are in the ledgers but not in the universe file; added by hand). Total 88 tickers.
- `SPX` and `SPXW` (type INDEX) are excluded. GOOG is the fourth scanner-added ticker and is a stock.
- Cross-check: the legacy `data\universe\polygon_liquid_universe.csv` marks 85 rows with `sector` in {ETF, Equity Inverse ETF, Volatility, Rates / Bonds ETF}. It differs from the security master by two tickers (XHB, XOVR).
- The draft's own ETF list could not be found (see WHY), so its counts could not be reproduced.

## WHY paragraph — CORRECTED (ETF counts) / CONFIRMED (hit rates)

Files: `data\scratch\workaround\decision_ledger_2026-10-14.csv` (2,321 rows) joined to `decision_ledger_2026-10-14_outcomes.csv` on `ledger_id`; `decision_ledger_2026-10-14_summary.csv`.

| Draft claim | Measured | Verdict |
|---|---|---|
| About 40 ETFs per ledger (1.7% of rows) | 66 ETF rows of 2,321 = 2.84% on 14 Oct (63 = 2.71% from the security master alone). Across the nine ledgers 12 Oct to 12 Nov: 60 to 64 master ETFs per ledger (2.63% to 2.79%), plus 3 scanner-added | CORRECTED |
| 24 of 36 ETFs with arrival over 60 sessions | 33 of 65 with a q50 (50.8%); 1 row has no q50 (SPXS). Buckets: 1–3 sessions 1, 4–10 11, 11–20 8, 21–60 12, >60 33 | CORRECTED |
| 1 resolved ETF outcome (a stop) | 6 resolved, all STOP, 0 TARGET: VOOG, XOVR, IGV, IYW, IVW, SQQQ. Other 60: 32 OPEN, 28 NOT_TRIGGERED. (2 ETFs reached the half target first: TLT, XLV) | CORRECTED |
| All names: 1–3 sessions 83%, 4–10 78%, >60 5% | 38/46 = 82.6%, 57/73 = 78.1%, 1/22 = 4.5% (`_summary.csv` rows `realisation`; recomputed from the outcomes file, same) | CONFIRMED |
| "2 sessions tracked, one date" | `sessions_available` = 2 for 2,317 rows, 1 for 4; `tracker_version` track_outcomes_v2; last session 2026-10-15 | CONFIRMED |

Notes:
- The rates are target share of **resolved** rows, not of all rows. Resolved n is small: 46, 73 and 22.
- Subsets tried to reproduce 36/24: `money == UNMAPPED` gives 48 rows, 23 over 60; ticker equal to its own `sector_etf` gives 62 rows, 32 over 60; triggered ETFs only gives 38 rows, 17 over 60. None gives 36/24/1.
- Searched for the draft's hand list: `data\scratch\workaround\*.py`, `*.ps1` (only `quickkill.py:21` SECTOR_ETFS, 11 SPDRs), `macro_board\config\macro_board_config_v1.json` (focus 4, sectors 11, industries 15, review 11). NOT FOUND.

## E1 — CORRECTED

Claim: "Ledger has no ETF flag; classification done by a hand list."

- Ledger: CONFIRMED no flag. Columns of `decision_ledger_2026-11-12.csv` (63) hold `sector_etf` and `money` only.
- Universe: an instrument-type field **already exists** but nothing reads it.
  - `data\universe\polygon_liquid_universe_security_master_v1.csv`, column `instrument_type`, 3,320 rows: EQUITY 3,233; INDUSTRY_ETF 21; EQUITY_INDEX_ETF 15; SECTOR_ETF 11; FIXED_INCOME_ETF 8; COMMODITY_ETF 5; FACTOR_ETF 5; COUNTRY_ETF 5; LEVERAGED_VOL_ETF 4; REGIONAL_ETF 4; THEMATIC_ETF 2; ETF_OTHER 2 (QQQ, XOVR); INDEX 2; CRYPTO_ETF 1; LEVERAGED_INVERSE_ETF 1 (SPXS); LEVERAGED_BOND_ETF 1 (TMF).
  - Grep `security_master` over `*.py, *.ps1, *.json, *.md` outside `data\`: 0 files. The file is not consumed by any code.
  - Typing gaps in it: QQQ is ETF_OTHER, not an index ETF; VXX and VIXY are ETNs/unleveraged but typed LEVERAGED_VOL_ETF; there is no ETN type.
  - Live universe `data\universe\polygon_liquid_universe.csv` (5 columns) carries a placeholder `sector` = "ETF" (82 rows) + "Equity Inverse ETF" 1, "Volatility" 1, "Rates / Bonds ETF" 1.
  - Run universe `data\output\runs\20261111_231951\universe\scanner_augmented_universe_20261111_231951.csv`: same 5 columns; 5 rows have every field empty (scanner-added; they include GOOG, SQQQ, ARKG; the full five were not listed).
- Lab publication (run 20261111_231951): `intelligence_lab\review_projection\manifest.json` `card_fields` (145): only `sector` and `sector_etf` relate; no asset_type / is_etf / instrument_type.
- Lab hand-off `data\scratch\workaround\handoff\lab_2026-11-12\handoff.csv` (173 columns): `sector` value "ETF" on 57 rows plus four one-off labels ("Rates / Bonds ETF", "Equity Inverse ETF", "Volatility", "Consumer Discretionary (ETF)") and 4 blank. So 61 of the 65 ETF rows can be picked out by the sector placeholder; ARKG, SQQQ, TQQQ are blank and XOVR reads "Communication / Tech".
- Hand lists in code (no single owner): `avshunter_discovery_ULTIMATE.py:1148` (`_TICKER_OVERRIDES`, FXI → "ETF"); `data\scratch\workaround\quickkill.py:21` (SECTOR_ETFS) and `:118` ("ETF_OR_UNMAPPED"); `macro_board\config\macro_board_config_v1.json` (`focus_tickers`, `rotation.sectors`, `rotation.industries`, `review.instruments`); research lists `Enhancements\structural_edge\supplement_short_vol.py:14`, `Enhancements\direction_evidence\short_horizon_direction_study.py:29`, `Enhancements\macro_board_replay\replay_macro_board.py:44`; `audit\td\AVS-TD-001\probes\p21_M1_dispersion.py:21` (NON_SECTORS).

Correction for the package: the change is "carry the existing `instrument_type` to the ledger and Lab card, fix its typing (QQQ, ETNs, leveraged/inverse, scanner-added tickers)", not "add a field from nothing".

## E2 — CORRECTED

Claim: "24 of 36 ETFs > 60 sessions on 14 Oct."

| Source | ETF rows | q50 known | q50 ≤ 20 | 21–60 | > 60 |
|---|---|---|---|---|---|
| 14 Oct ledger (`q50_sessions`) | 66 | 65 | 20 (30.8%) | 12 | 33 (50.8%) |
| 12 Nov Lab hand-off, run 20261111_231951 (`anticipated_sessions_q50`) | 65 of 2,132 (3.05%) | 62 | 15 (24.2%) | 20 | 27 (43.5%) |

- Hand-off: `data\scratch\workaround\handoff\lab_2026-11-12\handoff.csv`; `receipt.json` gives run_id 20261111_231951, session 2026-11-12, Lab revision f70092078e3f4a548955a08cbec131f6.
- 3 hand-off ETF rows have no q50 (SPXS, VIXY, VXX): `anticipated_time_basis` = GOVERNED_WINDOW_NO_DURATION_EVIDENCE.
- Timeframe of the ETF thesis event: 14 Oct ledger 1mo 24, 1w 20, 1d 19; hand-off `thesis_event_timeframe` 1mo 27, 1d 19, 1w 19. Supports "weekly/monthly structure".
- Lane B window flag on the hand-off: IN_WINDOW 14, OUTSIDE_WINDOW 48, NOT_ASSESSED 3.
- The draft acceptance "≥ 80% of ETF rows with q50 ≤ 20" starts from 24% to 31%, not from 33% (12 of 36).

## E3 — PARTLY (date confirmed; row count is one number, not a range)

File: `data\scratch\workaround\lessons\fix_inbox\2026-10-23_qqq_exclusion.md:1`.

- "READY_OLD_EVENT from 24 Apr": CONFIRMED. `decision_ledger_2026-10-22.csv` QQQ and SPY: state READY_OLD_EVENT, readiness READY_FOR_HUMAN_REVIEW, `readiness_event_date` 2026-04-24, timeframe 1w, focus_v3 False, q50 205 / q80 450. Same on 14 Oct.
- "469–470 rows dropped": CORRECTED. 469 READY_OLD_EVENT rows on the 22 Oct ledger, 0 of them focus_v3. 470 is a different number: the count of focus_v3 theses the options tool priced (the inbox line says "470 theses, all focus_v3"). Measured: READY_OLD_EVENT 469, focus_v3 True 470.
- Other dates: READY_OLD_EVENT rows 478 (14 Oct), 358 (11 Nov), 353 (12 Nov); none focus_v3 on any date.
- State today (12 Nov ledger): SPY is WAIT_TRIGGER_1ATR, 1d, focus_v3 True, q50 18; QQQ and DIA are WAIT_TRIGGER_FAR, 1mo, focus_v3 False, q50 231; IWM WAIT_TRIGGER_0.5ATR, 1w, focus_v3 True. The April event no longer holds QQQ/SPY on the latest ledger; QQQ and DIA are still outside focus for a different reason (monthly, far trigger).
- Lab hand-off 12 Nov does carry SPY (batch 17), DIA (batch 28), QQQ (batch 31) with contracts, so the focus_v3 drop applies to the legacy lane only.
- Code:
  - READY_OLD_EVENT: `data\scratch\workaround\build_thesis_ledger.py:240-248` (`fresh_from = bday_offset(evidence, -4)`; READY and not fresh → READY_OLD_EVENT at line 246); state rank 5 at `:64-65`.
  - focus_v3: `build_thesis_ledger.py:263` (`STATE_RANK ≤ 4 & checks3 ≥ 1 & rr_practical ≥ 1 & not stale`).
  - Drop point: `data\scratch\workaround\avshunter_options_standalone.py:117-118` (rows filtered to focus_v3 unless `--all`, flag at `:532`). Also `build_mining_handoff.py:155`, `preclose_trigger_scan.py:153`, `probe_chain_reuse.py:48`.

## E4 — CONFIRMED (wider than stated)

- Source line: `fix_inbox\2026-10-23_qqq_exclusion.md:2`.
- Code: `data\scratch\workaround\build_thesis_ledger.py:275-278` (money from `sector_etf` through `money_map`, default "UNMAPPED"); `money_map` at `:128-142` reads only the board's `rotation.rows` (11 sectors + 15 industries in `macro_board\config\macro_board_config_v1.json` `rotation`).
- 12 Nov ledger: QQQ, SPY, IWM, DIA all UNMAPPED. UNMAPPED rows 51, all ETFs (48 of the 63 master ETFs plus ARKG, SQQQ, TQQQ). 14 Oct: 48 UNMAPPED rows, all ETFs.
- So the gap is every ETF outside the board's rotation list (index, factor, country, fixed income, commodity, volatility), not only QQQ/SPY. Acceptance "0 ETF rows UNMAPPED" starts from 51.
- The Lab hand-off has no `money` column; the tag exists only in the legacy ledger and triage.

## E5 — NOT FOUND

Claim: "ACK allowed QQQ as an exception to macro-advisory-only (12 Nov)."

Looked in (pattern QQQ within 160 characters of exception / advisory, plus QQQ alone where stated):
- `data\scratch\workaround\lessons\fix_inbox\` and `processed\` — no hit. Only `2026-11-11_macro.md:15` and `2026-11-12_macro.md:15` mention QQQ with `macro_advisory_latest` (housekeeping, not a decision).
- `audit\laneb_fixB\` (QQQ or advisory) — no hit.
- `Claude outputs\` (QQQ) — only the draft itself, `AVS-TRACE-001_claude_code_prompt.md:104` and `:149`.
- Claude memory folder for this project — no hit.
- Whole repo `*.md, *.txt, *.csv` — search hit its time limit; hits before that were the draft and unrelated run CSVs / a 25 Sep trading plan. `Enhancements\` and `dropbox\` therefore only partly covered.

The only record of the exception is the draft that cites it. CLAUDE.md rule 6 (macro display-only) is unchanged. ACK needs to record the decision before E5 can cite it.

## E6 — CONFIRMED

`fix_inbox\2026-10-19_XLE.md:3`: holdings worth 65.2% of XLE report by 30 Oct (XOM 23.9% and CVX 17.9% on 30 Oct); triage earnings "none (ETF)", hand-off `earnings_date` null, catalyst_truth NO_CATALYST. Materiality rule (weight × implied event move ≥ 0.25 ATR): `:20`. Not recomputed from the holdings file.

## E7 — CONFIRMED

`fix_inbox\2026-10-19_XLE.md:4`: yield 2.29%; ex-dividend about 21 Dec inside the Jan 15 life; +22.0% ("r 3.89%, no dividend") vs +19.9% with a discrete 0.38 dividend; hand-off American CRR with yield gives +20.2%. Stale `dividend-next-date` (XLE 2022-12-19, XOM 2022-08-11): `:11`. Related: strategy layer S3 gain not repriced with the dividend, `:14`.

## E8 — CONFIRMED (recomputed)

- `fix_inbox\2026-10-19_XLE.md:5`: Tastytrade corr-spy-3month 0.77, beta 0.49; store 63-day correlation −0.31, beta −0.61.
- Recomputed from `data\canonical\historical_prices.sqlite` (`ohlcv_daily`, POLYGON_SPLIT_ADJUSTED, read-only), XLE vs SPY daily close-to-close returns, 63 returns from 2026-07-21 to 2026-10-16: correlation −0.311, beta −0.612. Log returns: −0.311 / −0.611.
- The Tastytrade figures are as quoted in the inbox; not re-read from the broker.

## E9 — CONFIRMED (OTM range corrected for puts)

- Source note: `fix_inbox\2026-10-23_qqq_exclusion.md:3`.
- Saved data: `data\phantom\phantom_history.db` `chain_snapshots`, ticker QQQ, DTE 14–45 (read-only).

| Quote date | Spot | Expiries in 14–45 DTE | Contracts within 1% of spot | Ask min / median / max | With ask ≤ $5 |
|---|---|---|---|---|---|
| 2026-10-22 | 704.47 | 7 (weeklies included) | 126 | 12.84 / 19.21 / 27.88 | 0 |
| 2026-11-11 | 690.02 | 6 | 156 | 10.75 / 17.68 / 27.35 | 0 |

- At-the-money asks: calls 15.73 (14 DTE) to 24.14 (39 DTE) on 22 Oct; 14.22 to 23.35 on 11 Nov.
- Nearest strike inside the cap: calls 4.0% to 6.7% OTM (delta 0.19–0.24) on 22 Oct, 3.3% to 7.2% (delta 0.17–0.26) on 11 Nov; puts 5.6% to 10.6% OTM (delta −0.12 to −0.18) on 22 Oct, 4.2% to 10.9% (delta −0.12 to −0.21) on 11 Nov. The draft's "5–8% OTM" fits calls; puts run to about 11%.
- Run 20261111_231951 picked QQQ270115C00705000 at ask 19.43, flagged OVER_CAP in the hand-off (not excluded).
- ETF rows over the cap on the 12 Nov hand-off: 24 of 65 (`lb_over_cap`).
- Where the $5 cap lives (Lane B only; it is not in `config\governed_constants_v1.json`, where grep "premium" finds only line 136, an approval note):
  - `data\scratch\workaround\avs_day.ps1:48` (default `cap = 5`), `:26`, `:145`, `:255-256`
  - `data\scratch\workaround\day_settings.json` (`"cap": 5`)
  - `data\scratch\workaround\build_lab_handoff.py:75-76` (`premium_cap` 5.0, `over_cap_lane` "flag") and `:243` (flag rule)
  - `data\scratch\workaround\check_triage.py:306`, `strategy_layer.py:477`, `today_context.json:5`
  - `avshunter_options_standalone.py:543` (`--max-premium`, "preference, not a filter")
- Wording: since the Lab-first hand-off the cap is a flag, so "premium cap excludes index ETFs" is true of the legacy lane and of triage contract choice, not of the Lab hand-off.

## E10 — CONFIRMED (no preference today); count measured

- `scripts\avshunter_options_intelligence.py:5615` `select_best_contract`: no ETF, asset-type, weekly or monthly term in the function; grep `weekly|weeklies|is_etf|monthly_only|third_friday` over the whole file: 0 hits.
- `config\governed_constants_v1.json:117` `long_option_contract_selection` (v2, PROVISIONAL): one delta mandate (0.20–0.75), preferred 0.30–0.60, runway shortfall 3.0 per day, excess 0.5 per day, value selection SHADOW. No asset-type key.
- 12 Nov hand-off, 65 ETF contracts, pipeline's own `anticipated_time_fit`: CONTRACT_EXPIRES_BEFORE_MEDIAN_TIME 34, CONTRACT_EXPIRES_BEFORE_Q80 15, CONTRACT_OUTLASTS_Q80 16. **49 of 65 (75%) expire before q80; 34 (52%) before q50.**
- Own recount (weekdays from 12 Nov to expiry vs `anticipated_sessions_q80`, holidays not removed): 47 of the 62 with a q80.
- Expiries chosen: 18 Dec, 24 Dec (2), 15 Jan, 19 Feb, 26 Feb (SPY). 62 of 65 are standard monthlies.
- For the 14 in-window ETFs the problem is mostly the reverse of the draft: contracts are 26 to 76 sessions long against q50 of 3 to 20. 6 of the 14 still expire before q80 (IHE, VOO, VTI, IVV, AGG, ARKG); 8 outlast it.
- The acceptance "0 ETF contracts expiring before q80" cannot be met by weeklies for the 27 rows with q50 over 60; it depends on E2.

## E11 — CONFIRMED

`fix_inbox\2026-10-19_XLE.md:13`: 19–30 Oct XLE 68C at 34–47% of mid; 6 Nov 68C 0.32/2.50; Tastytrade quote `updated-at` 2026-10-16T23:59Z for XLE 261023C00068000. The inbox says "likely reflect after-hours widths": the timestamp is measured, the cause is an inference. Not re-read from the hand-off JSON.

## E12 — CONFIRMED

- `domain\opportunity_rank.py:46-54` `rank_key`: blocked, lane, readiness, expected multiple present, −expected multiple, −evidence n, ticker. No asset type.
- `data\scratch\workaround\build_lab_handoff.py:468-470`: "order: GO_LIMIT first, then lab_rank ascending. Nothing else."; batch = order ÷ 30 at `:492`.
- 12 Nov hand-off: 0 ETFs in batch 1 (30 rows). First ETF is IHE at order 59 (batch 2). The 14 IN_WINDOW ETFs sit in batches 2, 14, 17 (3), 25 (3), 34, 39, 44, 56, 71 (2). All 65 ETF rows are MANUAL_REVIEW.

## E13 — CONFIRMED (recomputed)

- `fix_inbox\2026-10-19_XLE.md:16`: close 68.24, 52-week high 68.29, 0.04 ATR, no NEAR_52W_HIGH field; resistance test fails (−6% to −26% at the high).
- Store: XLE close 68.24 on 2026-10-16; 252-session high 68.29; difference 0.05.
- Related window-edge issue: `:25` (store 252-session low 42.35 on 2025-10-16 vs Tastytrade year-low 43.065). Recomputed low 42.35, first bar of the window 2025-10-16: matches.

## E14 — CONFIRMED

`fix_inbox\2026-10-19_XLE.md:24`: the two-space form "XLE  270115C00067500" returned `items []` (18 Oct 19:25 UTC); the six-character root "XLE   270115C00067500" is needed. Not re-tested (no broker call).

## E15 — CONFIRMED

- `data\scratch\workaround\track_outcomes.py:123`: summary groups are state, coherence, money, realisation, side, focus, focus_v3, decision. No asset type. The `money = UNMAPPED` row is an accidental near-proxy (48 rows on 14 Oct, all ETFs, 4 resolved, 0 targets).
- `Enhancements\outcomes\` (23 dated folders and reports): grep "etf", 0 files.
- `dropbox\macro\coaching\model\outcomes\`: `decision_events.sqlite` table `decision_events` has 76 columns, none for asset type, ETF, sector or instrument; `backfill_report_2026-11-13.md` has no ETF line.

## MISSED — ETF-specific problems in the logs that section 4 does not cover

Paths are under `data\scratch\workaround\lessons\fix_inbox\` unless stated.

| # | Problem | Path:line |
|---|---|---|
| M1 | An ETF's own `sector_etf` is wrong, so its money tag is read off the wrong sector (XOVR → XLC; 60-day correlation with QQQ 0.76). Proposed: map an ETF to the board ETF of highest 60-day correlation, or to itself | `processed\2026-10-14_XOVR.md:4` |
| M2 | Weeklies listed without a tradeable flag (XOVR weeklies OI 0–53, spreads 0.25/1.70). Bears directly on E10: "prefer the nearest weekly" needs an OI and spread test per expiry | `processed\2026-10-14_XOVR.md:7` |
| M3 | ETF with a single-name sleeve ≥ 10% (XOVR, SPCX 22.5%) moved 1.9× QQQ on CPI day; sleeve's own event distribution not in the scenario | `processed\2026-10-14_XOVR.md:13` |
| M4 | Barrier odds overstate target-first for an ETF (IGV: hand-off 0.375 vs store 21–29%) | `processed\2026-10-14_IGV.md:5` |
| M5 | No holdings file for industry ETFs (IGV, SMH, SOXX, XBI, KRE): E6's holdings-weighted event list cannot be built for them. Holdings exist for SPDRs + SPY/QQQ/DIA only | `processed\2026-10-14_IGV.md:7` |
| M6 | Tastytrade market-metrics tool fails a whole batch on non-standard chains (MSFT, PANW; VXX, UVXY; CVX, COP, DVN), so holdings' earnings dates are unreadable. Blocks E6 | `processed\2026-10-14_IGV.md:6`, `processed\2026-10-14_VXX.md:15`, `processed\2026-10-14_monitor_PRECLOSE.md:7`, `2026-10-19_XLE.md:10` |
| M7 | Volatility products lack inputs: VIX spot and term missing (`VIX_SPOT_AND_TERM_MISSING`), VX strip, VIX3M, settlement dates | `processed\2026-10-14_VXX.md:3`, `processed\2026-10-16_pipeline_improvements.md:12` |
| M8 | Catalyst truth tags a vol ETN NO_CATALYST / STRUCTURE_ONLY; the macro calendar is its catalyst set. Same pattern as E6 for non-equity ETFs | `processed\2026-10-14_VXX.md:13` |
| M9 | Triage quotes the wrong VIX future month for VXX without naming the contract | `processed\2026-10-14_VXX.md:11` |
| M10 | ETF event-exit rule has no materiality test (every ≥ 2% holding print would force an exit). The draft's E6 change text carries the rule; the problem line is separate | `2026-10-19_XLE.md:20` |
| M11 | Macro and political dated events missing from ETF holds (FOMC, GDP+PCE, US midterms 3 Nov; Brazil runoff for EWZ) | `2026-10-19_XLE.md:19`, `:22`, `:23`; `2026-10-19_VALE.md:5` |
| M12 | Two valuation lanes disagree on the same ETF contracts (Lab r_central −0.16 to −0.39 vs triage +22%) | `2026-10-19_XLE.md:9` |
| M13 | Weekly chase line not printed when a weekly rung shares the daily trigger (XLE called BEYOND CHASE on the daily only) | `2026-10-19_XLE.md:15` |
| M14 | Board oil condition STABLE in a week WTI rose 10.4% (feeds XLE) | `2026-10-19_XLE.md:12` |
| M15 | Kill switches estimated from ETF proxies (BNO/USO, TLT) were wrong; use the futures | `2026-10-29_monitor_PRECLOSE.md:6` |
| M16 | Region and industry ETFs not used for the money tag of stocks (EWZ, EWY, KWEB, JETS, OIH, XME, IGV, SMH); ETF bars missing from ticker packs. ETF-as-reference, not ETF-as-trade | `2026-10-19_triage.md:13`, `:28`; `2026-11-11_triage.md:8`; `processed\2026-10-16_BORR.md:2`; `processed\2026-10-16_AAL.md:1`; `2026-10-19_CAVA.md:10` and eight similar pack lines |
| M17 | Sector ETF returns and money flow not published in the Lab sector context (XLF, XLE, XLK, XLB, XLP) | `2026-11-12_lab_first_fix_list.md:59` |
| M18 | 39 of the 115 macro-board ETFs have no option chain in PHANTOM (includes RSP, UUP, IJR, EWY, KWEB, XME and all the leveraged/inverse pairs: SOXL/SOXS, SPXL/SPXU, TNA/TZA, FAS/FAZ, LABU/LABD, UDOW/SDOW, SDS, ERX/ERY, NUGT/DUST, BOIL/KOLD, UCO) | `dropbox\macro\coaching\model\audit\data_audit_2026-11-13.md:320`, `:348`; `reports\step1_report_2026-11-13.md:28`, `:88` |
| M19 | Leveraged, inverse and volatility ETFs are ranked and given contracts like stocks. 12 Nov hand-off: SPXS, SQQQ, TQQQ, TMF, UVXY, VXX, VIXY, SVXY all carry contracts; 3 have no arrival-time evidence. SQQQ/TQQQ/ARKG are scanner-added with no universe row at all. No inbox line names this; measured here | `handoff\lab_2026-11-12\handoff.csv` |
| M20 | Board universe (115 ETFs) and pipeline universe (85 ETFs in the security master) are different lists with no reconciliation | `macro_board\config\macro_board_config_v1.json` `universe`; `data\universe\polygon_liquid_universe_security_master_v1.csv` |
| M21 | EWG and IGV card legs never reached the broker (resting bids, close windows). Execution, not ETF-specific, listed because the names were asked for. IBB: no inbox line found | `processed\2026-10-14_monitor_OPEN.md:3-4`, `processed\2026-10-14_monitor_PRECLOSE.md:3`, `processed\2026-10-15_monitor_OPEN.md:5`, `processed\2026-10-15_monitor_POSTCLOSE.md:9` |

## Not done / limits

- The draft's ETF hand list was not found, so its 40 / 36 / 24 / 1 figures are replaced, not reconciled.
- E5 repo-wide search was cut off by the time limit; `Enhancements\` and `dropbox\` only partly searched.
- E6, E7, E11, E14 confirmed against the inbox text only (no broker or holdings re-read).
- E10 own recount uses weekdays without holidays; the pipeline's `anticipated_time_fit` is the figure to cite.
- Scratch scripts: `C:\Users\ACKVER~1\AppData\Local\Temp\claude\070dfed12763afa6\8cd4b30b-0235-46f9-b0d5-e53824635a0f\scratchpad\` (a.py to i.py).
