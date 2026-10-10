# S1: quote-age effects inventory (RC7 / E13), 6 Oct 2026

**Rule being checked (standing ACK decision):** quote **age alone** has no authority to block, downgrade, re-rank, re-value or hide a row. It may only be disclosed. A missing, invalid, crossed, future-dated or wrong-contract quote is a different thing, and it may legitimately prevent a valuation.

**Method:** read-only trace of production code by an audit agent. A1 was re-checked by me in code and in run `20261006_060401`. Line numbers are as of 6 Oct 2026. Nothing was changed.

## A. Age-alone effects that break the rule (S2 candidates)

| # | Where | What happens | Effect | Verified in run data |
|---|---|---|---|---|
| A1 | `morning_gate.py:119` (`LIVE_STOCK_PRICE_MAX_AGE_SECONDS = 300`, a literal), :831–832 | A valid underlying price more than 5 minutes old is **thrown away** (`STALE_PROVIDER_PRICE`). The lifecycle then sees "no spot" and gives `CONTRACT_REPRICE_REQUIRED` → FLAG/NO_TRADE, or FLAG WAIT "LIVE_PRICE_UNAVAILABLE". The label says "unavailable" when the price was only old | GATE (indirect) + VALUATION | **Yes: 17 rows today** (lane A 6: 2 BLOCK and 4 FLAG; lane C 11). 12 went to CONTRACT_REPRICE_REQUIRED. None could be GO |
| A2 | `canonical_data/bundle_freshness.py:59–80`, `session_clock.py:218`; `pipeline_interpreter/assessment_contract.py:46–49, 118–129` | Option quote > 60 s, underlying > 30 s or structure > 120 s → `REJECTED_STALE_BUNDLE`. The Interpreter overlay is never added to the Lab | VISIBILITY | Not measured (Interpreter path) |
| A3 | `pipeline_interpreter/evidence_resolver.py:182–227, 253–255` | Same TTLs for executable-session use → `EVIDENCE_REFRESH_REQUIRED`; `/ticker` prints "MSI BLOCKED". **On a 15-minute delayed feed this fires for essentially every ticker** | GATE / VISIBILITY (Interpreter) | Not measured |
| A4 | `vanguard/ev_engine_v3.py:552–554, 854–855` | Quote age adds up to 0.01 "quote uncertainty", which lowers the EV3 lower bound and can flip `absolute_state` to INDETERMINATE | VALUATION (advisory) | Not measured |
| A5 | `vanguard/ev_engine_v3.py:1005–1007` | Ties between contracts are broken by quote age | RANK (contract choice, ties only) | Not verified that production uses multi-candidate selection |
| A6 | `domain/exact_contract_quote_join.py:224–235` → `pipeline_interpreter/war_view.py:120–121, 211–213` | Label `NOT_EXECUTABLE_STALE` because of age; age is counted as a coverage gap | DISPLAY (misleading) | — |
| A7 | `domain/pretrade_focus.py:146–150, 166–167` | A quote session different from the evidence session → `CONTRACT_EVIDENCE_CONFLICT_REVIEW`, priority 7, hidden by the Lab "Focus" filter | RANK + VISIBILITY | **Borderline.** It may be meant as an identity check (S1 to decide with ACK) |

## B. Dormant: no producer today, but the code would act if one appeared (retire in S2/S6)
- `stale_data` → BLOCK_DATA / size 0: `avshunter_monetisation_policy.py:196–198` (and its `scripts/` copy), `position_sizing_engine.py:122`, `final_decision_engine.py:464`.
- `execution_viability_state == STALE_DATA` → tier gate: `contracts/opportunity_tier.py:130–132`.
- "DELAY" in the quote source → `DELAYED_OPTIONS_DATA` turns a Lab GO into ARMED: `contracts/lab_control.py:2923–3000`, `intelligence_lab.py:1309–1316`. No writer found; upstream columns not verified.
- `live_validation_state == STALE` → critical Lab flag: `lab_control.py:2884, 2944`. The Morning gate never emits it, but two QA harnesses still expect stale → WAIT (`scripts/qa_morning_validator.py:111`, `qa_market_scenario_simulation.py:739–740`).
- `QUOTE_STALE` → maturation factor 0.55: `domain/option_contract_liquidity.py:50, 102–103, 157, 660`. No longer produced.

## C. Mislabels (break R6: labels say what was measured)
- `morning_gate.py:2231–2235`: `quote_freshness` = "FRESH" whenever the age is known. It flows to `confluence_evidence.py:202–204` ("MORNING_QUOTE_FRESH"), `lab_v4_quote_freshness` and the Lab "Fresh" column. Replace it with the disclosed `quote_age_minutes` and source; no fresh/stale verdict.
- `contracts/contract_rejection.py:35, 71–97, 125`: `REJECT_STALE_QUOTE` actually means invalid, crossed, negative or no positive mark. Rename it (e.g. `REJECT_INVALID_QUOTE`).

