# AVS-RCA-003 — Decisions for ACK

Design questions surfaced by the investigation that are **not defects**. Each has evidence for both options; none has a single correct answer that the code can be said to have got wrong.

---

## DEC-1 — Should monetisability use a time-value model?

**The question.** `contracts/selected_contract_economics.py:574-583` values the option at the target using **expiry intrinsic** (`max(target − strike, 0) − entry_ask`). Should it instead retain time value remaining at the target?

**Evidence for changing it.** Black–Scholes ≥ intrinsic always, so the current model is a strict lower bound and can only produce **false negatives** — never a false positive. Measured on run `20260905_151448` (S1): **10 of 35** sub-monetisable rows flip to MONETISABLE, 8 more to LIMITED, and **0** MONETISABLE rows fail. `PNW` CALL misses breakeven by 3 cents (−3.53% intrinsic) and is +84.5% with 8 DTE of time value retained. AR-003 §7.10 flagged exactly this.

**Evidence for keeping it.** Intrinsic is model-free. A Black–Scholes number depends on a constant-IV assumption that will not hold to the target, and it would import a pricing model into a field the design deliberately keeps advisory. A conservative floor that never over-promises is defensible for a field whose purpose is to warn.

**A third option, which I would recommend.** Keep the intrinsic floor as the published `monetisability_state`, and add a **second advisory field** — `monetisability_state_timevalue` — alongside it, with the model and its assumptions named in the row. The operator then sees both bounds and the disagreement is visible rather than silent. Cost: one column, no authority change.

---

## DEC-2 — Should the contract-selection bands be widened?

**The question.** `DTE_CONFIG` (`scripts/avshunter_options_intelligence.py:1214-1218`) sets `1_5d` at δ 0.40–0.60 and 7–21 DTE. Should those windows be wider?

**Evidence for widening.** The median blocked ticker has **exactly one** contract inside the delta band, and 305 of 774 have **none** (S2). Selection is not choosing badly — it is being handed a single candidate. Widening δ by ±0.10 and DTE by ±7 days recovers **121 additional candidates per run** with the 25% spread gate **unchanged** (S2b), i.e. without accepting any trade the current liquidity policy rejects. On a 294-row book that is a 41% increase.

**Evidence against.** The bands encode a strategy view: δ 0.40–0.60 is a deliberate "close to the money, meaningful delta, not a lottery ticket" choice, and 7–21 DTE is matched to a 1–5 session hold with theta headroom. Widening δ to 0.30 admits cheaper, lower-probability options; widening DTE to 28 admits more theta exposure than the hold justifies. The recovered candidates are *available*, not necessarily *good* — S2b measures a contract clearing the spread gate, not one that would pass economics or the profit floor.

**What would settle it.** Run the widened bands in shadow for one Evening cycle and compare how many of the 121 recovered candidates clear economics and the monetisability floor. That is a cheap offline replay against the stored chains and needs no live run.

---

## DEC-3 — Which spread rule is the authority?

**The question.** `DTE_CONFIG` defines per-horizon `spread_max` of 15% / 25% / 35%; the terminal gate applies a flat `MAX_SPREAD_PCT = 25%` to every horizon (`:6018-6035`). Two rules, one quantity.

**Evidence.** They disagree in both directions. For `1_5d` the flat gate is **looser** than the horizon's own 15% band — 3 rows cleared the terminal gate that the band would have blocked. For a hypothetical `11_20d` candidate the flat gate would be **tighter** than the band's 35% (no `11_20d` rows exist in this run, so it does not currently bite).

**Options.** (a) Make the per-horizon band authoritative — a short hold demands a tighter spread, which is economically coherent. (b) Make the flat gate authoritative and delete `spread_max` from `DTE_CONFIG` — one number, simpler to reason about. (c) Keep both explicitly as `min(band, flat)`, documented as belt-and-braces.

I would take (a): a 5-session hold cannot absorb a 25% round trip, so the tighter band is the honest constraint. But this is a policy call, not a correctness one.

---

## DEC-4 — Should Discovery pre-filter on options liquidity?

**The question.** Discovery selects on equity-thesis quality with **no knowledge of the options chain**. Roughly half its output has no viable long single-leg expression (S2: 731 of 774 blocked tickers have zero contracts clearing the spread gate in-band).

**Evidence for a pre-filter.** The pipeline spends a full option-chain fetch on every one of ~1,460 tickers to discover something an underlying-level screen (ADV, chain open interest, typical ATM spread) could predict cheaply. It would raise book density and cut provider cost.

**Evidence against.** It couples Discovery to options data it is deliberately independent of, and the design is explicit that Discovery is *thesis-valid*, not *trade-valid*. A liquidity pre-filter would also silently bias the universe toward large caps and could hide a genuine thesis the operator would want to see even if untradeable today.

**Note the data does not support the obvious version of this filter:** the blocked names are not penny stocks — median underlying \$50.94, only 2.6% under \$10. A simple price screen would not work; it would have to be a chain-liquidity screen.

---

## DEC-5 — Where should the Anthropic credential live?

**The question.** Worker 3's transport reads `os.environ` only and deliberately never loads `.env` (`anthropic_http.py:41`, and both module docstrings say so). The repository `.env` also carries an `ANTHROPIC_API_KEY`. Two sources, different values, no documented precedence — the Part 1 root cause.

**Options.** (a) Environment only: matches the transport, keeps the credential out of the repo tree entirely. (b) `.env` only, with the transport changed to load it: single file, but contradicts the transport's explicit isolation property and puts a secret next to the code. (c) Both, with documented precedence: keeps the failure mode alive.

I recommend (a) and have written it into the Part 1 fix. The decision for ACK is whether any *production* component (as opposed to Worker 3) needs `ANTHROPIC_API_KEY` from `.env` — if none does, the line should simply be deleted after rotation.
