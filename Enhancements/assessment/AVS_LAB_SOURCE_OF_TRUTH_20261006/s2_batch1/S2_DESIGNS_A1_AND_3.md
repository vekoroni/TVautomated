# S2 designs for ACK sign-off: A1 (keep an aged share price) and #3 (strikes against the valued level)

Both change Morning or contract outcomes, so they come to ACK before any code. Evidence: S1 (`s1/S1_QUOTE_AGE_INVENTORY.md` §A1; `s1/S1_SETUP_LINEAGE_AND_OPEN_CHECKS.md` §1).

---

## A1: a valid share price is never thrown away for being old

**Root cause.**
- `morning_gate.py:119` sets `LIVE_STOCK_PRICE_MAX_AGE_SECONDS = 300` as a literal.
- At :831–832, a valid underlying SmartMid older than 5 minutes is **rejected** (`STALE_PROVIDER_PRICE`) and the live price is set to None. The lifecycle then sees "no spot" and gives `CONTRACT_REPRICE_REQUIRED` → FLAG/NO_TRADE, or FLAG WAIT "LIVE_PRICE_UNAVAILABLE".
- **Run 20261006:** 17 rows affected (lane A: 2 BLOCK, 4 FLAG). None could be GO.
- This breaks the standing ACK rule: quote age is disclosed, never a gate. It also breaks R6, because the price is labelled "unavailable" when it was only old.

**Design.**
1. Keep the price. Publish `live_price_age_seconds` and `live_price_source_time_utc`, plus `live_price_state` = `CURRENT` or `AGED_REFERENCE` (disclosure only).
2. The lifecycle (invalidation broken, move already realised, runway, pullback) uses that price.
3. The rejections that stay are **invalid** inputs, not old ones: missing provider timestamp, future-dated timestamp, non-positive or crossed quote.
4. The 300-second literal is removed. No age threshold remains anywhere.
5. The card's "Can I trust the data" row shows the price age, e.g. "share price 7 min old".

**Business risk to accept.** An old price can miss a break of invalidation that happened in the last few minutes. That is the trade-off ACK chose with "flag quote age, never gate on it". The age is shown beside the price, so the human sees it before acting.

**Test first:**
- a valid price 20 minutes old is used, labelled AGED_REFERENCE, and does not produce CONTRACT_REPRICE_REQUIRED;
- a future-dated or missing timestamp is still rejected;
- a characterisation test of today's 300-second rejection comes first.

**Acceptance:** a replay of the 17 rows from run 20261006 (the Morning quotes are in the frozen run) shows each row's new verdict and its reason.

---

## #3: choose strikes against the level the value is computed at

**Root cause.**
- OI's target-reachability filter (`scripts/avshunter_options_intelligence.py:5596–5617`) keeps only strikes on the intrinsic side of `structural_target` (falling back to `target_reachable`).
- That field is the **prior 40-bar range extreme** (`wyckoff_phase_validator.py:137–144`, relabelled DISCOVERY_TARGET).
- The anticipated move then **values** the contract at `anticipated_level_q50`, which comes from the governing setup's outcome level after S2-1.
- On 35 of 51 GOs the two levels differ by more than 1%. Example: HPQ, range extreme 36.23 vs anticipated level 38.49.
- So the contract is chosen for one target and judged against another.

**Design.**
1. **One level for selection and for valuation.** OI computes the anticipated level before contract selection, using the existing domain function: `domain/anticipated_move` `level_by` / `reach_by` on the governing setup's `thesis_outcome_level`, duration evidence and `target_reachable_vol_annual`. The strike filter uses that level. Today the EOD stage computes the anticipated move *after* OI; the same function would be called earlier, so there is one owner and two call sites that share inputs.
2. **No substitution.** If there is no anticipated level, no reachability filter is applied, and this is recorded as `strike_filter_basis = NO_ANTICIPATED_LEVEL`. It never falls back to the range extreme.
3. **Rename the range extreme** to `prior_range_extreme` (role SUPPORTING; glossary §1.2). It is shown on the card as "first objective (40-bar range)". It no longer selects strikes, and it no longer drives monetisability (link 5, same change or the next).
4. **Unchanged:** delta zone, DTE runway floor and spread policy. Strikes are only filtered against a different level.

**Expected effect (to be measured).** Where the anticipated level lies beyond the range extreme (the common case: HPQ 38.5 vs 36.2), more out-of-the-money strikes become eligible. Those are cheaper, with a value computed at the same level. Where it lies nearer, the filter tightens.

**Test first.** "the strike filter uses the level the contract is valued at"; "a missing anticipated level applies no filter and says so"; plus a characterisation test of today's filter.

**Acceptance.**
- A contract-selection replay on the frozen run, using the stored completed-session chains (MarketData canonical store; no provider calls).
- Report how many GOs change contract.
- For each change, report the anticipated value multiple before and after, and the spread and DTE.

---

## Decisions for ACK
1. **A1:** approve keeping and disclosing aged share prices, with no age threshold, and accept the risk above.
2. **#3:** approve one level for strike selection and valuation, no fallback to the range extreme, and the rename to `prior_range_extreme` (supporting).
