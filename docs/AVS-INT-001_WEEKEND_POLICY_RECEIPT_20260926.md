# AVS-INT-001 — Options ticket policy on non-session dates

**Status: IMPLEMENTED_PENDING_LIVE_ACCEPTANCE.** The operator starts the
Evening pipeline; this change used no provider API, broker tool or database
write and does not alter the universe or capital allocation.

## Confirmed root cause

`scripts/avshunter_options_intelligence.py` resolved
`outcome.signal.max_entry_spread_fraction` using `_iv_evidence_session()`.
Outside an orchestrated run that function can return today's calendar date.
On Saturday 26 September 2026 the governed registry rejects that date because
it is not an XNYS session. The function returned `None` and cached it for all
later rows, incorrectly labelling the ticket limit unavailable even though
the prior completed session has the configured 0.10 value. This is a policy
lookup/data-quality defect, not evidence that a wide spread is tradeable.

## Correction and boundaries

The lookup now normalises its date with the existing XNYS-calendar helper,
keys a successful cached value by resolved session and does not cache a
failed registry read. On a failure it continues to report unavailable; it
does not insert a literal default. Both calls and puts retain their observed
spread and the review flag rather than losing the contract or changing the
ticker thesis. The current `rr_options_*` telemetry remains a research
artefact, not a calibrated expected-return or a Lab trade authority.

The pre-fix governed-registry and explicit Saturday tests failed. After the
repair, the options-economics, direction, IV-owner, Lab-display and macro
publication selection passed **82 tests**. The operator's normal Evening run must still verify the
policy lookup's resolved session, quote provenance and ticket-state output.
