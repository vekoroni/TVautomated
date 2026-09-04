# AVS-MVP-001 — Minimum Viable Pipeline for trading resumption (Tue 8 / Wed 9 Sep 2026)

**Issued:** 2026-09-04
**Decision owner:** ACK
**Purpose:** Define the smallest subset of AVSHUNTER that can be trusted to put a real-capital trade in front of the trader by Tuesday 8 September, what is explicitly outside that subset, and what the trader does manually in the meantime.
**Governing principle:** The MVP trades only on rows whose every decision-critical field has been proven honest by a run artefact. Anything not yet proven is *visible but not trusted* — displayed as context, never as permission.

---

## 1. What "MVP" means here

The MVP is not the shippable product defined by AR-003 §12 (twenty gates) or Rev 1.1 §19. It is a **trust boundary drawn inside the existing pipeline**: the set of fields, stages and gates that will have passed a real run by Monday evening, plus a manual filter the trader applies on top.

Three things define the boundary:

1. **In-boundary fields must be honest** — present, lineaged, and fail-closed when missing. Proven by AG-18 (Saturday) and re-proven on Monday's Evening run.
2. **Out-of-boundary evidence is advisory context only** — Vanguard auction state, Market Profile, EV3, macro narrative, monetisability scenario value. It may inform the trader's judgement; it grants nothing.
3. **The edge is the trader's, not the pipeline's.** The pipeline has no measured hit rate (journal dormant since 18 Jul, 14 trades; ledger not yet capturing). MVP trades are discretionary trades on pipeline-surfaced candidates, at probe size, with the ledger recording every one.

---

## 2. Fixes required before Tuesday (cycle 1 of AVS-SD-003, subset)

Must be built, offline-replayed and proven on the Saturday AG-18 run:

| Item | What it guarantees for the MVP | Gate |
|---|---|---|
| W1-1 / W1-2 Vanguard fail-closed unconditional; Layer-2 uplift needs non-null POC | No row is ranked on a fabricated profile | AG-01…AG-04 |
| W1-3 Invalidation precondition at arming | No `ARMED` row without a stop | AG-05, AG-06 |
| W1-4 Null-target guard, both directions, governed reason code | No economics crash; no raw exception text in trader-facing fields | AG-09, AG-10 |
| W1-5 Invalidation precondition on EOD status and capital permission | No `EOD_CANDIDATE_ONLY` without invalidation | AG-07 |
| W1-6 / W1-7 Quote-size, quote-timestamp and `execution_viability_*` reach the Lab | Trader sees the actual quote the gate decided on | AG-11 |
| W1-9 + W1-10 Audit `EMPTY_BY_DESIGN` **with** the semantic rules | The audit fails for real defects and passes correct behaviour | AG-15, AG-16 |
| W1-12 Tests T-02…T-06, T-09, T-12 | Second-level closure | — |

**Explicitly deferred past the MVP** (not required to trade): W1-8 monetisability authority stamp, W1-11 stale-bar state, W1-13 documentation, all of cycle 2 (profile stage, cache identity, legacy-branch deletion, macro content, ledger coverage), and every dynamic-session flag except the ledger.

**Also required before Tuesday:** commit the working tree and tag it; every Evening run from Saturday onward is from a tagged SHA.

---

## 3. Required runs and what each must show

| When | Run | Must show | If it doesn't |
|---|---|---|---|
| **Sat 5 Sep evening** | `--evening`, all flags off (AG-18) | `ALIGNED`=0, `NOT_EVALUATED`=1,551-ish, POC null not `0.0`, `ARMED`-without-stop=0, `EOD_CANDIDATE_ONLY`-without-invalidation=0, no `unsupported operand` text, Lab lineage fields populated or named-absent, RG-01…RG-09 unchanged | Cycle 1 is not done; MVP date slips |
| **Sun 6 Sep** | Offline: Claude Code tester replays AG-01…AG-17 against Saturday's artefacts | All pass; audit `fail_count` = 0 genuine, 0 spurious | Fix and rerun Saturday's step |
| **Mon 7 Sep evening** (US holiday — no new session; run uses Fri 4 Sep completed session) | `--evening`, all flags off **+ `AVSHUNTER_DECISION_LEDGER_ENABLED=1`** | Same as AG-18; ledger captures every candidate incl. rejected | Ledger off → still trade, but journal capture is mandatory |
| **Tue 8 Sep premarket** | `--morning` over Monday's book (first live Morning path since the build) | Morning Gate + Execution Gate produce `final_action` with `execution_viability_state` from a **live** quote; Lab shows it; handoff finaliser passes | **No trades Tuesday.** Inspect, fix, retry Wednesday |
| **Tue 8 Sep, if Morning passes** | Trader applies §4 filter | ≥1 row survives | Wednesday |
| **Wed 9 Sep** | Same cycle | — | — |

