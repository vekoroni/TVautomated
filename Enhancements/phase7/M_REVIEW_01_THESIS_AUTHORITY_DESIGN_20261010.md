# M-REVIEW-01 — Morning authority from the thesis, not the legacy Vanguard label

Status: **approved by ACK 10 Oct 2026 and implemented** (tests/test_m_review_01_thesis_authority.py); was design + replay (ACK 10 Oct 2026: "bring the design forward with replay"). Brings
forward part of output-trust item 11 (D2-1 Step B) for the Morning gate only. No pipeline code changed for this item.

## Root cause (traced on run 20261008_220129, Morning 9 Oct)

862 Morning rows were BLOCKED with `UPSTREAM_NOT_AUTHORIZED` / `UPSTREAM_CAPITAL_PERMISSION` before any contract repair
or review was tried. The chain:

1. Vanguard's legacy actuarial `signal_type` (STRUCTURAL_MATCH 789, CURRENT_EDGE 67, FUTURE_EDGE 6).
2. `execution_intelligence_runner.py` turns it into `capital_permission` = WATCH_ONLY ("STRUCTURAL_MATCH_NO_CURRENT_EDGE",
   lines ~1450 and the DEFANG pass ~3134) or NO ("CURRENT_EDGE_EOD_BLOCK:LIVE_CLEARANCE_REQUIRED").
3. That sets `capital_authorization_state` = NOT_AUTHORIZED and `eod_candidate_authorized` = False (~2440).
4. `morning_gate._check_upstream_authority` requires EOD_CANDIDATE_ONLY, so the gate blocks first (~2797).

Among the 862: 282 activated theses (172 lane A), 64 of them with an option that pays at the target.

This contradicts ACK's decisions: Vanguard is context and never decides (Phase 4); legacy classifiers are inactive
(9 Oct). The label records "no current actuarial edge" for a state-hash match, not whether the ticker's thesis or the
option is tradable.

## Design

`morning_gate._check_upstream_authority` keeps the checks that are about this trade and drops the legacy label:

| Check | Kept / changed |
|---|---|
| `authority_source_stage == FINAL_EXECUTION` (provenance) | kept |
| options route OPTIONS_BLOCKED / OPTIONS_EQUITY_ONLY_BETTER | kept |
| governed invalidation missing (`NOT_AUTHORIZED_INVALIDATION_MISSING`) | kept |
| `capital_authorization_state` / `capital_permission` == EOD_CANDIDATE_ONLY, `eod_candidate_authorized` | **removed as a gate**; published as context `legacy_execution_permission_context` = "<capital_permission>:<signal_authority_reason>" and shown beside Vanguard history on the card |
| adopted thesis (`thesis__readiness` not NOT_ADOPTED / NOT_MEASURED / missing) | **added** (R1: no thesis, no authority) |

Unchanged after it: direction integrity, strategy, contract and spread policy, execution viability, lifecycle, the
anticipated value (pays), and GO eligibility (thesis activated + geometry justified, item 3). The EOD and execution
stages keep producing the legacy fields for audit; only their authority at the Morning gate ends.

## Replay (Enhancements/phase7/m_review_01_authority_replay.py / .json)

The real `run_gate` re-run on all 2,788 rows of the 9 Oct Morning, from the Evening rows plus the Morning's captured
live fields (structured fields restored, each row's recorded quote age; network blocked), twice with today's code.

- **Harness check:** the baseline (current rule) reproduces 2,781 of 2,788 recorded verdicts. The 7 differences are
  explained: 6 GO -> FLAG are the M-G2-01 repricing (VLO, JBLU, RIVN, UUUU, ARDX, PLUG no longer pay on their Morning
  quotes after spread and fees) and 1 FLAG -> GO, NVDA: its Evening value said it did not pay (0.98x) and its
  Morning quote says it pays - the same repricing in the other direction. All 7 differences are M-G2-01.
- **Candidate vs baseline:** 30 GO -> 31 GO; 839 BLOCK -> FLAG; 580 stay BLOCK; no GO lost.
- **The 862 legacy-blocked rows:** 1 GO (WYNN: lane A, activated thesis, the option pays), 839 FLAG, 22 BLOCK.
- **Why they are still not GO** (now stated instead of "upstream not authorised"): execution not viable 704 (mostly
  BLOCKED_WIDE_SPREAD: 680 of the 862 had spreads too wide to execute), quote missing 80, waiting for a fresh two-sided
  quote 40, overnight extension 11, target / invalidation order 21, no adopted thesis 2, lane C watch 2, does not pay 1.

**Reading:** on 9 Oct the legacy label mostly coincided with illiquid options, so lifting it adds one GO and changes
839 rows from an unexplained block to a reviewable flag with the real reason. Value: the decision rests on the
thesis and the contract, every non-GO names what failed, and the label can no longer silently remove a liquid,
activated, paying thesis (WYNN).

Caveats: one session; item 3's geometry rule is not applied in this replay (the 9 Oct rows pre-date it) - it can only
remove GOs; the next live Evening + Morning is the forward check.

## Tests (to write before the change)

- A row with capital_permission WATCH_ONLY, an activated thesis, a liquid quote and a paying contract can be GO.
- The same row with `thesis__readiness` NOT_ADOPTED is blocked `NO_ADOPTED_THESIS`.
- Provenance, options-route and missing-invalidation blocks are unchanged.
- `legacy_execution_permission_context` is published and shown on the card; never read by a gate.
- Characterisation: the existing upstream-authority tests are updated deliberately (named in the change).