## D. Compliant (age only disclosed, or the trigger is missing or invalid data)
- `option_contract_liquidity.py:520–547`
- `long_option_execution.py:168–193, 288–294, 308–309`
- `ev3_stage0.py:467–496`
- `empirical_option_ev.py:250–251`
- `quote_change_evidence.py:184–259` (`quote_age_affects_thesis=False`)
- `trade-card.js:59–66`
- the EOD path (`EOD_QUOTE_PENDING_MORNING_REQUOTE` is non-blocking)
- cache reuse at `morning_gate.py:991, 1056` (operational, not a gate)
- C12 `QUOTE_PRIOR_SESSION` (measurement only)

## E. Staleness of other data (bars, macro, triggers): outside the quote-age rule, listed for ACK
| Where | Effect | Note |
|---|---|---|
| `trigger_layer.py:110` `TRIGGER_MAX_AGE_SESSIONS=2` (literal) → `trigger_go_eligible=False` | GATE: Morning FLAG `AWAITING_TRIGGER` (`morning_gate.py:2929–2939`); EOD tier and status; orchestrator 7893–7919 sets `capital_permission=NO` and size 0 | Trigger age is a **thesis-evidence** rule, not quote age. A literal threshold breaks the config rule. ACK to confirm it is wanted |
| `regime_consensus.py:245–263`: macro > 20 h → 0.85× haircut on macro scores | VALUATION | **Possible conflict with CLAUDE.md rule 6** (macro is display only); downstream use not verified (S1) |
| Discovery `is_stale` (bars > 5 days) → `candidate_lane=SUPPRESSED`; OI session-scope quarantine; descriptive forecast `STALE_BAR`; canonical history > 5 days not returned | GATE / VISIBILITY on **bar** age | Data-integrity rules. Keep, but they must be labelled as such |
| Bond packet > 26 h dropped; stale curve nulls scores; macro freshness labels; scanner manifest age | Advisory / display | Compliant with rule 6 |

## Priority for S2 (each still needs root-cause approval, test-first)
1. **A1:** keep the old price, disclose its age, and value with it. It blocked 17 rows today.
2. **A3 and A2:** the Interpreter treats a delayed feed as stale for every ticker.
3. **A4 and A5:** EV3 is re-valued and re-ranked by age.
4. **C:** both mislabels.
5. **B:** retire the dormant paths, and update the two QA harnesses that still expect stale → WAIT.
6. **E:** ACK decisions on the trigger-age literal and the macro haircut.

## F. The two staleness rules outside quote age, examined for ACK (6 Oct 2026)

**1. Trigger-age gate** (`trigger_layer.py:111` `TRIGGER_MAX_AGE_SESSIONS = 2`, a literal)
- **What it measures:** the age, in sessions, of the price data behind the trigger. This is not setup age: `days_in_range` is explicitly excluded (`trigger_layer.py:108–110`). It reads only explicit fields (`trigger_source_age_sessions`, `equity_data_age_sessions`, `price_data_age_sessions`, `market_data_age_sessions`, or an explicit freshness state).
- **Effect when it fires:** `trigger_stale=True` → `trigger_go_eligible=False` → Morning FLAG `AWAITING_TRIGGER` (`morning_gate.py:2929`). The orchestrator then sets `capital_permission=NO` and size 0 (`TRIGGER_DATA_STALE_WITH_EXECUTION_MODE`, :7920).
- **Run 20261006_060401:** it **fired on 0 rows**. All 1,636 rows are `trigger_freshness_state=UNKNOWN` / `NO_EXPLICIT_SOURCE_AGE`, because no producer writes those age fields. The rule is **dormant**.
- **Assessment:** a rule that stops trades on price bars more than 2 sessions old is a legitimate data-integrity rule (bar staleness, not quote age). The defect is that the threshold is a literal (config rule) and that nothing feeds it.
- **Recommended:** move the 2 to versioned config; keep the rule. It is low priority while dormant.
- **Related, not staleness:** 814 rows are not GO-eligible because they have **no trigger at all** (`trigger_primary=NONE`), including **153 lane A rows**. That is the separate rule "GO needs a trigger", visible as FLAG `AWAITING_TRIGGER`. ACK may wish to review it alongside the lanes.

**2. Macro-age haircut** (`regime_consensus.py:245–263`)
- **What it does:** if the macro packet is more than 20 hours old, four macro scores (net liquidity, VIX regime, GEX regime, macro momentum) are multiplied by 0.85, lowering the Regime Consensus Score and its Kelly sizing multiplier.
- **Where it runs:** only inside `enhancement_integration.py` (Phase 9B). That call is **commented out** in the orchestrator (`intelligent_orchestrator.py:6750`), and the reference run has no `rcs_*.json`. The haircut is **dormant**.
- **Assessment:** if re-enabled, it would let macro alter a score and a size, against CLAUDE.md rule 6 (macro is display only). It also contains `gex_regime_score = 0.50` "placeholder" logic (R1: missing is never neutral).
- **Recommended:** quarantine it on the retire list (role AUDIT): it must never be re-enabled with scoring or sizing authority.
- **Live side effect found while tracing:** `execution_gate.py:373–397` reads `rcs_label` (from that disabled layer). It is always empty, so it is never in `TRENDING_REGIMES`, and the "above gamma flip" warning is never bypassed. That warning is one of those that turn BUY_NOW into BUY_SMALL (S2 item #7, link 4). This strengthens the case for item #7.
