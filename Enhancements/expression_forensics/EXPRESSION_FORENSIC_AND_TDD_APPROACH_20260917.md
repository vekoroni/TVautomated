# Expression forensic, data-quality inventory and test-driven enhancement approach

Status: **APPROVED by ACK 17 Sep 2026 (D1–D4, backfill option B)** · 17 Sep 2026 · Evidence: outcome scorer as of 2026-09-16 (`c12-expression-v1.1.0`), `expression_loss_diagnostic.py` (read-only), code trace of current `HEAD` (edb63f7 + uncommitted chain-ask entry change).

ACK direction (17 Sep 2026): analyse and clean the data before proceeding; validate where existing logic is broken; use test-driven design with domain design principles; treat the work as **enhancements to the existing pipeline**, not a new build.

---

## 1. Answer first: why did the contracts lose money?

Headline predictions with a marked option (entry at ask, exit at end-of-day bid): **2,937 marked, mean return on premium −45%, median −64%, win rate 16%** (17 evidence sessions; INSUFFICIENT_SESSIONS for a verdict).

Decomposition over the 2,265 marks with entry and exit quotes on both days (fractions of entry premium, means):

| Driver | Contribution | Evidence |
|---|---|---|
| **Bid-ask spread (round trip)** | **−35%** (entry −16%, exit −19%) | Mid-to-mid the same trades return −12% (median −23%) instead of −47%. Entry spread median 21% of ask; 37% of entries had spread ≥ 35%, and those lost −71% on average |
| **No trading in the contract** | concentrated in the worst group | 33% of entries had **zero volume** on the entry session (mean −66% vs −38% for traded contracts); 31% zero volume on the exit session |
| **Direction** | −24% on the 661 marks with a delta | The underlying moved in the thesis direction in only **32%** of marks (median move −1.6%) |
| Theta / vega / gamma / stale quotes (residual) | +6% | small and noisy; greeks are null on 95% of chain rows (`greeks_quality` null 2,789 of 2,937) |

Answers to ACK's question:
- **"No option trades"**: yes, a major cause. One third of chosen contracts did not trade that day, and wide quotes on illiquid contracts account for the largest single loss component.
- **"Contract selection wrong"**: partly. Against every same-side contract quoted on both days, the chosen contract was at the 59th percentile (most stored contracts are far out of the money and lose more), so selection is not worse than random. But it ignores spread and trading activity: a liquid at-the-money, ≥ 30-DTE alternative (|delta| 0.40–0.60, OI ≥ 100, spread ≤ 10%) returned a median **−32% vs −64%** for the chosen contract on the same predictions (only 125 comparable cases, limited by missing greeks).
- **"Direction wrong"**: also a cause, independent of the option. When the entry was liquid (spread ≤ 10% and traded) and the underlying hit target first, options returned **+48% mean / +39% median** (73 cases); on stop-first −60%.

So the option module is broken at two levels: it admits untradeable contracts (execution cost), and it is fed direction and geometry that are no better than chance (outcome report, increment 2).

## 2. Where the existing logic is broken (confirmed in code)

Call chain: `scripts/avshunter_options_intelligence.py` (OI) → `eod_candidate_engine.py` (EOD) → `morning_gate.py` → `contracts/lab_control.py` `write_final_opportunity_book`.

| # | Defect | Location (current code) | Measured effect |
|---|---|---|---|
| E1 | **Spread limit computed but not used in selection**; no open-interest, volume or premium gate; missing spread defaults to 0.15 in the score | OI `select_best_contract` 4562 (`spread_limit` unused), 4612 (`mark > 0` only), score 4663–4706 | spread −35% of premium; zero-volume entries −66% |
| E2 | One-sided / incomplete quotes stay selectable (only crossed or negative quotes removed) | OI 1610–1648, 4585–4607 | exit bid = 0 on 457 of 2,937 marks |
| E3 | **Missing ask becomes 0.0** in the candidate book (bid becomes NaN) | EOD 2618 (`_flt` default 0.0, 353–360) | 9,171 of 21,481 book rows with ask 0 |
| E4 | Book copies contract prices from generic fields; after a direction reselection the **symbol and bid/ask can describe different contracts** | `lab_control.py` 2891–2897 with `_contract_for_direction` 892–917 | not yet measured (needs DQ-3) |
| E5 | **Wrong-side contract kept** with a flag only (`CONTRACT_SYMBOL_SIDE_CONFLICT`), not blocked | `lab_control.py` 914–916; EOD clears only some contract fields 1434–1443 | 1,361 side-mismatch rows |
| E6 | **3R target has no floor or side check**: PUT `entry − 3 × stop_dist` goes negative when the stop is > 33% above entry; target measured against `entry_price`, book compares with `underlying_price` | OI 4247–4270, 4026; `lab_control.py` 2877 | 7,728 zero / negative / wrong-side targets |
| E7 | Invalidation can fall back to an unchecked legacy `stop_loss` | `lab_control.py` 2860–2867 | 1,830 missing invalidations (not yet split by cause) |
| E8 | **Five exit implementations, none applied to outcomes**; the option-premium exit engine is CLI-only; the lifecycle tracker is git-ignored but executed | OI 899; EOD 1566; `scripts/exit_rules_engine.py`; `avshunter_exit_engine.py`; `position_lifecycle_tracker.py` (`.gitignore:138`) | no measured exit policy exists |
| E9 | "Cheap convexity" is output only, never a selection input; no option-vs-shares comparison anywhere | OI 956, 841 | business objective "is the money in the option or the ticker" unanswered by the pipeline |

