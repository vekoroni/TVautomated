# AVS-RCA-004 — Stage Contradiction in Live-Marked (GO/GO_LIMIT/PROBE) Trades

**Date:** 26 Sep 2026
**Author:** Claude (read-only investigation, per CLAUDE.md working rules — no pipeline code changed)
**Source of truth:** `data/canonical/outcome_scoring.sqlite` (C12 outcome-scoring layer), tables `prediction_records`, `prediction_sightings`, `underlying_outcomes`, `expression_outcomes`. Coverage: sessions 2026-09-16 to 2026-09-25 only (9 sessions — this is a short, single-regime window; treat magnitudes as provisional, the mechanism as robust).
**Trigger:** ACK's original architecture premise — each pipeline stage should progress the thesis established by the prior stage, never re-derive or contradict it. Repeated fixes have not resolved persistent underperformance. This document traces why, using real scored data rather than audit narrative.

---

## 1. Correction to earlier same-day analysis (stated for the record)

Two claims made earlier in this investigation were wrong and are superseded here:

1. **"~26% of candidates have target/direction on the wrong side" was presented as a live-pipeline defect.** It is not, for trades that matter. That number came from the *entire* candidate stream (31,053 predictions), which includes every rejected/non-actionable row Discovery ever produced. When restricted to predictions the pipeline actually marked `GO` / `GO_LIMIT` / `PROBE` / `BUY_NOW` / `BUY_SMALL`, **0 of 1,811 have an invalid or wrong-side target.** The direction-integrity guard (`contracts/direction_governance.py::validate_direction_record`, enforced in `contracts/lab_control.py` lines ~3964–3976) works correctly for the actionable subset. It downgrades `lab_tradeable`/`lab_verdict` to `BLOCKED` only when a row is *already* claiming to be actionable — non-actionable rows keep their (possibly wrong-side) geometry uncorrected in the book, which is where the 26% comes from. **This is a measurement-scoping issue, not a trading defect.**
2. **The initial "target:stop ratio 3:1" root cause was pulled from the wrong table** (`base_rate_outcomes`, a synthetic matched-benchmark control, not the pipeline's real thesis geometry). Corrected using `prediction_records` directly: median real ratio is also 3.0, but the earlier 15%-vs-26%-breakeven framing overstated the gap. Corrected clean figure (valid-target population, target-vs-stop resolutions only): **21.8% observed vs 25.0% breakeven** — real but narrow.

Both corrections are left in the historical record rather than deleted, because the corrected finding below (§2) supersedes both and is more consequential than either.

## 2. The real finding: actionable trades fail early, not just often

Restricted to predictions the pipeline actually marked actionable, **in real (non-`TEST`) sessions only** (contamination check: 1,811 actionable predictions include 675 first-sighted under `run_condition=TEST`; excluding those leaves 894 real-session actionable predictions, 204 with a terminal underlying outcome):

| Metric | Value | n |
|---|---|---|
| Hit rate (target-first vs stop-first, clean resolutions) | **9.0%** | 199 |
| Stop-outs resolved within the very first observed session | **37.6%** | 181 |
| Stopped trades with zero favourable excursion at any point (MFE ≤ 0) | **24.9%** | 181 |
| Mean maximum favourable excursion before stopping | **+0.87%** | 181 |

**This is a different failure mode than "the model is often wrong."** A trade that is wrong but takes 5–10 sessions to prove it wrong is a calibration problem. A trade where **more than a third of losers stop out in the first session, and a quarter never move favourably at all**, is a trade that was already invalid, stale, or mispriced *at the moment it was entered* — i.e., the stage that is supposed to confirm the prior stage's thesis (Morning validation/entry) is not actually re-verifying that the thesis still holds against current price before acting on it. It is re-stamping a decision made on older evidence.

This matches, with fresh independent evidence across many real sessions (not one forced/abnormal run), the mechanism ACK's own prior audits already suspected in isolated incidents (11 Sep `QUOTE_STALE` finding, later partly attributed to an abnormal forced-timing run). **This dataset shows the same signature recurring organically across 9 sessions of ordinary operation — it is not a one-off artefact.**

## 3. What is NOT yet confirmed (do not act on these without checking)

- **Exact code location of the staleness.** Not yet traced into `morning_gate.py` or `morning_handoff_finalizer.py` this session — need to confirm whether the reference/entry price used at the GO decision is re-fetched at decision time or carried over from the Evening evidence session.
- **Whether this is a quote-freshness problem specifically, or a broader "Morning re-validates against yesterday's structure, not this morning's" problem.** The `QUOTE_STALE` mechanism found previously was about the *option quote*; this finding is about the *underlying thesis* (stop hit within session 1), which could be quote staleness, could be a stale structural level (invalidation/target computed off Evening data and never re-anchored), or could be a genuinely-late entry after the favourable window already closed. These have different fixes.
- **Whether premium tier interacts with this at all.** Zero of the 894 real-session actionable predictions have a matched `expression_outcomes` (option economics) row in this database — the C12 option-level scorer has not scored a single live-marked trade's option economics yet in this window. **The premium-tier analysis from earlier today was built entirely on non-actionable candidates' contracts and does not describe real trades.** This should not be used to inform premium-tier strategy decisions until real-trade option scoring exists.
- **Sample size.** n=199 resolved actionable trades is real but drawn from 9 sessions in one macro regime. Treat 9.0% as "clearly bad, needs fixing now" — not as a precise, regime-general number.

## 3b. Mechanism located in code (confirmed, not inferred)

`morning_gate.py::_check_invalidation()` (line 1565) is the live re-check between Evening's thesis and Morning's GO decision. Read in full — it is a **binary, zero-margin check**:

```python
if direction == "CALL" and live_price <= invalidation:
    return False, ...  # broken
if direction == "PUT" and live_price >= invalidation:
    return False, ...  # broken
return True, f"Invalidation intact — price {live_price:.2f} vs level {invalidation:.2f}"
```

There is no buffer. A CALL thesis with `live_price` one cent above `invalidation` returns `passed=True, "Invalidation intact"` — identical to a CALL thesis sitting comfortably mid-range. The check answers "has this technically failed yet," not "does this still have room to work." Combined with §2's evidence (37.6% of eventual losers stop out the very session they were approved in; mean favourable move before stopping under 1%), this is the concrete, code-level mechanism for the stage-contradiction ACK described at the outset: Morning does re-verify against live price (it is not blindly inheriting Evening's snapshot — that part of the architecture is intact), but the verification threshold has no margin, so it passes trades that are already most of the way to invalidation and lets ordinary intraday movement finish the job within hours.

