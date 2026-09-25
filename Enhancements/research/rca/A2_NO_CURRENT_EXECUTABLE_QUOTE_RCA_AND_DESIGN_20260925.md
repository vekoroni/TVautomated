# A2 — "PROVIDER_TIMESTAMP_MISSING" on rows that have no quote at all: root cause and design

**Date:** 2026-09-25 · **Owner of the change:** Morning Gate (`morning_gate.py`), existing owner of the post-open viability override · **Authority:** none changed; routing preserved (step 1 of the accepted sequence) · **Requested by:** ACK ("carry on with A2")

## 1. Symptom

On 24 Sep, 191 BLOCKED rows carried `execution_viability_reason = PROVIDER_TIMESTAMP_MISSING`; on 25 Sep morning, 205 rows. A reviewer reads that as a capture defect. It is not: 204 of the 205 have no contract symbol, no hydration and no bid or ask. There is no quote whose timestamp could be missing.

## 2. Root cause (confirmed)

`morning_gate.run_gate` first applies the governed policy `domain.long_option_execution.evaluate_execution_viability`, which already distinguishes the cases precisely: `DATA_MISSING / SELECTED_STRUCTURE_NOT_HYDRATED`, `DATA_MISSING / BID_OR_ASK_MISSING`, `DATA_MISSING / SELECTED_LONG_LEG_MISSING`, and `CURRENT_QUOTE_UNAVAILABLE / PROVIDER_QUOTE_TIMESTAMP_REQUIRED` for a present quote without a timestamp.

Immediately after (`morning_gate.py:2231-2242`), in `POSTOPEN_CONTRACT_REFRESH` mode, an override checks only whether a provider timestamp exists and, when it does not, overwrites state and reason with `CONTRACT_QUOTE_UNAVAILABLE / PROVIDER_TIMESTAMP_MISSING`. A row with no quote has no timestamp either, so the override collapses "no quote" and "quote without timestamp" into one label, discarding the domain's correct reason.

| Fact | Evidence |
|---|---|
| 205 rows with the label this morning; 204 have no contract symbol, no hydration status, no bid or ask; 1 has a two-sided quote without a timestamp | 25 Sep morning book |
| The domain policy's own reasons for those 204 would be `SELECTED_STRUCTURE_NOT_HYDRATED` (no hydration) | `domain/long_option_execution.py:214-241` |
| No consumer keys on the reason string; consumers key on the state (`selected_contract_economics_ready` excludes `DATA_MISSING / INVALID_QUOTE / UNSUPPORTED_STRUCTURE`; `opportunity_tier` keys on `DATA_MISSING`) | grep of morning_gate, contracts, domain, interpreter |
| No test covers the override | grep of tests for `PROVIDER_TIMESTAMP_MISSING` |

## 3. Design (routing preserved)

Extract the override into a pure function `postopen_quote_unavailable_override(out, live_data) -> dict` in `morning_gate.py` and call it at the same site. Behaviour:

| Case | State (unchanged) | Reason | New additive fields |
|---|---|---|---|
| Not POSTOPEN mode, or a provider timestamp exists | no override (as today) | — | — |
| POSTOPEN, no timestamp, a bid and an ask are present | `CONTRACT_QUOTE_UNAVAILABLE` | `PROVIDER_TIMESTAMP_MISSING` (as today; this is the real case) | `execution_viability_domain_reason` = the policy's reason, `execution_viability_reversible = True`, `execution_viability_recheck = NEXT_QUOTE_REFRESH` |
| POSTOPEN, no timestamp, no bid or no ask | `CONTRACT_QUOTE_UNAVAILABLE` | **`NO_CURRENT_EXECUTABLE_QUOTE`** | same three fields, domain reason preserved (e.g. `SELECTED_STRUCTURE_NOT_HYDRATED`) |

`execution_viability_eligible = False` and `executable_now = False` are set exactly as today in both override cases. The state string is deliberately unchanged so every routing consumer behaves identically; the reviewer's request for a reversible monitoring state is met by the reason and the `reversible / recheck` fields, which say the row re-enters when a quote appears. The three fields are projected to the Lab book and added to the ILA golden's additive list.

**Invariants.** Labels say what was measured (R6). One owner: the domain policy's reason is carried, not re-derived. Nothing revived, nothing killed: 0 rows change verdict or route (register amendment A2).

## 4. Tests (written first)

`tests/test_a2_no_current_executable_quote.py` against the extracted function:
- Characterisation of the routing-relevant outputs: in every override case, state `CONTRACT_QUOTE_UNAVAILABLE`, eligible False, executable_now False, exactly as the legacy block.
- No quote → reason `NO_CURRENT_EXECUTABLE_QUOTE`, domain reason carried, reversible, recheck named.
- Quote without timestamp → reason `PROVIDER_TIMESTAMP_MISSING`, domain reason `PROVIDER_QUOTE_TIMESTAMP_REQUIRED`.
- Quote with timestamp, or not POSTOPEN → empty override.
- Lab projection carries the three fields.

## 5. Result (implemented 25 Sep 2026, uncommitted pending ACK)

| Item | Outcome |
|---|---|
| Change | `morning_gate.py`: legacy 10-line block replaced by `postopen_quote_unavailable_override(out, live_data)`, called at the same site. `contracts/lab_control.py`: three fields in `FINAL_BOOK_FIELDS` and the projection. `tests/test_ila_selected_contract_identity.py`: golden additive list extended |
| Tests written first | `tests/test_a2_no_current_executable_quote.py`: 2 characterisation cases (state, eligibility, executable_now as the legacy block), 7 business-rule tests; all pass |
| Regression | ILA golden 7/7, morning state separation 5/5, quote feed delay 5/5, execution monetisability gate 9/9, DDD execution authority 16/16, OLM execution authority 27/27, book integrity 24/24; `--morning --plan-only` clean |
| Routing effect | None by construction: state, eligibility and executable_now unchanged in every case; no consumer keys on the reason string |

## 6. Acceptance

Tonight's evening run is EOD mode, so the override does not fire; the morning run on Monday will show `NO_CURRENT_EXECUTABLE_QUOTE` on the no-contract rows and `PROVIDER_TIMESTAMP_MISSING` only where a quote exists. Verdict and route counts identical to what the legacy block would have produced.
