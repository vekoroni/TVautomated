# Final Macro Operating Cycle research/governance build — 26 November 2026

> Release approval: the historical 155-pass result below belongs to the live working checkout, not this clean published-base branch. Initial clean tests exposed a missing shared-valuer interface. ACK approved a macro-only adapter; this isolated branch passes all 42 governance/adapter tests and saved E2E replay. ACK subsequently approved the exact 14-file macro-only commit, annotated tag and branch/tag-only push. No shared valuer/ticker/Lane B/data changes, main merge or schedule enablement are authorized. See `FINAL_RELEASE_SCOPE_20261126.md` for exact scope, actual output, portable commands, MACRO-COMPAT-01 follow-up and separate live shared-file inventory. Do not treat historical live-checkout passes as clean-release acceptance.

## Outcome and scope

Implemented the approved final contract and safeguards on the existing operating-cycle/board/Lab path. This is NOT a new trading engine or another house view. Macro stays ADVISORY_ONLY. No Lane B, ticker scoring/ranking/veto, Discovery, Vanguard, Options Intelligence, contract selection, order placement, scheduler, FULL-mode or budget changes.

Revision 1 is retained as RESEARCH_DRAFT, not approved, installed as a live input, or quietly repaired into a new forecast. The original pasted bytes and presentation-normalised JSON are immutable saved evidence. The replay envelope exposes the draft house thesis as unapproved and withholds incoherent event probabilities/world marks from machine-scored calls. It does not invent replacement probabilities, thresholds, priced policy odds or option contracts.

## Implemented contracts

- `macro_research_input_v2`: separate authored/evidence/approval clocks; exact-content ACK approval hash; distinct event forecasts, ordered market scenarios and ETF expression IDs. Author text is not approval. Legacy inputs remain readable but never acquire approval implicitly. A content hash is an operator-controlled approval receipt, not a cryptographic identity signature.
- Nine narrative sections retained. JSON remains the record; Markdown, board and Lab expose approval, evidence completeness, valuation readiness and separate clocks. Publication integrity is independent of economic completeness. COMPLETE_WITH_EVIDENCE_LIMITATIONS never means a trade recommendation or validated option profit.
- Event resolution requires a named series, unit, source, threshold, window, vintage and sampling rule. Direct source-hashed numeric observations are checked against archived JSON rows at intake. Late/unavailable/revised/incomplete/conflicting observations cannot silently become losses. First-published releases are distinct from as-read revisions. ANY_CROSSING needs an explicitly complete observation grid before a negative result; a valid positive crossing can resolve without the whole grid.
- VIX/Treasury alerts cannot resolve HY/Oil calls by proxy. Credit change rules carry pinned baselines; exact decimal comparison makes 3.72% + 75bp equal 4.47% at a GE boundary. Oil requires benchmark, contract, settlement and roll rule on both rule and evidence. No unapproved publication lag is guessed for saved HY history; absent lag policy is UNASSESSED_PUBLICATION_POLICY. A separately archived, timestamped direct spread observation can still resolve a correctly typed call.
- Declared IMPLIES and COMPLEMENT probability constraints are checked over a common horizon. No prose understanding or universal probability-consistency certification is claimed. The draft's 60% cool-CPI / 40% hot-CPI versus 20% containing-OR contradiction is tested and rejected, not renormalised.
- Market scenarios use common closing horizon, explicit baseline session/ETF/benchmark, absolute or relative return metrics, measurable boundaries, ordered first-match precedence and final residual. Exact saved closes only; no forward filling, missing-as-residual, or invented partition. Without authored definitions/probabilities the partition remains NOT_ASSERTED.
- Each ETF expression has one governed ETF, absolute/relative basis, benchmark where required, deadline, invalidation, killer event and covering-expression ID (or null). KRE is included in the governed macro ETF registry; this grants no ticker authority.
- ETF world marks are labelled AUTHORED_ETF_THESIS_ONLY_NOT_OPTION_PNL. Exact OCC identity, quote bytes/hash/clock, XNYS expiry close, bid/ask, scenario date/spot/IV/rate/dividend bases and spread stress are needed for conditional option valuation. Reuses `domain.option_valuation` American CRR and common fees/cost formula. No exact saved evidence => OPTION_PAYOFF_UNASSESSED. Per-world option valuations and authored delay/IV/spread stress comparisons are separate; absent worlds remain unassessed. Conditional model WIN is not a realised exit or guaranteed executable bid. No selector was built.
- Saved forward forecasts survive unrelated governance-policy upgrades under their ORIGINAL immutable policy/clock. Changed horizon/direction/evaluation still stops on identity conflict. Existing call journals are not rewritten or duplicated.