Not confirmed yet: canonical store quote normalisation; whether the 1,361 side mismatches come from OI direction ≠ final direction; code between 4 and 20 Aug (no history).

## 3. Data-quality inventory (clean before proceeding)

Principle: **cleaning never deletes or rewrites recorded evidence.** Each rule is a named, tested data contract; failing records are labelled (quarantined for a given use) with the rule id, and every report states how many records each rule removed.

| Rule | Dataset | Finding | Proposed treatment |
|---|---|---|---|
| DQ-1 | Opportunity books | ask ≤ 0 with a contract symbol: 9,171 sightings | `ENTRY_NOT_VALUED` unless evidence-session chain ask exists (ACK 17 Sep: use it; 222 marks now valued) |
| DQ-2 | Books | contract side ≠ direction: 1,361 | expression `CONTRACT_INVALID`; underlying still scored |
| DQ-3 | Books | contract prices not belonging to the symbol (E4) | new check: book ask vs chain ask for the book symbol on the evidence session (today 70% within 5%; median ratio 1.00) — tolerance to be set in configuration |
| DQ-4 | Books | target zero / negative / wrong side: 7,728; invalidation missing: 1,830 | already classified (`INVALID_LEGACY`, `NOT_SCORABLE`) |
| DQ-5 | Books | `thesis_state` TARGET_REALIZED / INVALIDATED are not predictions (resolve on session 1) | exclude from skill groups |
| DQ-6 | Chain store | backfill parameters store expiries 7–60 calendar days out, 40 strikes, OI ≥ 1 (`run_phantom_backfill_parallel.py` 145–153) → exits in a contract's last week and OI-0 contracts are never stored | measured: of 461 September exit gaps, 187 ticker absent, 153 expiry outside window, 121 strike absent (OI filter) |
| DQ-7 | Chain store | exit bid = 0: 457 marks; greeks null on 95% of marked rows | report separately; bid 0 with ask > 0 is "no bid", not a price |
| DQ-8 | Chain store | daily panel only from 28 Aug; weekly Fridays before | backfill decision §4 |
| DQ-9 | Actuarial v7 | 20-day returns up to 46.9M; 309 rows > 1,000% | untouched in the 17 Sep refresh; C4 treatment decision |
| DQ-10 | Price store | 11 predictions without ATR history | `NO_ATR` |

## 4. Backfill sizing (MarketData credits; nothing run)

Missing exit quotes (`MARK_UNAVAILABLE`, v1.1): **2,285 marks = 1,897 (ticker, session) pairs across 1,129 tickers**; 1,826 in 23 Jul – 27 Aug, 461 on or after 31 Aug. Separately, 670 marks lack an evidence-session chain row for entry diagnostics.

| Option | Scope | Credits (≈ 1 per request) | Recovers | Caveat |
|---|---|---|---|---|
| **A. Full-panel daily backfill** with the existing tool | 21 sessions (23, 27–30 Jul; 3–6, 10–13, 17–20, 24–27 Aug) × ~3,060–3,320 tickers | **≈ 64,000–70,000** (one day at the 100,000 allowance, or three days at ≤ 30,000) | est. ~80% of the Jul–Aug gaps (September analogue); none of DQ-6 gaps | also gives daily history for C7 IV work |
| **B. Targeted contract quotes** (new measurement tool) | one request per (ticker, session, expiry) needed by the scorer, `from = to = expiry`, `minOpenInterest = 0`, no strike limit; stored in a separate outcome-quote table, not mixed into `chain_snapshots` | **≈ 2,000–2,700** (1,897 exit pairs + up to ~700 entry pairs) | nearly all, including last-week and OI-0 contracts | new code (small; needs this design approved) |

