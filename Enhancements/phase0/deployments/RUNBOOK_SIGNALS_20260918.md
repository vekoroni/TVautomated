# Runbook — signal tickets, first live trial session (Fri 18 Sep 2026)

Decision support only. Tickets carry no capital authority (G1–G4 not passed); every trade is ACK's decision. Every
ticket is scored at real prices whether traded or not, so the track record grows each session.

## Tonight (Thu 17 Sep, after the US close 21:00 UK)

1. Confirm nothing is running: no morning job, no Phantom backfill.
2. Plan check, then the evening run (scoring runs automatically at the end):
   ```
   python intelligent_orchestrator.py --evening --plan-only
   python intelligent_orchestrator.py --evening
   ```
3. Check the evening options output has the value-model columns (`emp_path_*`, `emp_expression_preference`) and
   `l3_price_history_state`; these are what tomorrow's tickets are re-valued from.

## Tomorrow morning (Fri 18 Sep)

| UK time | Step |
|---|---|
| 14:30 | US open. Do not run before 14:45: the option feed is 15 minutes delayed. |
| ~14:45 | `python intelligent_orchestrator.py --morning --plan-only` — check VALIDATE on tonight's run id, session REGULAR |
| ~14:45 | `python intelligent_orchestrator.py --morning` (≈ 20–30 min). Must end with "Morning final handoff" and `DISPATCH_COMPLETE`, not `DISPATCH_FAILED` |
| after handoff | `python -m avshunter.c12_outcome signals` — issues tickets now, at current prices |
| then | Open `data/output/runs/<run_id>/signals/signal_tickets_<run_id>_2026-09-18.md` and review |

The ticket builder can be re-run later in the session (a new issue time re-values from the prices then); ticket ids
include the issue session, so the same session does not duplicate tickets.

## Reading a ticket

- **Expression / contract** — OPTION (bought) or SHARES (long for CALL, short for PUT).
- **Limit** — options: the issue-time mid; place a limit order at or inside it, never a market order.
  **Scored entry** — the ask the track record assumes (conservative).
- **Stop / Target / Hold** — underlying levels and planned sessions; exit at the first of these (options also before
  their last usable session, expiry minus 2 sessions).
- **Cautious / central / upside** — value-model return on capital at the issue-time premium (volatility range, exit
  at the bid). A ticket exists only when cautious is above zero.
- **Quote** — `CURRENT_SESSION` / `PRIOR_SESSION` and whether the delayed (15-min) quote was delta-adjusted to the
  issue instant. Flags, not gates: check the live quote in your broker before entering.
- **O4 / H9R** — information only (O4 put/call open-interest stance; H9R gap-up event). They never change eligibility
  or rank.

## Every evening

`python -m avshunter.c12_outcome all` runs after the evening pipeline: it scores open tickets (options at the exit
session's end-of-day bid) and writes the "Signal track record" section of `Enhancements/outcomes/<date>/outcome_report.md`.
The trust gate needs ≥ 40 closed signals over ≥ 15 issue sessions with the lower 90% interval bound above zero.

## Known limits (17 Sep 2026)

- MarketData options entitlement is delayed 15 minutes; the delta adjustment is first-order.
- EV3 (retired, advisory) still labels delayed quotes stale — ignore it.
- O2 is not recorded by the pipeline yet (shown as UNAVAILABLE).
- Direction has no demonstrated edge; expect many NEITHER rejections and roughly half of tickets to lose.