## Saved acceptance evidence

Evidence root: `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a`.

- `MACRO_FINAL_GOVERNANCE_REPLAY_20261126.py`: network-blocked replay from existing 25 November close captures, not a market refresh or paid build.
- Output: `MACRO_FINAL_GOVERNANCE_REPLAY_20261126\cycle\latest.json` and `publication\macro_publication_latest.json`.
- Final publication: `7e610f6316be3386237372e3199b70a59a8a12fe875b3cf3ee9608be1699079e`.
- Narrative: `macro_2026-11-25_5a415bf521499c4fb981366f`, RESEARCH_DRAFT.
- Original pasted draft SHA-256: `edb788822b9837c2372806c62c239a41d7a87f507df188bb7f300e48f99e2364`.
- ETF board and Lab test-client HTTP 200; identical narrative hash; all three accepted USMI/News/Events feeds verified; 115 ETF rows and all original market payload fields unchanged. Historical narrative bytes unchanged. Live latest publication was NOT replaced by this test.
- New governance tests cover overlapping events, residual world, contradictory probabilities, credit boundary, incorrect source/unit/stale/late/vintage, missing paths, oil identity, relative correctness without put profit, delayed IV-crush loss, option quote/identity gaps, exact-content approval and policy-upgrade compatibility.
- Full final test accounting: 155 Python PASS and two JavaScript harnesses PASS. Receipt: `audit/fix_receipts/MACRO_FINAL_GOVERNANCE_20261126.json`. One initial Lab test attempt hit sandbox read denial on the existing Worker 3 policy; the unchanged test was rerun with read access and all 11 passed. No Worker 3 repair was made.

## Claude/ACK receiving checklist

1. Independently run the validator and saved replay; check both consumer hashes and source captures. Do not approve the research view merely because structure/tests pass.
2. Supply the next authored draft using the v2 schema and Python semantic validator. Do NOT install revision 1's overlapping alternatives as an exhaustive world partition.
3. Author fresh market-world boundaries, shared deadline, precedence/residual and probabilities. Supply structured event relationships, exact release/outcome clocks and first-publication policies. The code does not author these judgements.
4. Pin direct HY and exact oil evidence/units; approve any required publication-lag policy separately. External news and policy-pricing claims from the pasted review were not independently verified here and are not measured facts.
5. Separate SMH and QQQ; provide absolute move/deadline/invalidation and any real covering expression. For option assessments provide archived JSON quote rows plus explicit base/per-world/stress assumptions; no option selection was delegated to this module.
6. After review, ACK can approve the exact content hash. A changed authored forecast still requires new call IDs/correction lineage; historical calls and outcomes remain immutable.
7. Operational live-run evidence remains AWAITING_RUN. All three MacroInputs tasks remain Disabled. No providers, paid builds, pipeline run, live DB writes, or live research-input activation took place.

## Ready-to-paste offline verification

`Set-Location "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"; & "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\venv\Scripts\python.exe" -B -m pytest "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\tests\test_macro_cycle_governance.py" -q -p no:cacheprovider --basetemp="C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\macro_claude_governance_verify"`

`Set-Location "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"; & "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\venv\Scripts\python.exe" -B "C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\MACRO_FINAL_GOVERNANCE_REPLAY_20261126.py"`

The replay writes NEW dated evidence versions only, never starts the board producer/pipeline and never replaces the live publication. A rerun naturally has a new assembly clock/narrative ID.