Recommendation: **B now** (cheap, complete for scoring), A only if C7 needs daily IV history before 28 Aug.

## 5. Approach: test-driven enhancement of the existing pipeline

ACK direction changes the migration stance: fix the **existing** modules in place, test-first, instead of rebuilding contexts beside them. This needs `CLAUDE.md` rule 4 ("legacy is an asset mine, not a design reference; strangler migration") amended; see decision D1.

Cycle per defect (one work package at a time):

1. **Characterise** — pin current behaviour with a characterisation test on recorded inputs (a real evening row set replayed through the function). No behaviour change; proves the test harness reaches the code.
2. **State the business rule as a failing test** in domain language, derived from the spec and ACK decisions (e.g. *"a contract without a positive ask or with spread above the horizon limit is not a tradeable expression"*; *"a PUT target is positive and below the reference price, or absent"*; *"book bid/ask belong to the book contract symbol"*; *"a contract on the wrong side never reaches the book; the share expression remains"*).
3. **Minimal change** in the owning module to pass; thresholds in the configuration registry (no literals); one owner per fact (R2).
4. **Acceptance against reality** — the outcome scorer is the acceptance test (R10): re-run on the same history and on forward sessions; the work package is accepted only if the targeted metric moves (e.g. spread cost share, zero-volume share, `INVALID_LEGACY` count) without degrading others. Legacy decisions keep no new authority until G1–G4.
5. Record in the decision map: defect id → test ids → commit → scorer delta.

Domain boundaries used for the tests (spec contexts, applied to existing code): Thesis geometry (targets / invalidation: E6, E7), Expression selection (E1, E2, E5, E9), Quote integrity (E3, E4), Exit policy (E8), Outcome measurement (C12, done).

### Proposed work packages, ordered by measured money impact

| WP | Defects | First failing tests | Acceptance metric |
|---|---|---|---|
| WP1 Expression tradeability | E1, E2 | spread > limit excluded; ask ≤ 0 / one-sided excluded; zero volume and OI below minimum excluded (thresholds PROVISIONAL in registry) | round-trip spread share of premium and zero-volume share fall; mean return on premium vs liquid alternative |
| WP2 Quote integrity in books | E3, E4 | missing ask stays missing (never 0.0); bid/ask/delta read from the contract that is written | DQ-1 and DQ-3 counts → 0 on new books |
| WP3 Direction-contract coherence | E5 | side conflict removes the option expression (share expression kept, S2 pattern) | DQ-2 count → 0 on new books |
| WP4 Target and invalidation geometry | E6, E7 | no non-positive or wrong-side targets; one reference price for target and book | `INVALID_LEGACY` → 0 on new books; target-first incidence vs base rate |
| WP5 Exit policy | E8 | one exit policy, measured by the scorer, replacing display-only variants | option return by exit policy vs hold-to-resolution |
| WP6 Option vs shares | E9 | every thesis records share and option expression outcomes | report answers "money in option or ticker" per thesis |
| Direction quality | signal-accuracy root causes (15 Sep audit) | separate track; biggest driver of underlying outcomes | target-first excess over base rate |

## 6. Decisions for ACK

- **D1** Amend `CLAUDE.md` rule 4 and spec authority wording: *enhance existing modules test-first; the rebuild package keeps measurement (C12), configuration and run context; new contexts only where no legacy owner exists.*
- **D2** Approve the data-quality rules DQ-1 … DQ-10 as labelled quarantine rules (no deletion).
- **D3** Backfill option **B** (≈ 2,000–2,700 credits, new targeted quote tool) — or A (≈ 64,000–70,000).
- **D4** Start with **WP1** (largest measured loss), then WP2 → WP3 → WP4.

## 7. ACK decisions (17 Sep 2026)

- D1 approved: `CLAUDE.md` rule 4 amended (enhance existing modules test-first) and working rules for test-driven change and reality-calibrated logic added.
- D2 approved: DQ-1 … DQ-10 as labelled quarantine rules.
- D3 approved: backfill option **B** (targeted contract quotes, ≈ 2,000–2,700 credits).
- D4 approved: start **WP1**. ACK direction: build intelligent, reality-calibrated logic (historic chains, implied vs realised volatility, forward probabilities) rather than textbook option rules; benchmark is a human option trader without a pipeline.
