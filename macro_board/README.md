# ETF Macro Board

A standalone decision board for QQQ, SPY and every ETF in the price store. It is built from
AVSHUNTER's macro outputs and databases (ACK, 6 Oct 2026).

- **Outside the pipeline.** It opens the price store read-only and reads the macro files without
  writing to them. Its only writes go to `macro_board/output/`, and no pipeline module reads
  that folder.
- **Measured, not asserted.** A lean is what each ETF did after past sessions whose macro
  conditions looked like today's. It runs from the next open, counts only independent windows
  and checks the result on a held-out final quarter. Advisory sources (the LLM packet, the US
  Money Index, event and news overlays, the Colab models) are shown as published and scored
  against SPY/QQQ.

**Desk manual for traders:** [docs/ETF_Macro_Board_Manual.html](docs/ETF_Macro_Board_Manual.html). It covers reading every tab, the morning routine, the desk card and worked examples. A published copy is at https://claude.ai/artifact/MwP2uQYJkKSrUE4fTniBSX (private; share it from the page).

## Run

```powershell
.\Run-MacroBoard.ps1            # refresh holdings + tastytrade metrics, build and open
venv\Scripts\python.exe -m macro_board --as-of 2026-09-15   # measured layers as of a past session
```

A build takes about 40–90 seconds. The first run also caches the breadth panel, keyed on the
price store's size and modification time. Output:

- `output/etf_macro_board.html`: a self-contained page; open it in any browser.
- `output/snapshots/board_<session>.json`: the leans shown by the evening build. This is the
  scored record; later builds score it on the Scorecards tab.
- `output/snapshots/board_<session>_<kind>.json`: morning, intraday and off-session builds. They
  are kept but never scored, because a pre-open build shows the same closing session as the
  evening before.

Run-MacroInputs.ps1 builds the board twice per session. PostClose gives the evening build
(the scored record). PreOpen gives the morning build: it adds the overnight capture
(`dropbox/market_data/overnight_*.json`) at the top of the Overview, showing futures,
pre-market, VIX, FX, Asia, Europe and the 08:30 ET prints since the US close. The header
names the build. A manual build is labelled from the XNYS calendar and the clock ("by clock").

## Pages

| Tab | What it shows |
|---|---|
| Daily review (opens first) | First, the day's information and the market's reaction: a measured reading per instrument and sector (accepted / rejected / absorbed, from the opening gap and the close in the instrument's own daily move), what followed past days with the same reading for SPY/QQQ/IWM/DIA, what changed and what was expected (event payload as published, FRED prints, missing consensus stated), what disagreed (measured moves against SPY, SPY constituents, the payload's contradictions) and what remains unresolved. Then where the opportunity is strongest, top-down: QQQ vs SPY per horizon and whether the move is broad or concentrated (RSP vs SPY, share of index weight above its 50-day average); sectors vs SPY with relative strength kept apart from absolute direction ("outperforming while falling" is defensive preference, not a call); whether each sector's holdings confirm its move; room to the nearest obstacle above and below (252-day high/low, 50/200-day averages, GEX walls/flip with their date, pipeline target/invalidation) in % and daily moves. Above it, tomorrow's decision points: what could force participants to reassess SPY/QQQ/IWM/DIA in the next session; scheduled events up to 20 sessions ahead (FRED releases with ET times, FOMC decisions from config, earnings of the top issuer holdings via MarketData, holidays and shortened sessions); unscheduled developments from the news enrichment and event payload kept apart. Every review table has a CSV button. |
| Overview | SPY/QQQ/IWM/DIA cards: leans per horizon, dealer gamma and price state. The 10 macro conditions with their history. What changed. Analog depth and recent analog episodes. Packet headline. |
| ETF matrix | All ETFs by group, with returns, relative strength, trend, realised vol, lean, analog vs base mean, independent windows and packet lead/avoid. Click a row for evidence by horizon and by condition. |
| Transmission map | ETF × condition heatmap: how each ETF's forward return differed while each condition sat in today's state. |
| Sector rotation | A relative rotation map (approximation, not JdK) for the 11 SPDR sectors or industries/themes, with weekly tails. Rotation table: quadrant and days in it, relative 5/20/60d, participation, leading holdings, macro-conditional relative lean, packet bias with agree/disagree. Macro-conditional ranking vs SPY with 80% intervals. Sector × condition heatmap on relative returns. Quadrant → forward relative return (with an all-sessions baseline). Measured quadrant transitions. Scorecard of the LLM packets' leading vs lagging sectors. |
| Macro intelligence | LLM packet, US Money Index transmission score and triggers, event risk, news overlay, VIX complex, GEX, rates/credit, liquidity, Colab models, FRED prints, threshold flags. Each shows its source, as-of time and freshness. |
| Scorecards | Colab regime model, archived LLM packets (latest wins per session) and the board's own leans, scored from the next open. |
| Method | Definitions, thresholds, point-in-time rules and limits. |
| Next session plan (last tab) | The board's pieces in a veteran's order (ACK, 10 Oct 2026). The call: what the index ETFs did, whether they accepted the news, breadth and measured macro pressure, with an approach for that state. Scenarios for SPY/QQQ/IWM/DIA: base / up / down, triggered by the nearest board levels around the current price, targets the next level (or one implied move when the next level is more than 5 daily moves away), size from the daily move and the straddle, what followed the same reaction in history (a scenario is marked only where history measured a lean), and the expression (options cheap / fair / rich vs history, runway 2x the horizon). A time-ordered checklist for the next session. Where the opportunity is. What would change the view. The jigsaw: every input (measured, models, LLM narratives) with what it points to, whether it agrees with the tape and how fresh it is; missing is shown as missing. Sentences come from measured fields; wording is in `config["session_plan"]`. CSV buttons on the scenarios, checklist and jigsaw. |

