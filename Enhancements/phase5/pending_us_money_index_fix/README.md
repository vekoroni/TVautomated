# Pending: US Money Index text-flag fix (prepared 8 Oct 2026; apply after the Evening finishes)

**Root cause.** The LLM producer drifted: since 7 Oct `current_state.risk_off_transition` is text
("CONFIRMED_WITH_…; NO_BROAD_SYSTEMIC_UPGRADE") instead of a boolean. The contract
(`contracts/us_money_index_contract.py`, `_validate_v2`) correctly refused the whole packet, and the Evening ran
without the money index (verification report G2-03; log "US Money Index rejected").

**Fix (ACK: "prepare both, apply after the evening finishes").**
1. Contract reads the flags through an explicit vocabulary and keeps the text as `<field>_detail` and
   `<field>_basis` (`apply_contract_change.py`). Unknown text is still refused, naming the field.
2. Producer-side check: `scripts/validate_us_money_index.py`, plus the prompt wording in `PRODUCER_PROMPT_ADDITION.md`.

**Proof, 8 Oct 2026, in an isolated scratch copy (production contract untouched while the Evening runs):**
- Before the change: 4 failed for the real reasons ("current_state.risk_off_transition must be boolean", no
  `_basis` field, the validator refused today's packet); 4 passed (unknown text refused).
- After `apply_contract_change.py`: 8 passed. The validator on today's packet printed ACCEPTED, with
  `risk_off_transition=True (PARSED_FROM_PRODUCER_TEXT)`, the two other flags BOOLEAN and a quality note.

**Apply steps (test-first), after the Evening finishes and no pipeline is running:**
1. Copy `fixtures/us_money_index_v2_text_flags_20261008.json` to `tests/fixtures/`.
2. Copy `test_us_money_index_text_flags.py` to `tests/` and run it: it must fail first (shown below).
3. Copy `validate_us_money_index.py` to `scripts/`.
4. Run `apply_contract_change.py`; re-run the new test, `tests/test_avs_d03_sector_routing.py`,
   `tests/test_macro_domain_enhancements.py` and the consumers that read `state.risk_off_transition` as a boolean:
   `tests/test_worker3_avshunter_source_bridge.py`, `tests/test_worker3_macro_ticker_context.py`,
   `tests/test_worker3_market_environment.py`.
5. Run `scripts/validate_us_money_index.py` against today's packet: it should print ACCEPTED with
   `risk_off_transition=True (PARSED_FROM_PRODUCER_TEXT)`.
