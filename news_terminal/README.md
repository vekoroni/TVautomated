# AVSHUNTER News Terminal v1.3

Bloomberg-style global market narrative, corporate-event and session-transmission intelligence engine.

## Quick Start

```
1. Double-click install.bat  (first time only)
2. Double-click start.bat    (every session)
3. Type /brief to run
```

## Commands

| Command | Purpose |
|---|---|
| `/brief` | Full global session intelligence brief |
| `/event "text"` | Analyse a specific news event |
| `/map` | Beneficiaries, losers and companies worth analysing |
| `/forward` | Forward-looking impact view with FIPS |
| `/ticker-csv` | Create curated ticker candidate CSV |
| `/handoff-csv` | Create full narrative/event handoff CSV |
| `/watchlist` | Watchlist-only candidates |
| `/mna` | M&A, strategic reviews and activist signals |
| `/sector TEXT` | Sector narrative brief |
| `/risk` | Stale, crowded, source, options, thesis risks |
| `/sources` | Confirmed / assumption / missing data |
| `/refine` | Reduce to highest-quality names only |
| `/reset` | Clear session, keep rules active |
| `/status` | Show current session summary |
| `/exit` | Close terminal |

## Scheduled Runs (Auto)

After running install.bat, the terminal runs automatically:
- **06:30 ET** — Morning: Asia/Europe digest + /brief + /mna
- **12:00 ET** — Midday: Intraday update + /brief
- **17:30 ET** — Evening: After-hours + next-day setup + /brief

## Output Files (per run)

```
outputs/daily/YYYYMMDD_HHMM/
  news_terminal_YYYYMMDD_HHMM.csv       Ticker candidates (Excel-ready)
  handoff_YYYYMMDD_HHMM.csv             Full event handoff
  macro_delta_YYYYMMDD_HHMM.json        Macro enrichment delta
  brief_YYYYMMDD_HHMM_full.html         Full trading brief (open in browser)
  brief_YYYYMMDD_HHMM_trader.html       Subscriber newsletter
  brief_YYYYMMDD_HHMM_summary.txt       Free tier / social summary

outputs/
  catalyst_calendar_master.csv          Running master (deduplicated)
  scheduler.log                         Scheduled run log
```

## Governance

- `execution_permission = NONE_NEWS_TERMINAL_ONLY` (hardcoded, cannot be overridden)
- `capital_grade = NO` (hardcoded, cannot be overridden)
- Terminal is analysis-only. It does not trigger AVSHUNTER or allocate capital.
- Human remains the capital gate.

## File Structure

```
news_terminal/
  news_terminal.py              Interactive entry point
  news_terminal_engine.py       API + session state + prompt builders
  news_terminal_commands.py     Command router
  news_terminal_outputs.py      CSV/JSON/HTML writers
  news_terminal_scheduler.py    Scheduled runner
  system_prompt_v1_3.txt        Intelligence instructions
  install.bat                   Setup + Task Scheduler
  start.bat                     Launch terminal
  README.md                     This file
  outputs/
    daily/                      Timestamped output folders
    catalyst_calendar_master.csv
    scheduler.log
```
