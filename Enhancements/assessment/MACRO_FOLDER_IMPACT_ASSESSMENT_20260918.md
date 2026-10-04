# Macro folder: impact assessment against what has been built

18 September 2026 · prepared by Claude Code for ACK · read-only review, nothing changed · evening run 20260918_112522 in progress

Scope: `dropbox/macro/` (theses, data feeds, `coaching/`, `Archive/`) and `data/macro/`. Governing rules: CLAUDE.md
rule 6 (macro and event guards are display-only: never gate, score or rank), R1 (missing is never neutral), R2 (one
owner per fact), R12 (fresh or flagged).

## 1. Summary

1. **The macro folder is a money-flow advisory tool (ACK, 18 Sep 2026), not a trade-decision input.** That is its
   intended role and it matches rule 6. It is refreshed by the macro run each morning and feeds the morning run as
   context for the human reviewer. It is also a data source for a volatility-regime scenario. The coaching overlays
   (12 Sep) are the exception: they tried to turn it into decisions (desk gate, rank engine). They were never wired
   in and hold no outcomes (all 41 desk-gate decisions have `"taken": null`).
2. **The display-only rule is still broken in live code.** Of these, one (the options score) is verified, and one
   (the legacy EV v2) affects a value that has no authority. The rest are listed in §4 for confirmation. None of them
   touches today's ticket ranking, which uses the macro-free path value. They reach tickets only indirectly, through
   the Lab's legacy `final_action` labels (blueprint item A1).
3. **The material itself asks for gates we have removed.**
   - The theses ask for macro gates: a VVIX > 100 block, an FOMC 48-hour block, "no broad-index longs before CPI",
     and a size multiplier.
   - The money-index learning report states that "the macro layer ranks and sizes" trades.
   - The coaching desk gate hard-stops on a 15% spread and a 5-session DTE buffer.

   All of these conflict with decisions taken since (rule 6, R11, D1, and the 25% single spread limit). They should
   be displayed, not implemented.
4. **Three pieces are worth reusing:**
   - the point-in-time macro packet archive, as volatility-regime and rates features for a shadow scenario;
   - the root-cause groups (OIL, RATES, GROWTH, DEFENSIVE, INDEX), as a diversification cap on the daily list;
   - the discovery test M2: does our forecast add anything beyond implied volatility?
5. **This morning's packet (the latest data, feeding the morning run) has internal inconsistencies** that would
   mislead the reviewer:
   - the 10Y conflict rule adopts a lagged FRED vintage over this morning's value;
   - VIX comes from two sources;
   - `iv_vs_realised_pct` reads 100 when the gap is about 59%;
   - the money index names the 13 Sep revision as its previous (so the change reads −25, not −3);
   - the event payload is never consumed;
   - there are no earnings dates anywhere.

## 2. Inventory

| File | What it is | As of | Read by | Status |
|---|---|---|---|---|
| `dropbox/macro/macro_intelligence_latest.json` (622 KB) | `macro_contract_v1_0`, built by `build_macro_json.py`, then normalised and enriched in place | 18 Sep 11:24Z | `intelligent_orchestrator.py:422`, Discovery (stamps `active_regime`, `regime_drift_status`), Lab (display) | **Authoritative copy** |
| `data/macro/macro_intelligence_latest.json` (189 KB) | Raw build output, copied before enrichment | 18 Sep | Only `vix_governor.py:149`, which is unused and has a broken path | Duplicate; drifts from the dropbox copy (`gex_regime_score` 0.30 against 0.25) |
| `avshunter_macro_enrichment_delta.json` | News/terminal delta, AUGMENT_ONLY; `merge_controls` forbid overriding filter, size, horizon or sectors | 18 Sep 10:27Z | Macro normaliser; `signal_grader.py:102,212` | Current |
| `avshunter_us_money_index.json` | USMI v2_0, `risk_off_transmission_score` 32, revision 4 | 18 Sep 11:00Z | Macro build (listed under `unverified_metrics`) | **Revision lineage broken** (see §6) |
| `avshunter_us_economic_event_payload_2026-09-16.json` | 4 dated events (FOMC, retail sales, import prices, EIA) with surprise scores; verdict LONG_PUTS_FAVOURED 94 | This morning's run (events of 16 Sep) | **No reader** | Current but not consumed |
| `bond_macro_state.json` | Bond score 48, BOND_MACRO_CAUTION, curve 2 sessions stale | 18 Sep | Runner flags (`execution_intelligence_runner.py:680-738`), morning gate (display) | Current, partly stale |
| `auction_calendar.csv` | 2 rows (2Y 22 Sep, 5Y 23 Sep), sizes blank | 18 Sep | Macro build | Thin |
| `thesis/macro_thesis_2026-09-14.md`, `-17.md` (+ Archive 09, 11) | Advisory narrative theses: scenarios, threshold board, data-quality register | 9–17 Sep | People | Useful context; 14 Sep says "no previous thesis exists" although 9 and 11 are archived |
| `Archive/Claude outputs/us_money_index_learning_report_2026-09-11.md` | Teaching narrative on the 11 Sep USMI state | 11 Sep | People | Asserts macro "ranks and sizes": conflicts with rule 6 |
| `data/macro/archive/*.json` | `macro_packet_archive_v1`, content-addressed 75-field packets, written by both `build_macro_json.py:1979` and `intelligent_orchestrator.py:2721` | 11–18 Sep | — | **Point-in-time: the right base for backtesting** |
| `data/macro/macro_latest.json` | Old schema | Feb 2026 | Nothing | Dead file |
| `coaching/` | 12 Sep coaching board, trade dossiers, desk gate, rank engine, fix registers, tester prompts | 12 Sep | Nothing in production | Design history; see §5 |

