# AVS-LEDGER-001: Card outcome ledger (traded and not traded)

Brief for Claude Code. Written 13 Nov 2026 for ACK. Branch from `laneb/lab-first-handoff`.

## 1. Why

AVSHUNTER has no record of what each card would have made. Without it no rule, ranking or exit can be proven.
Two things exist today, and neither answers the question:

- `track_outcomes.py` (v2) scores every decision-ledger row on the **stock** (target, stop, half target, MFE/MAE).
  It was last run on the 12, 13 and 14 Oct ledgers. Seven ledgers since (16, 19, 20, 22 Oct, 11 and 12 Nov) have never been scored.
- The post-close monitor writes `data\scratch\workaround\monitor\option_closes.csv` (closing quote of TRADE/WATCH/ENTER card
  contracts for 10 sessions). Nothing turns those quotes into a result per card.
- `collect_decisions.py` (B10) creates a decision record per card (`CARD_BUILT_DECISION_MISSING` if none), but records no outcome.

What ACK needs: for **every card, traded or not**, what the **option** did over the hold, so we know which cards pay,
what was left on the table, and which setups to rank first.

## 2. Scope

| Item | What |
|---|---|
| L1 | Backfill `track_outcomes.py` on every ledger that has no `_outcomes.csv` (stock outcomes, unchanged rules v2) |
| L2 | New `card_outcomes.py`: option outcome for every card, traded or not |
| L3 | Backfill L2 on every card since 14 Oct 2026 |
| L4 | Run L1 and L2 daily in `avs_day.ps1 eod` |
| L5 | One summary that ACK reads |