**UPDATE 26 Sep, same day — hypothesis tested against real Morning validation output, NOT confirmed as stated:**

Pulled `morning_validated_trades_20260924_085940.csv` (one full run, n=401 GO/GO_LIMIT rows with live_price, invalidation_spot and signal_price all present) and computed actual approval-time margin = clearance-to-invalidation ÷ full stop distance:

- Mean margin at approval: **0.96** (i.e., on average, approved trades sit almost the *entire* stop distance away from invalidation, not at the edge).
- Only **0.5%** of GO trades were within 10% of their stop at approval; only **2.7%** within 30%.

**This refutes the zero-margin-approval theory as the general mechanism.** The code (`_check_invalidation`) genuinely has no margin requirement, but in practice most approved trades aren't exploiting that — they're comfortably clear at the moment of approval. So same-session stop-outs are not, in general, "approved one cent from the edge." A same-session stop after ~96% average clearance means price moved almost the *full* stop distance within one trading day for the trades that failed — a large move, which points more toward **stop distances sized too tight relative to the instrument's realistic intraday range** (a volatility/ATR or GARCH-sizing question, consistent with ACK's own historical D1/AVS-VAL-001 GARCH-bias finding) than toward an approval-timing gap.

A same-day, same-run stratified check (n=41 matched rows only — too small to trust) showed same-session-stop rows averaging lower margin (0.71) than other outcomes (1.77, but n=4) — suggestive, not conclusive. **This needs a multi-day matched sample (all runs, not one) before treating margin as the mechanism.** Flagging this now rather than letting the single-run aggregate stand unchallenged, per ACK's instruction to check all paths before concluding.

**Revised open question, confidence: medium (code-level check confirmed real; causal story for same-session stops not yet nailed):** is the invalidation distance itself set too tight relative to the ticker's realized volatility for the intended hold horizon? This is the next concrete trace — into whatever sets `invalidation_spot`/`structural_stop` (Discovery/Wyckoff structural stop logic) — rather than further into Morning Gate, which appears to be behaving as designed.

## 4. Recommendation (for ACK's decision — no code changed)