## 3. Impact on what was built (17–18 Sep)

| Build | What the macro folder says | Impact | Recommendation |
|---|---|---|---|
| **Rank, don't gate (A0, `025c284`)** | The coaching `AVS-RANK-001` (12 Sep) already proposed rank-not-gate with integrity-only vetoes. The theses ask for event and VVIX gates. | Confirms the direction. The theses' gates stay out (rule 6). | Keep. Show the thesis "when not to trade" items as labelled context on the ticket, not as filters. |
| **Daily top 5 (`apply_daily_cap`)** | AVS-RANK-001: portfolio of 10, at most 2 per sector and 3 per macro root cause. The thesis learning report: three oil puts are "the same oil bet wearing three hats". | **Gap.** Today's top 5 has no concentration control; five tickets can be one oil bet. | Candidate change: a root-cause/sector **diversity rule inside the ranking** (skip a sixth same-cause name, record why). It is rank ordering, not a gate. Needs design approval. The root-cause map comes from `desk_gate.map_routing()`. |
| **C3 last exit session (`c65cc59`)** | Annex A ALG-03: keep short contracts, mark them HORIZON_LIMITED, never value them over the full hold, and require a separately versioned policy. | Aligns; C3 is that policy. | Record the C3 valuation version in the decision record (versioning requirement). |
| **D2 20-session window (`49d4a4c`)** | The learning report uses "the 15-day maximum hold" and a mid-hold time exit. Annex A uses a per-thesis hold h. | Minor conflict; the specification (1–20 sessions) governs. | No change; note the difference. The time-exit idea is a candidate exit-policy variant for the ledger. |
| **Horizon not a gate / runway floor (`186e4ba`)** | The learning report prefers about 30 DTE and delta 0.55–0.60 because time value is rich. The desk gate hard-stops at a 5-session DTE buffer. | Supports buying runway, and the value model agrees. The desk gate's DTE stop conflicts with D1. | Keep. Delta 0.55–0.60 is a candidate for the governed preferred range (0.30–0.60 today), to be tested on the ledger, not adopted from the narrative. |
| **Single 25% spread limit** | The desk gate uses a 15% hard stop, and Annex A an 18% executable limit. | Conflict, knowingly accepted (ACK 18 Sep): tickets keep their own 10% entry limit, so wide contracts reach manual review, never a ticket. | No change. |
| **Long options at today's premium** | Every thesis says implied volatility is expensive ("IV ~100% above realised"; the measured SPY ATM IV gap is about 60%). They advise defined-risk spreads, and warn that "post-FOMC IV can collapse even when direction is correct". | **Relevant to returns.** Buying single legs in an expensive-IV regime is the Goyal-Saretto headwind (research item R1). | Make IV/forecast visible on every ticket, and prioritise the **volatility-cheap scenario** (R1) as the first shadow scenario. Verticals stay deferred (D8). |
| **Multi-scenario idea** | The packets carry VIX, VIX9D, VIX3M, contango, VVIX, realised 20-day vol and VIX percentile, all with `data_as_of`. There are dated macro events, but **no earnings dates**. | Enables a vol-regime feature set that can be backtested. The event scenario still lacks its core data (R3). | Use the archive packets (11–18 Sep only: short) plus the price store to build the vol-regime scenario in shadow. Record the earnings-calendar gap as a blocker for the event scenario. |
| **GEX** | Theses: GEX stale since 4 Sep; SPY −$2.94bn on 17 Sep with walls at 745/775. | Matches today's GEX-D9 finding: same-day chain requests fail with "date … historical only". | GEX-D9 fix (awaiting approval). GEX stays display-only. |
| **Decision ledger and backtest ledger** | The desk gate has a hand-filled outcome block; DISC-002 M8 asks for a trial counter. | Already built in better form. | Archive the desk-gate decision files as history. |