Out of scope: any change to the pipeline, the Lab, `data\output\runs\`, or a ledger's decision columns.

## 3. L2 rules (freeze as `card_outcomes_v1`; change only with a new version)

**Card population.** Every `*_deep_dive_*.html` card in every hand-off folder (`handoff\split_*` and `handoff\lab_*`), joined to its
`decisions\<TICKER>.json`. One row per card: ticker, side, contract, card session, decision (TRADE / WATCH / PASS / blank), traded (yes/no
from the order record), card entry price (card mid), target, first profit, stop, time stop, planned hold.

**Option price source, in this order, stamped on every row as `price_source`:**
1. `OBSERVED_FILL`: actual fill and exit for traded cards (order record or Tastytrade transactions, read-only).
2. `OBSERVED_CLOSE`: verified session close from `monitor\option_closes.csv`.
3. `PHANTOM_OBSERVED`: quotes in the PHANTOM store, including the 13 Nov 2026 backfills (20 Oct and 9 Nov scoped chains:
   standard contracts, 7–60 DTE, 40 strikes, OI ≥1, SPX/SPXW excluded; 44 longer-dated/ARKG quotes; 508 exit/path quotes
   13 Oct–5 Nov). Exact contract match only; a neighbouring strike or expiry is not a match. Record the quote time.
4. `MODELLED_BS`: Black-Scholes reprice from the stock close in `historical_prices.sqlite`. IV, in order: the contract's own
   PHANTOM IV nearest the session (`iv_source = PHANTOM`), else the card's entry IV held flat (`iv_source = CARD_ENTRY`).
   Use only when 1–3 are missing. Never mix modelled and observed in one number without the label.

Known gaps to report, not fill silently: 12 Nov (40 entry and 20 path quotes deferred); contracts over 60 DTE outside the
44 backfilled quotes (many Lab-selected contracts are long-dated, e.g. HSBC Jan 2027, CPNG Feb 2027); SPX/SPXW.
The summary shows the share of each result that is observed vs modelled.

**Entry.** Card mid on the card session (`entry_rule = CARD_MID`). If the card had a trigger that never fired, `NOT_TRIGGERED` and no P&L.

**Path, per session to the earlier of: planned hold, time stop, option expiry.**
- `mfe_pct`, `mae_pct`: best and worst option mid vs entry, in %.
- `sessions_to_first_profit`: first session the mid is at or above +30% (ACK's base-hit bar). Blank if never.
- `hit_first_profit`, `hit_target` on the stock (reuse track_outcomes rules) and on the option.
- `result_at_exit_rule`: P&L % under ACK's one-contract exit rule as written on the card (`one_contract_exit`); if absent, at the time stop.
- `result_hold_to_end`: P&L % at the end of the window.
- `status`: OPEN, CLOSED_RULE, CLOSED_HOLD_END, EXPIRED_WORTHLESS, NOT_TRIGGERED, NO_PRICE.
- `left_on_table_pct` (traded cards only): MFE minus realised P&L.

**Never** drop a card for missing data. Write it with the status and the reason.

## 4. L5 summary: `data\scratch\workaround\ledger\card_outcomes_summary.md` (plus `.csv`)

Win rate (result at exit rule > 0), median result, median sessions to first profit, share reaching +30%, by:
traded vs not traded; decision (TRADE / WATCH / PASS); ETF vs stock; realisation band (1–3, 4–10, 11–20, 21–60, >60 sessions);
coherence; money tag; side; contract covers q80 (yes/no); liquidity tier at entry; price source.
Each cell shows n. Cells with n < 10 are shown but marked `LOW_N`.

## 5. Constraints

- Read-only on `data\output\runs\`, the Lab, the price database and Tastytrade.
- MarketData: no new calls in the backfill (observed closes or model only). Daily run may use the monitor's existing capture.
- No Claude API calls.
- Commands for ACK in PowerShell, full paths.
- Tests: rules in section 3 each have a test; one fixture card per status.

## 6. Acceptance (two-level: code evidence and run evidence)

| # | Check |
|---|---|
| A1 | Every ledger in `data\scratch\workaround\decision_ledger_*.csv` has an `_outcomes.csv` and `_summary.csv` |
| A2 | Card count in `card_outcomes.csv` equals the count of deep-dive cards on disk (print both) |
| A3 | Every row has `price_source` and `status`; 0 rows silently missing |
| A4 | Recompute 5 random cards by hand from the source quotes; 0 differences (write `audit\ledger001\spotcheck.md`) |
| A5 | Reproduce the 23 Oct 40-card test (traded and not-traded cards since 14 Oct) within ±5 points on win rate; explain any gap |
| A6 | `avs_day.ps1 eod` runs L1 and L2 and the summary updates |

## 7. Receipt (required; no receipt = not done)

`audit\fix_receipts\AVS-LEDGER-001.md`: commits, files changed, tests run and results, counts (ledgers scored, cards scored, by price source),
A1–A6 results, anything deferred, and the PowerShell lines ACK runs.

## 7a. Shared change log (AVS-CHANGELOG-001)

Before starting, read the last 7 days of `data\scratch\workaround\lessons\change_log.md` and the open rows of
`lessons\fix_register.csv` (the existing log; do not create a second one) and list any open branch that touches your files. Append one line per commit and one per backfill run, with the receipt path and `run_evidence`.

## 8. Lines ACK will run (Claude Code to confirm or correct in the receipt)

Backfill stock outcomes, one ledger:
`& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\venv\Scripts\python.exe C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\track_outcomes.py C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\decision_ledger_2026-10-16.csv`

Card outcomes, full backfill:
`& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\venv\Scripts\python.exe C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\card_outcomes.py --backfill-since 2026-10-14`

Note: `track_outcomes.py` reads the price database from the current folder, so run it from the repo root
(`Set-Location C:\Users\ACKVerissimo\AVSHUNTER-Intelligence` first).

---

# Note on other branches (for awareness; not part of this brief)

Codex work since 11 Nov sits on unmerged branches: `phantom-scoring-iv-hold-fixes-20261111`, `fix/production-eligibility-20261112`,
`fix/ac-reliability-20261112`, `feat/a12-monetisation-clock-20261112`, `fix/station-quarantine-20261113`,
`fix/phantom-path-completeness-safeguards-20261113`. If `feat/a12-monetisation-clock-20261112` already computes a monetisation clock
from saved data, reuse its definitions for `sessions_to_first_profit` rather than inventing a second one, and say so in the receipt.
