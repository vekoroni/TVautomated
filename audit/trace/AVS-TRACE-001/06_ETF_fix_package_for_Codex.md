# AVS-ETF-001 · ETF fix package · hand-over to Codex as owner

Prepared 14 Nov 2026 by Claude Code (reviewer, AVS-TRACE-001) for ACK. Owner of delivery: **Codex**, once it has accepted or challenged each item in writing (section 7).
Evidence for every line: `audit\trace\AVS-TRACE-001\evidence\etf_evidence_check.md` (queries, counts, method). Nothing in this package has been built or changed.

## 1. Objective

ETFs become a first-class, short-horizon part of the book: identified everywhere, timed in sessions, given contracts that last, priced with dividends, and measured on their own. No ticker is dropped.

## 2. What the data says today

ETFs were identified from `data\universe\polygon_liquid_universe_security_master_v1.csv` (`instrument_type` containing "ETF": 85 tickers) plus ARKG, SQQQ and TQQQ, which the scanner adds and which have no universe row. The draft's own hand list was not found, so its headline figures are replaced, not reconciled.

| Claim in the draft | Verdict | Measured |
|---|---|---|
| About 40 ETFs per ledger, 1.7% of rows | **Corrected** | 66 of 2,321 rows (2.8%) on 14 Oct; 60 to 64 on each of nine ledgers |
| 24 of 36 ETFs with arrival over 60 sessions | **Corrected** | 33 of 65 with a median arrival (51%) on 14 Oct |
| 1 resolved ETF outcome, a stop | **Corrected** | 6 resolved, **all stops, no target** (VOOG, XOVR, IGV, IYW, IVW, SQQQ) |
| Hit rates by expected time: 83% / 78% / 5% | Confirmed | 38 of 46, 57 of 73, 1 of 22 resolved rows; two sessions tracked, one ledger date |

On the last completed run (`20261111_231951`, hand-off `data\scratch\workaround\handoff\lab_2026-11-12\handoff.csv`):