## 4. Display-only rule (CLAUDE.md rule 6): findings

| Location | What it does | Reaches tickets? | Evidence |
|---|---|---|---|
| `scripts/avshunter_options_intelligence.py:6071` | −3 OIS points when the regime is TRANSITIONAL and IV percentile is high | Indirectly, via the verdict and `final_action` (A1) | **Verified** |
| `ev_engine_v2.py:300-304, 371` | EV × regime × drift. `regime_drift_status` values from Discovery (e.g. `DRIFTING_BULLISH`) are not in the table and default to **0.88** (−12% on every row) | No: legacy EV v2 has no authority (rule 5) | **Verified** |
| `scripts/avshunter_superbrain_layer.py:704, 1556-1567, 1666-1671, 1937-1941` | Regime warnings, a direction-dependent regime discount on the risk label, `regime_size_mult` 0.88–1.08 | Possibly, via the verdict and risk label | Reported by review; to confirm |
| `signal_grader.py:102, 212` → `intelligent_orchestrator.py:812-911`, Discovery `:2130` | Enrichment-delta timestamp and tickers assign routes including EXCLUDED | Yes, if the grader ran | Reported; to confirm |
| `ml_confidence_layer/run_ml_on_vanguard_output.py:309, 141-144` | Macro sub-regime as an ML feature; wrong key paths make it almost always TRANSITIONAL_BEARISH | Advisory layer | Reported; to confirm |
| Latent: `enhancement_integration.py:321,527` (Kelly by regime, disabled at orchestrator `:6059`), `final_decision_engine.py:641,655-665`, `execution_intelligence.py:401` | Size or sector block by regime | Not wired now | Reported |
| Compliant: `macro_horizon_router.py:460-487`, morning gate `:1630-1637, 2286, 2304, 2381`, Discovery `:838, 1561`, options `:7452`, monetisation policy `:488-520`, Lab `_normalise_macro` | Display or neutral | — | Reported |

Stale comments at `intelligent_orchestrator.py:557-573, 5316` still describe macro as a sizing multiplier.

**Recommendation:** one root-cause-and-design item, "macro reaches no score". It covers the OIS −3 (verified) and
the EV v2 regime factor (verified), and confirms and removes the Superbrain and grader paths, test-first. Priority is
**medium**: it does not touch today's ranking, but it biases the legacy verdict that still feeds `final_action`
(A1), which blocks tickets.

## 5. Coaching folder (12 Sep) against today

- **Not in production.** No import of `desk_gate`, `rank_engine`, `build_coaching_board` or `build_trade_dossiers`
  outside `dropbox/`. The tester verdict for AVS-TD-001 (13 Sep) was REJECT.
- **Its outputs show why gating failed:**
  - The desk gate on Friday 11 Sep evening gave 41 probes and 1,310 no-trade rows (720 on spread, 451 on missing
    stop/target).
  - The morning result was **0** probes.
  - The rank engine's top ten were cheap far-out-of-the-money contracts (−99% at −1σ, +370% at +1σ), with an
    uncalibrated p of about 0.50. This is the lottery-strike trap (Boyer-Vorkink; our OTM study).
- **Its ranking maths conflict with ours:** a 7-point Black-Scholes grid over a GARCH budget, against today's
  empirical path value with C3 and fill models. Ours is measured on the ledger; theirs never was. Keep ours.
- **Requirements still open and worth scheduling:**
  - calibration gates (ALG-09: shrinkage, embargo, ECE and Brier) before any p is trusted;
  - the replay harness (WP8, partly covered by the backtest ledger);
  - the preferred-contract switching margin (ALG-11);
  - the macro routing and scenario evaluator (ALG-14), which maps to the multi-scenario design.
- **Discovery tracks that map to the multi-scenario plan:**
  - M1: do macro routing labels predict sector returns? This decides whether macro ever earns more than display.
  - M2: realised move regressed on forecast plus implied volatility.
  - M8: condition splits with Benjamini-Hochberg correction and n ≥ 100.

  The `audit/td/AVS-TD-001/track_M2`–`M8` outputs (13 Sep) are unread and may hold measured outcomes. They should be
  read before designing the vol-cheap scenario.

## 6. Consistency defects inside this morning's macro run