## Decision aids (thesis review, 6 Oct 2026)

These are labels and measurements for the human. None of them is a permission or a probability.

- **Observation dates:** each condition tile shows the date of the data it used and how many
  sessions old it is. The Money Index card lists the dates of the values inside the packet.
- **80% interval** and **price-only lean** sit beside every measured lean. The scorecard
  compares the board's leans with price-only leans, which shows what macro adds.
- **Path-dependent products** (leveraged, inverse, volatility) get no 5d or 20d lean.
- **Move made:** 5d and 20d return in units of the ETF's own realised vol.
- **Response:** supporting / absorbing pressure / rejecting relief / mixed / insufficient. It
  uses the signs the board has measured for each ETF.
- **What the option market charges:** the ATM straddle from MarketData chains in the phantom DB,
  on the first expiry covering the horizon. It is compared with the analog mean absolute move.
- **Pipeline proposal:** direction, verdict, target and invalidation from the newest full run,
  read-only. Distances to target and invalidation, and the share of the move already used, are
  measured from today's close.
- **Uncalibrated labels** sit on the Money Index score, event confidence and news fragility.
  The Money Index is scored by its own ladder band on the Scorecards tab.
- **Holdings (issuer daily files):** State Street for SPY and DIA (xlsx), Invesco for QQQ (JSON).
  `--refresh` downloads them and archives the raw bytes under `output/holdings/raw`. If a
  download fails, the last good file is kept and marked stale. The board shows each holding's
  contribution (start-of-window weight × return), the top contributors and detractors,
  participation (share of weight above its 50-session mean) and unpriced weight.
- **tastytrade metrics:** IV index, IV rank and percentile, HV 30/60/90, IV−HV, beta, SPY
  correlation and the IV term structure, plus an IV-implied |move| beside the straddle move.
  `--refresh` fetches them through the read-only `bridge.tastytrade_readonly_mcp`, which needs
  the broker OAuth environment (`TASTYTRADE_CLIENT_ID` / `_SECRET` / `_REFRESH_TOKEN`). Without
  it the fetch fails cleanly, the board keeps the last snapshot and marks it stale after 30 h.
  The bridge returns all 115 ETFs. Thirteen leveraged/inverse products carry adjusted
  (post-split) option chains, which are left out of the IV term structure. The provenance
  notice appended by the tastytrade MCP server (21 Sep 2026 build) is accepted by the bridge
  and never parsed as data.
- **Momentum history (rev e):** each ETF's own streak and 5d/20d extension, with what followed
  similar runs (independent windows, intervals, holdout). Extended moves are measured, never
  assumed late. On 6 Oct 2026, SPY/QQQ runs of 5+ up closes had continued (next 20d +2.19%/+2.86%
  against +0.92%/+1.18% normal).
