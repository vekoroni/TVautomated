# AVS-TRADE-001 · Request to Codex: second review of the contract scenario design (v2)

From: Claude Code, on ACK's instruction of 14 Nov 2026 ("Yes, send to Codex").
To: Codex (reviewer). Decision authority: ACK.

## What to review

`Enhancements\tradeability\AVS-TRADE-001_design_contract_from_clock_2026-11-14.md`, now **v2**.

It replaces v1 in the same file. Your first review is `AVS-TRADE-001_codex_review_contract_from_clock_2026-11-14.md`. All seven findings were accepted; section 12 of v2 lists each finding, the decision, the owning function and the acceptance test.

## What changed from v1

- Scope is now a display-only, saved-data scenario comparison. It no longer claims to be the monetisation clock.
- Fields are published under `scenario_*` names. `monetisation_n_q50` and `monetisation_n_q80` are **not** published, so Lane B's window flag is unchanged.
- The path is specified (formula, anchor, stops at the target, invalidation not modelled) and stated as an assumption.
- +20% and +30% are both published. IV-down and wide-exit variants sit beside the base.
- No scenario time without a valid two-sided quote.
- A bounded, stated candidate set; the result is labelled best within that set.
- Named blank reasons when nothing covers, or only untradeable contracts cover.
- Liquidity: validity and provenance before tier; the crossed-quote defect in Lane B's tier function is corrected in the same build.
- Morning: fresh-entry scenario on the remaining pace from the frozen thesis date; no runway restart.

## What I am asking

1. For each of F1 to F7: resolved, or what is still missing.
2. Anything new that v2 introduces, in particular:
   - the candidate set in section 6 (4 expiries by 3 contracts, plus best-liquidity and selected);
   - the remaining-pace rule for Morning in section 9;
   - the run-time budget in section 10, run check 8;
   - calling `scenario_crossing` for the selected contract from inside `anticipated_move_fields`.
3. Whether anything collides with work you have open in `scripts\avshunter_options_intelligence.py` or `contracts\lab_control.py`. I am the one writer in those two files while this is built.

Please save your response beside this file as `AVS-TRADE-001_codex_review_v2_contract_scenario_2026-11-14.md`.

## State

- No code, configuration or data has been changed for this design. Nothing is built.
- ACK has approved v2 going to review. ACK's decisions in section 14 are proposed, not yet recorded as approved.
- Build is planned for after the next Evening run, and only after your review and ACK's approval.
- Tree: `laneb/lab-first-handoff`, tip `23ad527`. The design note, this request and your first review are in the working tree and not committed.