Corrected 18 Sep after ACK's review. Every file in `dropbox/macro/` is this morning's macro run, the latest data
available, and it feeds the morning run. The defects below are therefore **internal inconsistencies within today's
packet**, not stale files.

| Defect | Evidence (this morning's packet) | Rule |
|---|---|---|
| 10Y: an older source vintage wins the conflict | Bond sidecar `yield_10y` 5.01% is a FRED series with a 2-day publication lag (value for 16 Sep). C-02 adopts it over this morning's USMI 4.94% and intraday 4.93% (as of 18 Sep 11:00Z) | R12 (freshest source should win) |
| VIX: two sources for one fact | `extras.vix_spot` / `volatility.vix_spot` 15.33 (VIX engine CSV) against USMI and put gate 15.44 (CBOE official 17 Sep close). Both are 17 Sep, from different sources | R2 |
| `volatility.iv_vs_realised_pct` = 100 | Same block: VIX 15.33, `realised_vol_20d` 9.64 → +59%. The value looks capped. No repo code writes this field, so it comes from the macro build tool | R6 (labels say what was measured) |
| Money index: wrong "previous" reference | Score **32 is current and correct** (as of 18 Sep 11:00Z). But the packet says it supersedes revision 3 of 13 Sep (score 57), not last night's revision 6 (score 35). So "change since previous" reads −25 when the real move is −3, and `regime_change_since_previous_packet` is true | R7 (reproducible lineage) |
| Event payload not consumed | This morning's file (covering the 16 Sep releases: FOMC, retail sales, import prices, EIA). **No code reads it**, so it never reaches the morning run or the Lab | Missing consumer, not staleness |
| Contradictory states in one packet | `macro_filter` NO_GO with `risk_on_off_switch` SELECTIVE_RISK_ON; horizon biases `NARRATIVE_UNVERIFIED` | R6 |
| Narrative inconsistencies across theses | CPI 3.54% against 3.713% against "+3.4% in line"; copied VIX9D/VIX3M; re-used event facts; Fung-Hsieh arithmetic (0.70 × 0.7 ≠ 0.50) | Display quality |
| Two copies of the macro contract drift | `gex_regime_score` 0.30 against 0.25 | R2 |
| No earnings dates anywhere | All event sources checked | Blocks the event scenario (R3) |

## 7. How far the macro narrative can be trusted (checked against later notes)

- **Right:**
  - the risk-off transition, 9 Sep scenario B (about 30%);
  - the IWM 287.20 break;
  - the SPY 766/760 and QQQ 706.52 breaks;
  - financials weakening in the bear flattener;
  - credit spreads, not HYG price, deciding "systemic".
- **Wrong:**
  - the 9 Sep base case, on day one;
  - the carry-unwind / stronger-yen variant;
  - "energy calls" (XLE fell on a +6% crude day);
  - the 11 Sep "in-line CPI" branch behaved like the soft branch.
- **Never tested:** the recommended trades' option P&L.

Directional calls came out mixed, about half right, with no sizing or option evidence. That supports rule 6:
display for the human reviewer, and only a pre-registered, measured test (M1) could ever promote a macro field to a
ranking input.

## 8. Recommended next steps (for ACK decision)

| # | Item | Type | Why |
|---|---|---|---|
| 1 | Root-cause/sector diversity in the daily list (at most N per root cause), using the existing `map_routing` groups | Design → build | Stops five tickets being one bet; rank ordering, not a gate |
| 2 | "Macro reaches no score": remove OIS −3 and the EV v2 regime factor; confirm and remove the Superbrain and grader paths | Root cause → build | Rule 6; biases the legacy verdict that feeds `final_action` |
| 3 | Volatility-cheap scenario in shadow, using archive packets and chain IV against the HAR forecast; read the TD-001 M2 results first | Research (ledger) | Every thesis flags expensive IV as the main headwind to long options |
| 4 | Macro packet consistency: freshest-source-wins for the 10Y, one VIX source, correct `iv_vs_realised_pct`, money-index "supersedes" pointing at the last published revision, a consumer for the event payload (Lab display), retire `data/macro/macro_latest.json` and the unused `vix_governor.py`. The first four sit in the macro build tool, outside this repo's Python | Root cause → build (macro tool owner) | R2, R7, R12; the advisory must read right |
| 5 | Show the thesis "when not to trade" items (VVIX > 100, FOMC 48h, pre-CPI) as labelled context on each ticket | Display | Human element at entry, without gating |
| 6 | Source a point-in-time earnings calendar | Data | Unblocks the event scenario |
| 7 | Archive `coaching/` desk-gate and rank-engine outputs as design history; port only `map_routing` | Housekeeping | One owner per fact; avoid a second ranking engine |
