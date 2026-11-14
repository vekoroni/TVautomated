# AVS-TRADE-001: Codex v4 design review

Date: 14 November 2026. Reviewer: the separate Codex review chat. Decision authority: ACK.

**Outcome: R1, R2 and C1–C5 are substantially resolved in design. R3 still needs a targeted freshness/provenance correction.** The sampling grid is consistent with the inspected timing owners when implemented as specified below. This is design review, not implementation acceptance or approval of section 15.

Reviewed: the v4 request and design, the saved v3 review, and local timing/calendar, semantic-freshness, quote-feed policy, valuation and liquidity interfaces. No tests, benchmarks, providers, pipelines or broker actions were run by this reviewer. Only this review document is written.

## Important snapshot qualification

The request/design say “nothing is built” and refer to proposed changes. The current inspected workspace already contains v4-labelled implementation: domain/crossing_scenario.py, domain/quote_provenance.py, a crossing wrapper in domain/anticipated_move.py, raw-return changes in domain/option_valuation.py and quote_tier in domain/option_contract_liquidity.py. Their presence is direct evidence that the request's state description is stale. It does not establish who authorized or completed those changes, or whether any commit/release occurred.

I have not treated their existence as approval, run their tests, audited the complete implementation, reverted anything or taken write ownership. Before the next handover, update the design/request state and identify the actual implementation snapshot, approval record and writer interval. Do not claim this review certifies existing code. The files also differ from the design's proposed locations/signature: provenance is in domain/quote_provenance.py and crossing in domain/crossing_scenario.py, with an optional crossing mapping at the anticipated-move boundary. Reconcile the file/interface list rather than documenting an implementation that no longer matches the tree.

## R1–R3 and C1–C5

| Point | Disposition | Assessment |
|---|---|---|
| R1: raw return and multiplier | Resolved in design | Section 9 names the raw owner, preserves the four-place wrapper, bounds/validates stress input and leaves entry fees/ask unchanged. Existing None/error behaviour must also remain compatible. |
| R2: boundary actually searched | Resolved in design | Arrival/usable/cap states, tie order, search end, no usable window and headline rules are explicit. The small cap=5 fixture can exercise a pure search helper without weakening the governed production cap minimum of 20. |
| R3: quote provenance owner | Partly resolved | evaluate_freshness is a suitable semantic session/age primitive, not the complete Morning quote policy. The direct raw-age TTL test conflicts with the existing provider-delay convention and does not establish spot/IV freshness. See required correction below. |
| C1: Morning grid | Resolved in design | First close strictly after A aligns the scenario with completed-session countdown. Requires New York dates and explicit inclusive E, not unchanged date-only session arithmetic. Details below. |
| C2: candidate pool | Resolved in design | Sequential survivor counts, preferred-delta narrowing and above-limit fallback are now explicit. Section 4's shorthand “within spread limit” should refer to section 7's fallback; it is not a new filter. |
| C3: state precedence | Resolved in design, with ordinary input validation details | Origin geometry versus reached target is now ordered; unknown thesis status and pricing failure remain explicit. Validate origin spot, direction, positive strike/IV and dates before evaluating geometry/pricing; missing origin spot must not fall through to a reached/wrong-side conclusion. |
| C4: Lane B compatibility/names | Resolved in design | Caller settings, 1e-9 tolerance and new quote_tier names address the concern. Pin exact tuple reasons and spread units as well as tier letters; only the crossed-quote case may change under the declared compatibility scope. |
| C5: benchmark/reproducibility | Resolved as a release plan | Fixed cap/parameters, hashes/versions, full Morning population and the candidate-input precheck are adequate. They remain proposed and unmeasured by this review. No silent candidate synthesis or selective workload reduction. |

## Sampling-grid answer

Yes: section 5 is consistent with remaining_hold, sessions_between and after_sessions **as a grid adapter over those helpers**, not by applying each helper unchanged to date(A).

remaining_hold counts completed sessions strictly after the frozen origin; before today's close it does not spend today. after_sessions advances strictly after its input date. Thus Morning j=1 must use today's date, implemented as after_sessions(today,j−1), while an assessment at the close must advance to the next session. A timestamp exactly at close counts that completed session and excludes that close from the future grid. Convert A to America/New_York before extracting today; a UTC date is not an exchange-session date.

Let F be the first grid date and L the last XNYS session on/before expiry. For valid dates, E is 0 if L<F, otherwise 1+sessions_between(F,L). Using sessions_between(date(A),expiry) unchanged on a pre-close Morning would miss today's grid point. Use grid_date(U) for a positive U; do not pass U directly to after_sessions(date(A),U) in both modes.

