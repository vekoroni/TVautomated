# P0-4 (slice 1): daily chain capture for open records, one adapter, labelled marks

18 September 2026 · for ACK approval before code (CLAUDE.md: no pipeline change without an approved root cause and
design) · owner context C1 market data · parent plan `PHASE0_PLAN_AND_BACKFILL_DESIGN.md` §P0-4

## 1. Root causes (measured)

| # | Finding | Evidence |
|---|---|---|
| RC1 | Option chains reach the store only for the evening run's **candidates**, plus any manual backfill. A ticker that drops out of the candidate list loses its daily marks while a ticket on it is still open (blueprint B3). | 16 and 17 Sep: 1,339 and 1,359 tickers stored (candidates only). 14 and 15 Sep: about 2,780 (full backfill). |
| RC2 | The MarketData chain adapter always sends `date=` (GEX-D9). The provider rejects `date` for the current session, so a same-evening request fails. | `canonical_data/marketdata_option_chain.py:89`. Evening GEX refresh failed on 14, 16 and 17 Sep with "HTTP 400: date is for historical queries only"; it succeeded only when run the next day. |
| RC3 | Production marks are already exact-date: `ChainQuotes` does point lookups with "no nearest-date substitution", and a missing mark stays `MARK_UNAVAILABLE` and is retried. But nothing reports how many open tickets are waiting on a missing mark, and outcome events do not record the quote date they used. The weekly-versus-daily difference is therefore invisible to a reader. | `avshunter/c12_outcome/adapters/chains.py`; `signal_service.score_signals` skips non-CLOSED outcomes. |

## 2. Design

1. **One adapter rule (fixes RC2).** `MarketDataOptionChainAdapter.fetch` sends `date` only when the requested session
   is before today's exchange date. For the current session after the close, it sends no `date`. Every returned chain
   is validated against the requested session using the rules that already exist for benchmark chains (timestamp
   coverage ≥ 80%, timestamps in the session, near the close); a chain that fails is refused, never stored.
2. **Capture set (fixes RC1).** A new evening step runs after the options stage and before C12 outcome scoring. It
   captures:
   - **open records:** tickers of every issued ticket in the Decision and Outcome Ledger with no CLOSED outcome and
     `last_usable_session ≥ session`;
   - **benchmarks:** as built, SPY and QQQ stay with the existing completed-session GEX refresh at the start of the
     evening run. That refresh uses the same fixed adapter, so it now works on the same evening, and the two steps
     never fetch the same chain.

   It skips any contract already stored for the session in `chain_snapshots`, so the run never fetches twice or
   overwrites stored data. The request window for each ticker reaches its latest open expiry, which matters because
   contracts are now often 64–92 days out.
3. **Store and project with receipts.** Reuse the existing path: canonical store → projection outbox →
   `deliver_phantom_option_events` → projection receipt check. `CanonicalBenchmarkOptionChainStore` is generalised
   with a `purpose` (MARKET_REFERENCE_GEX or OPEN_RECORD_MARK) instead of adding a second store. The existing
   completed-session GEX refresh then uses the same adapter rule, so it works on the same evening.
4. **Budget.** Credit use is capped by `market_data.daily_credit_budget`, and the step reports what it spent. The
   open-record set is small: at most about 5 tickets a day × 20 sessions, before de-duplication against candidates.
   The step is non-critical: a failure is recorded, never silently skipped.
5. **Coverage and labelling (fixes RC3).**
   - Each run writes `capture/open_record_coverage_<run>.json`: open tickets, tickers needed, captured, skipped as
     already present, failed (with reason), and credits used.
   - Every signal OUTCOME event records `mark_quote_date`, which always equals the exit session because lookup is
     exact.
   - The signal report counts tickets waiting on a missing mark, and lists them.
   - Production never substitutes the nearest date.
   - Research scripts that use non-exact marks label every mark with its gap in days (done in
     `legacy_signal_scoring.py`).
6. **Out of scope.** The full nightly panel (about 3,300 tickers, about 26,500 credits a session) stays a manual
   backfill for now. Point-in-time universe (P0-5).

## 3. Configuration

As built, this slice reads `market_data.daily_credit_budget` in the evening stage as the request cap. The request
window is at least 60 days and reaches the latest open expiry.

The other `market_data.*` keys (chain offsets, strike limit, benchmark list, settlement delay) belong to the
full-panel capture, which remains the rest of P0-4. They stay in `PENDING_CONSUMERS` because the key-reference test
scans only the `avshunter/` package.

## 4. Tests (written first, business language)

- A same-session request carries no `date`; a past-session request does.
- A returned chain whose timestamps are not in the requested session is refused.
- The capture set is open tickets' tickers plus benchmarks, minus tickers already stored for the session.
- A closed ticket, or one past its last usable session, is not captured.
- A ticket whose ticker is no longer a candidate still gets its daily mark (the RC1 scenario, end to end with fakes).
- The credit budget stops fetching and is reported.
- A capture failure does not stop the run and is reported.
- The outcome event records `mark_quote_date` equal to the exit session.
- A missing mark stays `MARK_UNAVAILABLE`, is counted in the report, and is never nearest-date substituted.
- Characterisation first: the current adapter always sends `date`, which pins today's GEX-D9 behaviour.

## 5. Order and safety

The code is built in an isolated worktree while any pipeline run is in progress, and merged only after it finishes.
It is tested with fakes and never touches live `data/` or the provider. The first live use is the next evening run
after ACK approves.
