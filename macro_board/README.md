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

## Run

```powershell
.\Run-MacroBoard.ps1            # refresh holdings + tastytrade metrics, build and open
venv\Scripts\python.exe -m macro_board --as-of 2026-09-15   # measured layers as of a past session
```

A build takes about 40–90 seconds. The first run also caches the breadth panel, keyed on the
price store's size and modification time. Output:

- `output/etf_macro_board.html`: a self-contained page; open it in any browser.
- `output/snapshots/board_<session>.json`: the leans shown that day. Later builds score them on
  the Scorecards tab.

Build after the macro refresh, or before the open alongside the morning run.

## Pages

| Tab | What it shows |
|---|---|
| Overview | SPY/QQQ/IWM/DIA cards: leans per horizon, dealer gamma and price state. The 10 macro conditions with their history. What changed. Analog depth and recent analog episodes. Packet headline. |
| ETF matrix | All ETFs by group, with returns, relative strength, trend, realised vol, lean, analog vs base mean, independent windows and packet lead/avoid. Click a row for evidence by horizon and by condition. |
| Transmission map | ETF × condition heatmap: how each ETF's forward return differed while each condition sat in today's state. |
| Macro intelligence | LLM packet, US Money Index transmission score and triggers, event risk, news overlay, VIX complex, GEX, rates/credit, liquidity, Colab models, FRED prints, threshold flags. Each shows its source, as-of time and freshness. |
| Scorecards | Colab regime model, archived LLM packets (latest wins per session) and the board's own leans, scored from the next open. |
| Method | Definitions, thresholds, point-in-time rules and limits. |

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
- **Input archive:** each build stores a content-addressed copy of every file it read in
  `output/inputs/`; the manifest goes in that day's snapshot.

## Design

| Module | Role |
|---|---|
| `sources.py` | Read-only loaders. Every file carries its as-of time and FRESH / STALE / MISSING status. |
| `conditions.py` | Point-in-time condition states. Trend, vol and breadth reuse `avshunter.c12_outcome.conditions.market_condition` and the registry settings, so the board and the outcome scorer agree. |
| `evidence.py` | Forward returns, adaptive analog depth, independent windows, lean, holdout check, per-condition sensitivity. |
| `scorecard.py` | Scores the regime model, the archived packets, the Money Index ladder and the board's own snapshots (against price-only leans). |
| `decision.py` | Move already made, response label, remaining opportunity against the pipeline's target and invalidation. |
| `options.py` | ATM straddle implied move from executable chain quotes (read-only phantom DB). |
| `build_board.py` | Orchestration, payload, HTML render. |
| `config/macro_board_config_v1.json` | Every threshold, band, lag and horizon, with its rationale. All are PROVISIONAL. |

Tests (business rules, no live data):

```powershell
venv\Scripts\python.exe -m pytest macro_board/tests/test_macro_board_rules.py -q -p no:cacheprovider --basetemp=$env:TEMP\avs_mb
```

## Known data gaps (6 Oct 2026)

- UUP and RSP stop at 2026-08-20 in the price store. They show as STALE on the board.
- IEF, SHY, TIP, MDY, VTI, VOO, IVV and others have only 63–92 sessions. They show price data
  only ("Short history").
- The VIX index has no history in the store, so the vol condition uses SPY realised vol. VIX
  term structure appears as advisory only.
- HY OAS history in the FRED master starts in Oct 2023, so the credit condition uses HYG vs LQD
  (full history).
- The archived macro packets often keep several projections of one generation, and some drop
  the BULLISH/BEARISH qualifier. The scorecard resolves each generation to one call and
  reports the counts.