Concrete example, no holiday: origin Monday 9 November 2026, T=3. Evening grid is Tuesday 10, Wednesday 11, Thursday 12. Tuesday Morning has e=0,R=3 and the same three dates. At Tuesday close e=1,R=2 and the next closes are Wednesday and Thursday. The arrival date remains Thursday. The specified holiday/early-close fixtures should assert the same invariance and the actual expiry/U dates. This is reasoning from the inspected source, not an executed test result.

## Required R3 correction: compose session truth with the quote-feed policy

### 1. Do not silently replace effective-age freshness with raw-age freshness

canonical_data/session_clock.py:evaluate_freshness compares raw age to live_ttl_seconds for live domains. It does not know the provider's disclosed delay. The existing owner domain/long_option_execution.py:effective_quote_age_seconds uses max(0, raw_age−disclosed_delay). The governed option_quote_feed currently records 900 seconds of disclosed delay and a 900-second freshness window; tests/test_option_quote_feed_delay.py explicitly pins that convention and Morning's reuse of the owner.

For example, a quote 1,200 seconds old has effective age 300 seconds. The existing feed policy considers it within the 900-second window, while v4's direct evaluate_freshness(...live_ttl_seconds=900) returns STALE and makes the candidate provisional. That is a different policy. It may be a deliberate stricter research restriction, but it is not unchanged reuse of the existing Morning owner.

Recommended design correction: use evaluate_freshness/calendar functions for aware-time, future-time and session validity, and compose the existing effective-age/feed assessment for Morning freshness. Preserve the original quote timestamp, raw age, disclosed delay, effective age, provider/feed identity and policy version. Do not add delay to a stored timestamp or call a delayed quote real-time. Apply a delay only for the feed/entitlement for which it is actually established; unknown feed identity must remain explicit. If a stricter raw-age rule is desired instead, record it as a separate proposed policy for ACK and label its divergence.

Add fixtures at raw ages 900, 1,200, 1,800 and above 1,800 seconds for this governed delayed feed, plus a real-time feed, unknown feed and a future timestamp. Keep the existing pipeline's disclosure/authority behaviour unchanged; this correction is about the new comparison's provenance contract.

### 2. Morning requires provenance for the values being combined

The v4 Morning ALIGNED row checks option quote timestamp/session/OCC, but omits the spot and IV checks required in the Evening row. A fresh option bid/ask can therefore be combined with a stale fallback spot or IV from another contract/session and still be labelled ALIGNED. The current Morning caller has a signal-price fallback, so this is a concrete integration risk.

Specify the source identity and assessment for Morning spot and IV as well as bid/ask. Reuse their existing source/freshness policies; do not invent a new synchronization threshold. If current compatible spot/IV evidence is missing, label that combined result provisional with its precise reason and keep it out of the tradeable shadow. A fallback may be shown for research but must not inherit the option quote's freshness. Add a fresh bid/ask plus stale spot fixture and a repaired OCC with old-contract IV fixture.

### 3. Evening owner and saved-assessment answer

evaluate_freshness is appropriate for EOD_CURRENT when called with explicit now=A and a verified dataset session. It checks that dataset session against the last completed session; it does not itself validate the quote's closeness to the close or source identity. Keep the adapter's separate calendar/close-tolerance, spot/IV session and OCC checks.

With A fixed at the evidence close, a quote more than one second after A is INVALID under evaluate_freshness, even when within the symmetric 1,800-second close tolerance. State explicitly that post-assessment observations remain provisional/excluded from aligned evidence; the tolerance must not admit look-ahead data. Preserve the actual INVALID reason rather than labelling every failed EOD test as a session mismatch.

A saved assessment is reusable only if bound to the exact OCC, source observations/hashes, assessment instant, mode and policy/config version. A saved enum without those bindings is insufficient. For a new A or changed input, recompute through the owners. There is no need to replace the adapter with a generic saved SESSION_ALIGNED field. The adapter should live at a dependency-appropriate boundary; the current separate domain/quote_provenance.py already reflects that distinction, unlike section 8's proposed placement inside the data-layer-independent liquidity module.

## Handoff and approval boundary

The previously confirmed ETF state is explicitly parked, not committed. This review did not send a new request to that chat or recertify an exclusive filesystem lock. Section 2's ACK-confirmed handoff/writing interval remains a stated precondition; reconcile it with the implementation now present. The design's separate assertion that the Evening run awaits an ETF commit is reported as a document claim, not authorization here to commit or run anything.

Close the targeted R3 policy/input gap and reconcile the stale document/workspace state. R1, R2 and C1–C5 do not require another architecture revision. After ACK's actual decisions are recorded, assess implementation and saved-data evidence against the agreed snapshot. This review approves no build, commit, operational adoption, provider call or pipeline run.