The first real-capital trade is **Tuesday only if Tuesday's Morning path is clean on inspection**; the realistic first trade is Wednesday. Tuesday's Morning run is itself an acceptance test — it is the first time the post-build Morning Gate, Execution Gate and Lab handoff will have run on live quotes.

---

## 4. The MVP trade filter — applied by the trader to every row

A row is **eligible** only if **all** of the following hold. Check them in the Lab; if any field is blank or the Lab cannot show it, the row is out.

**Identity and direction**
- `governed_direction_record_sha256` present and matches between Options and Lab (the run's strongest proven positive — RG-03)
- `final_direction` is `CALL` or `PUT`. Never STRANGLE, UNRESOLVED or blank.
- `hold_period` is `1_5d` or `6_10d` (the only lanes the run populates; `11_20d` is empty and unvalidated)

**Geometry**
- `invalidation_price` present and on the correct side of entry (below for CALL, above for PUT)
- `structural_target` present and on the correct side of entry
- Target distance / invalidation distance ≥ 1.5 (your existing R:R eligibility floor, applied to *underlying* geometry, manually)

**Contract and quote (from Tuesday's Morning run, not the Evening book)**
- Exact OCC contract symbol present and identical across quote, economics and Lab
- `execution_viability_state` from Morning Gate = pass/eligible, with `execution_viability_bid`, `_ask`, `_spread_pct` visible and quote timestamp within the session
- Spread ≤ 15% of mid; bid > 0; bid size and ask size visible and ≥ 1
- `final_action` from Execution Gate ∈ {`BUY_NOW`, `BUY_SMALL`}; anything else — including any Lab-displayed GO that Execution Gate did not grant — is out
- DTE ≥ 2 × planned hold in trading days

**Explicitly ignored for eligibility (context only)**
- Vanguard `auction_state`, `ready_to_trade`, Market Profile levels — all `NOT_EVALUATED` in the MVP window by design
- `monetisability_state` and scenario EV/R:R — advisory (AR-003 §7.10); a `NOT_MONETISABLE` row is not blocked by it, a `MONETISABLE` row is not promoted by it
- EV3, GARCH, Wall Break, trigger quality — visible, no authority
- Macro regime and narrative — 19 of 24 macro columns are empty in the Lab; treat the whole family as unavailable
- `win_probability` — a heuristic rank, not a probability

---

## 5. Position rules for the MVP window

- **Probe size only.** Maximum risk per position = the smaller of 0.5% of account or the premium at ask; no scaling until the ledger's first calibration report exists.
- **Maximum 3 open positions** in the first week; maximum 1 new entry per day.
- **Hard exit at `invalidation_price` on the underlying**, close-of-day basis, no exceptions — this is the one field the MVP has proven and it is the whole risk control.
- **Time stop** at the governed hold period; do not extend.
- **Long single-leg only**; no adjustments, no rolls, no spreads.
- **Every entry and exit recorded in the trade journal the same day** with `trade_idea_id`, run ID, contract symbol, fill price, and the §4 checklist result. The ledger records what the pipeline decided; the journal records what you did.

---

## 6. Kill criteria — stop trading immediately if any occurs

- Any Lab row reaches `EXECUTABLE_SUBJECT_TO_GATES` or `BUY_*` with blank `invalidation_price` (AG-08 regression)
- `governed_direction_record_sha256` mismatch on any row (RG-03)
- Any STRANGLE/UNRESOLVED row appears in the Lab book (RG-07)
- Any `unsupported operand`, `Traceback` or `Unhandled exception` string in a trader-facing field (AG-09)
- Morning handoff finaliser fails or reports Lab/Execution permission disagreement
- Audit `fail_count` > 0 for a genuine rule, or a run scores green while §4 finds a defect the audit missed
- Two consecutive positions exit at invalidation with no target ever approached — pause and review, not a pipeline fault but a signal-quality flag

Resume only after the cause is filed, fixed, and a fresh Evening + Morning run shows it clear.

---

## 7. What the MVP is not

- Not evidence of edge. It is a data-integrity milestone. Expectancy is measured by the ledger over the following weeks, and probe sizing exists so that measurement is affordable.
- Not the shippable product. AG-19 (profile stage), AG-20 (warm cache, G19), the four-state live cycle, cycle 2 and the dynamic flags remain on the AVS-SD-003 / Rev 1.1 path unchanged.
- Not a replacement for the trader. Every §4 check is manual by design until the audit layer (W1-10) has been proven to fail on a known-bad run.

---

## 8. Decision log

| Decision | Made by | Date |
|---|---|---|
| Trading resumes Tue 8 / Wed 9 Sep on the MVP boundary defined here, probe size | ACK | 2026-09-04 |
| Vanguard/Market Profile evidence carries no authority in the MVP window | per AVS-SD-003 D1/D2 | 2026-09-04 |
| First trade only after Tuesday's Morning path is inspected clean | ACK to confirm | — |
| Ledger enabled from Monday's run | ACK to confirm | — |