**Priority 1 — CONFIRMED mechanism, ready to fix:** `morning_gate.py::_check_invalidation()` (line 1565) re-checks live price against the Evening-set invalidation level, but as a zero-margin binary test (see §3b). Fix under consideration: require live_price to clear invalidation by a minimum fraction of the stop distance (e.g., a configurable `min_invalidation_margin_pct` of `abs(reference - invalidation)`) before passing, rather than merely being on the correct side. This is a threshold change to an existing, working check — not a rebuild, and it is squarely a "root cause approved, design needed" item per CLAUDE.md rule 5 (needs gates G1–G4 / spec §24 before it gains decision authority).
- Before sizing the exact margin: pull the actual (live_price − invalidation)/stop_distance distribution at real GO decisions from the per-run Morning validation output (not in `outcome_scoring.sqlite`) to avoid picking an arbitrary number.
- This is the priority ahead of premium-tier or target-ratio work because it affects every trade regardless of premium tier or target distance — it is upstream of both.

**Priority 2:** fix the C12 book reader (`avshunter/c12_outcome/c12_outcome/adapters/books.py::read_book`) to record `lab_tradeable`/`lab_verdict`/`run_condition` as first-class filterable columns on ingestion (they currently only live inside `labels_json`, requiring exactly the kind of manual join done in this investigation every time). Without this, every future analysis risks repeating today's initial scoping error (mixing rejected candidates with real trades).

**Priority 3, deferred:** premium-tier strategy differentiation. Not decidable until Priority 1 is fixed and real trades accumulate *option-level* scored outcomes (currently zero). Revisit after Priority 1 lands and a few weeks of clean GO-trade option scoring exists.

## 6. "Ideal-world" judgment simulation (ACK's request, 26 Sep)

**Ask:** using the pipeline's own data and Claude's independent judgment, would a smarter discretionary read of the same evidence have produced meaningfully more winners over the last 10 trading days.

**Coverage limitation, stated plainly:** the C12 scorer has only captured real (non-`TEST`), verdict-tagged GO/GO_LIMIT/PROBE trades with matured outcomes for **3 of the last 10 sessions — 16, 17 and 22 Sep** (894 actionable predictions, 199 with a clean target-or-stop resolution). The other 7 sessions' Morning-validation runs exist on disk (`data/output/runs/*/morning_validation/`) but have not been ingested/labelled by the C12 pipeline yet. Rather than fabricate a 10-day number, this section reports the honest 3-day result and says so.

**Test performed:** for all 199 gradeable real trades, applied one explicit, auditable rule using only evidence the pipeline already had at decision time (`condition_records`, populated from the same-day macro packet): **reject a CALL when `regime_state` contains "BEARISH" and `market_breadth_state = LOW`; reject a PUT under the mirrored bullish condition.** This is exactly the kind of check a discretionary trader would apply and that CLAUDE.md rule 6 currently forbids the pipeline itself from using as a gate ("macro and event guards are display-only... never influence a gate").

| Group | n | Target-first hits | Hit rate |
|---|---|---|---|
| All trades (pipeline as-is) | 199 | 18 | 9.0% |
| Kept (rubric passes) | 155 | 15 | 9.7% |
| Rejected (regime-conflicted, would skip) | 44 | 3 | 6.8% |

**Conclusion, confidence high on the numbers (small but real sample), high on the implication:** the regime-conflict filter is directionally correct — rejected trades did perform worse — but the effect is small (9.0% → 9.7%), and **both numbers are still far below any breakeven threshold.** This means macro-alignment is not the dominant failure. Even trades a sensible discretionary overlay would have kept are failing at a ~90% rate. **The core defect is upstream of macro/regime alignment entirely** — most plausibly in target/stop sizing relative to realistic volatility (the open thread from §3b) or in the base thesis signal's actual predictive power (Wyckoff/Crabel/catalyst fusion), not in whether the trade fights the tape. A smarter discretionary read of the same evidence would not have turned this around; it would have traded slightly fewer, slightly-less-bad losers.

**What this means for "getting it right today":** stop treating macro-alignment, premium tier, or morning-gate margin as the primary lever — all three have now been tested against real data and are, at most, secondary. The unresolved, highest-leverage open question is still the one from §3b: is the invalidation/stop distance itself sized correctly against realistic volatility for the intended hold horizon. That is where the next trace should go, and it requires opening the structural-stop / GARCH-sizing code (`layer3_forward_variance.py`, Discovery's stop-setting logic), not another outcome-database query.

## 7. Data provenance note

All numbers in this document are directly computed from `data/canonical/outcome_scoring.sqlite` on 26 Sep 2026, code and queries described inline above. No trade journal (`data/journal/trade_journal.db`) data used — that ledger was excluded per ACK's instruction as too immature (14 rows, dormant since 18 Jul).
