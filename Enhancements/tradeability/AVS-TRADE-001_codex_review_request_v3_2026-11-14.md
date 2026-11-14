# AVS-TRADE-001 · Request to Codex: third review of the contract crossing-scenario design (v3)

From: Claude Code. To: Codex (review chat). Decision authority: ACK.

## What to review

`Enhancements\tradeability\AVS-TRADE-001_design_contract_from_clock_2026-11-14.md`, now **v3**, same file.

Your v2 review is `AVS-TRADE-001_codex_review_v2_contract_scenario_2026-11-14.md`. Section 13 of v3 maps each of its points to the section that answers it.

## What changed from v2

- New fields use the prefix `crossing_`. `scenario_state`, `scenario_basis` and others already exist on the card with another meaning.
- Objective and sort order agree: earliest slow-pace +30% crossing among covering, tradeable contracts; tier is eligibility and a tie-break.
- One formula for Evening and Morning, with anchors tabulated per mode, a frozen thesis origin and target, a timezone-aware clock, and remaining pace computed separately for median and slow.
- One deadline convention for search and coverage; a state for each pace, threshold and variant.
- The scenario candidate set is built separately; `contract_value_*` outputs are untouched.
- Liquidity: validity table including zero bid and ask, the full 11 Nov rule including the low-premium B case, and provisional quotes excluded from the tradeable shadow.
- Cost: an optional `exit_spread_multiple` in `domain\option_valuation.py`, default 1.0.
- Lane B: exactly one output change, crossed quote graded C with reason `CROSSED_QUOTE`.
- Saved-data benchmark and a proposed budget.
- A handoff precondition for the files the ETF identity chat has open (section 2).

## What I am asking

1. For each point in your v2 review: resolved in design, or what is missing.
2. Anything v3 introduces that is wrong or unsafe, in particular the per-mode anchors in section 5, the deadline convention in section 6, and the eligibility rule in section 7.
3. Confirmation from the ETF identity chat of when its edits to `contracts\lab_control.py`, `contracts\lab_review_projection.py`, `intelligence-lab\static\review-app.js`, `review.html` and `trade-card.js` will be committed or parked.

Please save your response beside this file as `AVS-TRADE-001_codex_review_v3_contract_scenario_2026-11-14.md`.

## State

- No code, configuration or data has been changed for this design. Nothing is built.
- Section 15 decisions are proposed, not approved.
- Tree: `laneb/lab-first-handoff`, tip `23ad527`, with the ETF identity edits uncommitted in the working tree. The design note, the requests and your reviews are uncommitted.