- 65 ETF rows. Median arrival known for 62: **15 within 20 sessions (24%)**, 20 between 21 and 60, 27 over 60.
- **49 of 65 ETF contracts expire before the q80 arrival; 34 before the median** (the pipeline's own `anticipated_time_fit`).
- **No ETF in batch 1.** The first ETF is at position 59. The 14 in-window ETFs are spread over batches 2 to 71.
- QQQ, SPY, IWM and DIA all carry the money tag UNMAPPED on the 12 Nov ledger; all 51 UNMAPPED rows are ETFs.
- Leveraged, inverse and volatility products (SPXS, SQQQ, TQQQ, TMF, UVXY, VXX, VIXY, SVXY) are ranked and given contracts like stocks.

The outcome figures are two sessions on one date. They show where to look. They are not a measured edge.

## 3. Items E1 to E15, validated

Verdict on the draft's evidence line: C = confirmed, X = corrected, P = partly, NF = not found.

| ID | Verdict | Evidence, confirmed or corrected | Change (as corrected) | Acceptance |
|---|---|---|---|---|
| E1 | X | The decision ledger and the Lab card have no asset-type field (the card has `sector` and `sector_etf` only). **The security master already has `instrument_type` (15 ETF types, 3,320 rows) and no code reads it.** Hand lists: `avshunter_discovery_ULTIMATE.py:1148`, `data\scratch\workaround\quickkill.py:21`, `macro_board\config\macro_board_config_v1.json`. Gaps in the master: QQQ is typed ETF_OTHER, there is no ETN type, scanner-added tickers have no row. | **Carry and repair the existing `instrument_type`**, do not add a second field: one owner, read by Discovery, the ledger and the Lab card; add ETN and leveraged/inverse/volatility types; type scanner-added tickers. Retire the hand lists. | 100% of book rows typed; leveraged, inverse and volatility products flagged; 0 hand lists left |
| E2 | X | 14 Oct: 66 ETF rows, 20 with median arrival within 20 sessions, 33 over 60. 12 Nov: 15 of 62 within 20 (24%). | ETF targets sized to the ETF's own volatility over 1 to 10 sessions; weekly and monthly setups restated in sessions and flagged when outside 1 to 20. | **Baseline is 24% to 31%, not near the target.** State the target as a measured step (for example 24% → 60% on one normal run), then 80%. No row dropped to reach it |
| E3 | P | QQQ and SPY were READY_OLD_EVENT with a 24 Apr event date on the 22 Oct ledger (`build_thesis_ledger.py:240-248`). Rows dropped: **469** (470 is the number of `focus_v3` theses priced, a different count; drop at `avshunter_options_standalone.py:117-118`, `focus_v3` at `build_thesis_ledger.py:263`). **On the 12 Nov ledger neither is frozen**, and the Lab hand-off carries SPY, DIA and QQQ. | The `focus_v3` drop is a legacy-lane problem that ends when Lane B switches to the Lab hand-off. Keep only: a READY thesis older than N sessions is flagged STALE_EVENT and re-armed on a fresh event. N in config. | No ETF thesis older than N sessions without a flag; QQQ, SPY, IWM, DIA priced on every run (already true on `20261111_231951` for three of four; confirm IWM) |
| E4 | C, wider | UNMAPPED on 12 Nov for QQQ, SPY, IWM, DIA; 51 UNMAPPED rows, all ETFs (`build_thesis_ledger.py:275-278`, `money_map` at `:128-142`). The Lab hand-off has no money column at all. | Index ETFs map to themselves against SPY/RSP breadth; sector ETFs to their own sector route; other ETFs to the board ETF of highest 60-day correlation (also fixes XOVR → XLC, M1). Display and context only (CLAUDE.md rule 6). | 0 ETF rows UNMAPPED |
| E5 | **NF** | ACK's QQQ exception of 12 Nov is **not recorded anywhere in the repo**. Looked in: `fix_inbox\` and `processed\`, `audit\laneb_fixB\`, `Claude outputs\`, `Enhancements\tradeability\`, `docs\`, project memory. The only mentions are this package's own draft and Codex's `QQQ_ENHANCEMENT_DESIGN_20261112.json` (outside the repo), which treats macro direction for QQQ as "an explicit policy-change gate". CLAUDE.md rule 6 says macro never influences a gate, score or rank. | **Decision for ACK, in writing, before any build:** may the board set direction for index and sector ETFs? If yes: the rule, its kill switch, and an amendment to CLAUDE.md rule 6. | Decision recorded in the repo; rule in governed constants; CLAUDE.md amended or the exception refused |
| E6 | C | XLE: holdings worth 65.2% report by 30 Oct (XOM 23.9%, CVX 17.9%), triage said "no events" (`fix_inbox\2026-10-19_XLE.md:3`; materiality rule proposed at `:20`). | Holdings-weighted event list; a holding's print counts when weight × its implied event move ≥ 0.25 ATR of the ETF (threshold in config, to be calibrated). Disclosure, never a gate. | ETF cards list material holding events inside the hold. **Blocked for industry ETFs** until M5 and M6 are fixed |
| E7 | C | XLE yield 2.29%; +22.0% without the dividend, +19.9% with a 0.38 dividend; Tastytrade next-date stale (`2026-10-19_XLE.md:4`, `:11`). | Discrete dividends from the ex-date cadence in the one valuation engine (`domain\option_valuation.py`); ignore Tastytrade `dividend-next-date`. | Reprice matches the card basis within 1 point |
| E8 | C, recomputed | Price store, 63 sessions to 16 Oct: correlation −0.311, beta −0.612. Tastytrade showed 0.77 and 0.49 (`2026-10-19_XLE.md:5`). Same defect as register N17-03 (31 inbox reports). | Correlation and beta from the price store, everywhere. | Card values equal the store |
| E9 | C, range corrected | QQQ within 1% of spot, 14 to 45 DTE: **0 of 126 contracts (22 Oct) and 0 of 156 (11 Nov) ask at or under $5**; at-the-money asks are about 14 to 24. Inside the cap: calls 3.3% to 7.2% out of the money (delta 0.17 to 0.26), puts 4.2% to 10.9% (delta 0.12 to 0.21). The cap lives in Lane B only (`avs_day.ps1:48`, `day_settings.json`, `build_lab_handoff.py:75-76`), not in governed constants. | Follows ACK's decision of 13 Nov: the cap is a flag with a labelled over-cap lane. **Open for ACK:** for index ETFs, show the over-cap at-the-money contract, the in-cap out-of-the-money one, or both as alternatives. | Rule recorded; both contracts visible on the card |
| E10 | C | No ETF or weekly preference in `select_best_contract` (`scripts\avshunter_options_intelligence.py:5615`) or in `long_option_contract_selection` (`config\governed_constants_v1.json:117`). 49 of 65 ETF contracts expire before q80. | **Reworded.** ACK decided on 12 and 13 Nov that the contract is chosen from the monetisation clock n, not from q80. So: for ETFs, the shadow pick prefers the nearest expiry that covers n plus the monitoring and exit sessions and passes the liquidity tier **per expiry** (M2: XOVR weeklies have OI 0 to 53). | ETF rows with `contract_covers_n = YES`; no tier C pick where an A or B exists. "0 before q80" is **not** the test and cannot be met for the 27 rows whose median is over 60 sessions |
| E11 | C | XLE short-dated spreads 34% to 47% of mid on quotes stamped 2026-10-16T23:59Z (`2026-10-19_XLE.md:13`). Same pattern in `2026-10-23_monitor_POSTCLOSE.md` (ASO 9% at 15:17 ET, 77% at 16:21 ET). | Liquidity tier computed on a quote taken in the session; a post-close quote is labelled POST_CLOSE_QUOTE and the tier marked provisional. A flag, not a gate. | No tier shown without its quote time; post-close tiers labelled |
| E12 | C | The rank key and the batch order use no asset type (`domain\opportunity_rank.py:46-54`; `build_lab_handoff.py:468-470`, `:492`). No ETF in batch 1. | **Decision for ACK** (design): either a labelled ETF lane in the hand-off (batch 0), or asset type as a readiness input in the one rank owner. Sorting ETFs first by rule outside `opportunity_rank.py` would create a second rank owner. | Every in-window ETF is in the first triaged batch or its own lane |
| E13 | C, recomputed | XLE close 68.24, 252-session high 68.29, gap 0.05; no flag (`2026-10-19_XLE.md:16`). Reported missing from triage in 8 ticker files on 19 and 22 Oct. | NEAR_52W_HIGH / LOW and the resistance-test value on every row (stocks too). | Flag present on every row |
| E14 | C | "XLE  270115C00067500" (two spaces) returns nothing; a six-character root is needed (`2026-10-19_XLE.md:24`; also LTC). Not re-tested here (no broker calls in this review). | Normalise OCC symbols in the tool wrapper and prompts. | Lookups succeed for 1 to 5 letter roots |
| E15 | C | No ETF split in any outcome summary: `track_outcomes.py:123` groups have no asset type; `decision_events.sqlite` has 76 columns, none for it. | ETF vs stock split in the card outcome ledger (AVS-LEDGER-001), using E1's field. | Summary shows ETF rows with n; cells under 10 marked LOW_N |

## 4. Items the draft misses (from the logs)

| ID | Problem | Source | Proposed change |
|---|---|---|---|
| E16 | Leveraged, inverse and volatility products are treated as stocks: ranked, timed and given contracts on stock rules. Their decay and path dependence are not modelled. | Measured on `handoff\lab_2026-11-12\handoff.csv` (SPXS, SQQQ, TQQQ, TMF, UVXY, VXX, VIXY, SVXY) | Flag from E1; **decision for ACK**: research-only lane, or trade with a stated rule. Until then, label on the card |
| E17 | The board's ETF list (115) and the pipeline's (85) are different lists. 39 board ETFs have no option chain in PHANTOM, including every leveraged/inverse pair. | `macro_board\config\macro_board_config_v1.json`; `dropbox\macro\coaching\model\audit\data_audit_2026-11-13.md:320` | One ETF list, with a "has options data" column; the 39 marked NO_CHAIN, never silently absent |
| E18 | No holdings file for industry ETFs (IGV, SMH, SOXX, XBI, KRE); holdings exist for SPDRs, SPY, QQQ, DIA only. Blocks E6. | `fix_inbox\processed\2026-10-14_IGV.md:7` | Holdings source for the remaining ETFs, or E6 marked NOT_ASSESSED for them |
| E19 | The Tastytrade metrics call fails a whole batch when one symbol has a non-standard chain, so holdings' earnings dates are unreadable. | `processed\2026-10-14_IGV.md:6`, `processed\2026-10-14_VXX.md:15`, `2026-10-19_XLE.md:10` | One symbol per call (register N17-17, the one Closed row, already says this); apply it in the ETF event step |
| E20 | Volatility products lack inputs: VIX spot and term, VX strip, VIX3M, settlement dates; a vol ETN is tagged NO_CATALYST when the macro calendar is its catalyst set. | `processed\2026-10-14_VXX.md:3`, `:13`; register R14-09, A16-06 | Feed the vol inputs; map non-equity ETFs to the macro calendar for events |
| E21 | Macro and political dated events missing from ETF holds (FOMC, GDP and PCE, 3 Nov midterms; Brazil runoff for EWZ). | `2026-10-19_XLE.md:19`, `:22`, `:23`; register N17-09 | Add to the event list in E6 |
| E22 | Barrier odds overstate target-first for an ETF (IGV: hand-off 0.375 against 21% to 29% from the store). | `processed\2026-10-14_IGV.md:5`; register R14-06 | Show the store race beside the in-sample odds |
| E23 | An ETF with a single-name sleeve of 10% or more moves on that name (XOVR). | `processed\2026-10-14_XOVR.md:13` | Flag CONCENTRATED_HOLDING from the holdings file |
| E24 | Region and industry ETFs are not used as the reference for stocks (EWZ, EWY, KWEB, JETS, OIH, XME, IGV, SMH); ETF bars missing from ticker packs. | `2026-10-19_triage.md:13`, `:28`; `2026-11-11_triage.md:8`; register R14-03, R14-04, A16-02 | Out of this package's scope (stock mapping), listed because it shares E4's map |

## 5. Dependencies and order

| Item | Depends on |
|---|---|
| E2 | The window flag (tradeability brief W3) |
| E10 | The monetisation clock and `contract_covers_n` (W1, W2). A12 is built on `feat/a12-monetisation-clock-20261112` and is not merged or run |
| E15 | AVS-LEDGER-001 and E1 |
| E6 | E18, E19 |
| E12, E5, E9, E16 | A decision from ACK first |

Suggested order: E1 (everything else needs it) → E13, E14, E8, E7 (small, independent) → E4 → E11 → E2 and E10 with the tradeability work → E6 with E18 and E19 → E15 with the ledger.

## 6. Rules for this package

- CLAUDE.md applies: no pipeline code change without an approved root cause and design; a failing business-rule test first; thresholds in versioned configuration; macro display-only unless ACK amends rule 6.
- Flags and labels. Nothing here gates, blocks or drops a row. Missing is blank with a reason.
- Options data from MarketData only. Tastytrade is used for earnings dates and live checks, not for stored quotes.
- Two-level closure: each item is CLOSED only with code evidence and a run artefact. Code and tests alone is CLOSED OFFLINE.
- Each commit gets its change-log line (AVS-CHANGELOG-001).

## 7. For Codex: accept or challenge, in writing

Please return one line per item before any build, to `audit\trace\AVS-TRACE-001\ETF_codex_response.md`:

`E<n> | ACCEPT / CHALLENGE / NEEDS ACK | reason or correction, with path:line | design note due | depends on`

Points I expect a challenge on, and would welcome:

1. E1: whether `instrument_type` in the security master is reliable enough to be the one owner, given QQQ is typed ETF_OTHER.
2. E2: the method for "targets sized to the ETF's own volatility"; the GARCH D1 fix (`fff3a3e`) changes those numbers and is not yet run.
3. E10 and E12: both touch contract selection and rank, which are governed (`value_selection_mode` is SHADOW; one rank owner).
4. E3: whether anything remains to build once Lane B is on the Lab hand-off.

## 8. Decisions needed from ACK

| # | Decision | Item |
|---|---|---|
| 1 | May the macro board set direction for index and sector ETFs? If yes, CLAUDE.md rule 6 must be amended. The 12 Nov QQQ exception is not written down anywhere. | E5 |
| 2 | Index ETFs and the $5 cap: over-cap at-the-money, in-cap out-of-the-money, or both shown | E9 |
| 3 | ETFs first: a labelled lane in the hand-off, or asset type inside the rank | E12 |
| 4 | Leveraged, inverse and volatility products: research-only lane or traded with a rule | E16 |
