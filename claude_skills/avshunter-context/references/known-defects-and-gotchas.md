# Known defects and gotchas (historical audit findings)

These were found by prior audits (mostly Aug–Sep 2026, before the
spec-governed rebuild and the `avshunter/c12_outcome` package existed).
**Treat every item here as "was true as of the date given, verify before
relying on it"** — the rebuild is explicitly meant to fix these, and CLAUDE.md
rule 4 means fixes land in the existing modules rather than a parallel
system, so the surface area looks the same even after a fix lands. Don't
report one of these as a live bug without re-checking the current code.

## Units / field-collision bugs (classic AVSHUNTER failure mode)

- `spread_pct` has had two writers disagreeing on percent-vs-fraction
  (`lab_control.py` percent; `morning_gate.py` / `execution_gate.py`
  fraction) — a recurring pattern in this codebase: the same field name
  reused with different units by different writers. When a metric looks
  implausible (e.g. capped at exactly 2.0, or an entire book failing one
  gate), check for a units mismatch before assuming the logic is wrong.
- `opportunity_tier` showing `BLOCK` on every row was traced to a
  fraction-vs-percent constant mismatch (`SPREAD_TIER_2_MAX=0.25` fraction
  compared against a percent input), not a real veto.
- GARCH forward-variance fields (`layer3_forward_variance.py`) have been
  found to be *differences of cumulative moves* rather than the
  independent-window values their names imply, making the 6–10 day/11–20
  day fields smaller than the 1–5 day field on effectively all rows.

## Silent-neutral / fail-open bugs (the exact thing Invariant B forbids)

- Convexity score has been found constant (a placeholder value) because
  the compute function was called on a pre-economics row with an empty
  dashboard — a case of a failed computation returning a neutral-looking
  number instead of an explicit missing-data state.
- Vanguard fail-open protection has been found gated by a data-plane
  boolean with defaults of `False` whose only producer was a flag-gated
  stage — meaning "protection off" could look identical to "protection
  passed."
- Direction resolution has previously hardcoded `else: 'CALL'` on
  ambiguous/unresolved evidence — the opposite of Invariant B. The spec's
  direction-governance rule is explicit: `UNRESOLVED` must never default to
  a direction.

## Quote freshness / timing

- Morning Gate has been found evaluating rows on stale quotes (timestamped
  from the prior session) without the 15-minute freshness rule catching
  it, because the run itself was executed intra-session (mid-trading-day)
  rather than at the designed pre-open time — this produced misleading
  "most rows fail liquidity" results that were actually a run-timing
  artefact, not a pipeline defect. **Before trusting any book-level
  pass/fail statistic, confirm the run was executed at its intended time**
  (Evening after session close, Morning pre-open) — an intra-session run
  is not representative.

## Monetisability / target-reachability

- "Monetisable" has been computed as *expiry intrinsic value at the
  structural target* in places, which is a different (usually much larger)
  number than what's reachable within the actual hold window — this
  produces false-looking edge. The spec's Valuation context (C8) fixes
  this by using a common path set with forced exits at the hold window;
  if you see monetisability computed any other way in legacy code, it
  predates that fix.
- Targets/stops have been found effectively unbounded in the legacy
  Discovery/Options Intelligence code, driving the "target several multiples
  of the expected move" pattern.

## Macro / USMI join

- The macro-to-ticker join has repeatedly failed silently (empty
  `gics_sector`, `macro_ticker_context_available: 0`), producing
  `UNMAPPED` on effectively every row rather than an explicit join
  failure. If a macro-alignment field looks uniformly `UNMAPPED` or
  `UNVERIFIED`, check the join key before assuming there's no macro signal
  for that universe.
- Regardless of join health: macro/USMI/GEX are display-only by spec
  (rule 6) — a working join still must never be wired into a gate, score,
  or rank.

## General debugging heuristic for this codebase

Given the above pattern, when a metric looks wrong the most common root
causes, roughly in order of historical frequency, have been: (1) a units
mismatch between two writers of the same field name, (2) a run executed at
the wrong time relative to market session boundaries, (3) a silent
neutral/default value standing in for a missing computation, (4) a join or
lookup failing silently rather than raising. Check these before assuming
new logic is needed.