- **Desk card (rev e):** the six desk questions filled for every pipeline candidate and index
  ETF. Checks cover macro lean, momentum, room left, option price, data and event risk; they
  describe evidence and never decide. The card adds a stale-target note when measured
  continuation (interval clear of zero and beating normal drift) exceeds the room left. The
  trader's decision is downloadable as a JSON record for `output/journal/`.
- **Input archive:** each build stores a content-addressed copy of every file it read in
  `output/inputs/`; the manifest goes in that day's snapshot.

## Design

| Module | Role |
|---|---|
| `sources.py` | Read-only loaders. Every file carries its as-of time and FRESH / STALE / MISSING status. |
| `conditions.py` | Point-in-time condition states. Trend, vol and breadth reuse `avshunter.c12_outcome.conditions.market_condition` and the registry settings, so the board and the outcome scorer agree. |
| `evidence.py` | Forward returns, adaptive analog depth, independent windows, lean, holdout check, per-condition sensitivity. |
| `scorecard.py` | Scores the regime model, the archived packets, the Money Index ladder and the board's own snapshots (against price-only leans). |
| `momentum.py` | Streaks, extension states and what followed similar runs per ETF. |
| `desk_card.py` | Desk card checks (direction vs evidence, room left, option price, stale target) and card assembly. |
| `decision.py` | Move already made, response label, remaining opportunity against the pipeline's target and invalidation. |
| `review.py` | Daily review section 1: reading per instrument (gap, path, close vs threshold), label history and its record via `evidence.ticker_evidence`, information items, disagreements, headline. Config `config["review"]`. |
| `decision_points.py` | Daily review section 2: sessions ahead, holidays/short sessions, releases, FOMC, constituent earnings (`canonical_data.marketdata_earnings`, cached in `output/external/earnings/`), unscheduled developments, next-session reassessment list. Config `config["decision_points"]`. |
| `market_prices.py` | The board's own prices (ACK 9 Oct 2026): fills completed sessions the pipeline store lacks from Polygon grouped daily (cached, whole gaps only, never overwrites the store; the gap limit counts only sessions not yet cached, so the 37 ETFs and RSP/UUP the pipeline never fetches stay current) and takes one Polygon snapshot per refresh build so pre-market / intraday / after-hours quotes supersede the close for room, levels and focus cards. Config `config["prices"]`. |
| `session_plan.py` | Next session plan: tape, call, scenarios, expression, checklist, opportunity, what changes the view, jigsaw. Reads the assembled payload only; never scores, ranks for the pipeline or gates. Config `config["session_plan"]`. |
| `opportunity.py` | Daily review section 3: leadership and breadth, sector relative-vs-absolute labels, constituent confirmation, price room. Thresholds in `config["opportunity"]` (provisional). |
| `rotation.py` | Rotation coordinates and quadrants, relative forward returns, quadrant evidence and transitions, mapping packet sector names to ETFs (via `config/sector_etf_map_v1.json`), lead/lag scoring. |
| `options.py` | ATM straddle implied move from executable chain quotes (read-only phantom DB). |
| `build_board.py` | Orchestration, payload, HTML render. |
| `config/macro_board_config_v1.json` | Every threshold, band, lag and horizon, with its rationale. All are PROVISIONAL. |

Tests (business rules, no live data):

```powershell
venv\Scripts\python.exe -m pytest macro_board/tests/test_macro_board_rules.py -q -p no:cacheprovider --basetemp=$env:TEMP\avs_mb
```

## Known data gaps (6 Oct 2026)

- The pipeline's fetcher never writes UUP and RSP (last stored 2026-08-20) or 37 ETFs dropped from its universe on 16 May 2026
  (last stored 2026-05-15). The board fills them from its grouped-daily cache; see `market_prices.py`.
- IEF, SHY, TIP, MDY, VTI, VOO, IVV and others have only 63–92 sessions. They show price data
  only ("Short history").
- The VIX index has no history in the store, so the vol condition uses SPY realised vol. VIX
  term structure appears as advisory only.
- HY OAS history in the FRED master starts in Oct 2023, so the credit condition uses HYG vs LQD
  (full history).
- The archived macro packets often keep several projections of one generation, and some drop
  the BULLISH/BEARISH qualifier. The scorecard resolves each generation to one call and
  reports the counts.
