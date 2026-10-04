# AVSHUNTER — build_local_gex.py permanent fix
# Save as: C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\scripts\CLAUDE.md
# Deploy: cd C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\scripts && claude → type: go

## Role
You are a quant engineer working in the AVSHUNTER pipeline. Fix build_local_gex.py
so it never hard-fails on a missing chain again.

## The problem
build_local_gex.py derives an expiry date from the --session argument and fails
with "chain unavailable for SPY/YYYY-MM-DD" if that chain is not in local storage.
This happens every time:
- The derived expiry is today (chain not settled yet)
- The derived expiry is yesterday (chain expired, removed from provider)
- The Colab pull hasn't run yet for this session

## The fix — three-layer fallback

### Layer 1 — forward-roll
If the derived expiry chain is missing, scan forward up to 5 trading days
and use the nearest available chain. Log at WARNING level:
  WARNING: chain SPY/YYYY-MM-DD unavailable — rolling forward to SPY/YYYY-MM-DD2

### Layer 2 — backward-roll
If no forward chain found within 5 days, scan backward up to 5 trading days
and use the nearest available chain. Log at WARNING level:
  WARNING: no forward chain found — rolling backward to SPY/YYYY-MM-DD2

### Layer 3 — graceful degradation
If no chain found in either direction, write the following JSON to the output
path and exit with code 0 (never block the pipeline):

{
  "status": "GEX_UNAVAILABLE",
  "reason": "no_chain_in_store",
  "fallback": true,
  "session": "<session argument as passed>",
  "tickers": {}
}

Log at ERROR level:
  ERROR: no GEX chain available for any expiry near YYYY-MM-DD — writing GEX_UNAVAILABLE sentinel

## Implementation rules
- Read existing chain discovery logic first before writing any code
- Fix goes into chain resolution function only
- Do NOT touch: GEX calculation logic, output schema (beyond adding fallback_used), CLI argument parsing
- Add --fallback flag (default: true) — when false, restore original hard-fail behaviour
- Log every fallback at WARNING level with old and new expiry dates
- Add "fallback_used": true/false field to output JSON for downstream consumers to detect

## Verification — test all three layers

Layer 1 (forward-roll): session where derived expiry is today or future
  python scripts\build_local_gex.py --session latest-completed

Layer 2 (backward-roll): force a session far enough out that forward roll exhausts
  python scripts\build_local_gex.py --session 20261015

Layer 3 (graceful degradation): session so old no chain exists in either direction
  python scripts\build_local_gex.py --session 20200101

Expected in all cases: exit code 0, valid JSON written to output path, "fallback_used" field present.
