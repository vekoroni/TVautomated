# Intelligence Lab data validation: SOFI example, whole book (3 Oct 2026)

**ACK's request:** "the data accuracy need to be validated before it can be used for trading … from a veteran trader does the data make sense and is it tradable … review inconsistencies. sofi is used as an example".

**Basis:**
- Run `20261001_211641` (Evening 1 Oct) with the Morning post-open refresh of 2 Oct, gate time 16:58Z.
- 18 Lab screenshots (3 Oct, 09:51–10:12).
- The Lab payload as served (`/api/run/20261001_211641`: 1,554 rows; 144 GO, 203 GO_LIMIT).
- Canonical daily bars.
- Code.
- Independent cross-check: Tastytrade market metrics (read-only, production), used for earnings dates and the one-year IV percentile only.
- No pipeline input was changed.

## 1. What is accurate

The arithmetic and quotes that were checked against source data are correct:

| Item | Lab | Check |
|---|---|---|
| SOFI close 1 Oct | 15.84 | Canonical bar 15.84 |
| Morning price | 15.92 (+0.51%) | SmartMid, 4.8 s old |
| Contract quote | 1.49 / 1.51, spread 1.33% of mid | Morning file; the EOD quote was 1.54 / 1.58 |
| IV | 52.4% (contract), 53.6% (ATM) | Tastytrade Dec-18 expiry 55.5% at the 2 Oct close |
| Greeks | Δ −0.447, Γ 0.103, Θ −0.0089, ν 0.029 | Black–Scholes at S=15.92, K=16, T=0.15, σ=0.524: Δ −0.46, Γ 0.12, ν 0.025 (consistent) |
| Intrinsic / extrinsic | $0.08 / $1.43 (94.7%) | 16 − 15.92 = 0.08; 1.51 − 0.08 |
| Breakeven, max loss | 14.49 (−8.98%), $151 | 16 − 1.51; ask × 100 |
| HV 30d | 44.1% | HV20 32.8%, HV60 52.9% from bars (consistent for 30 sessions) |

## 2. Inconsistencies: whole book

Counts are over the 144 GO rows. "Next Evening" marks defects already fixed in code that the 1 Oct book predates.

| # | Defect | GO rows affected | Root cause | Severity | Status |
|---|---|---|---|---|---|
| N1 | **GO without an eligible trigger.** Morning GO is a fall-through: any row that is not invalidated, has a quotable contract and raises no flag becomes GO. Trigger state and candidate status are never checked. | 74 have no eligible trigger (XLF: `trigger_primary` NONE). By candidate status: 74 REPAIR_AT_OPEN, 16 WATCH_ONLY, 54 TRIGGER_REQUIRED. | `morning_gate.py:2790` (the `else` branch). | Critical | **New** |
| N2 | **Earnings calendar disconnected.** Earnings came from the Polygon snapshot field; live data moved to SmartMid, which has no earnings field, so every row is UNKNOWN. UNKNOWN is then treated as "no catalyst". Breaks rule R1, "missing is never neutral". | 144/144 UNKNOWN; 138 NO_CATALYST. In a sample of 13 GO tickers, 11 report before contract expiry and 6 inside the 20-session hold (SOFI 27 Oct, AMZN 29 Oct, INTC 22 Oct, UNH 13 Oct, NET 29 Oct, TWLO 29 Oct). 54 rows are tagged EVENT_PRICED with NO_CATALYST. | `morning_gate.py:2510–2526`; `catalyst_truth` has dates on 15 of 1,675 rows, all from August. | Critical | **New** |
| N3 | **Delayed option quotes labelled current.** Option quotes come from a delayed feed (`DELAYED_PROVIDER_FEED`), while the trade setup says "a current, executable quote" and the card says STALE. | 144/144; raw age median 22 min, max 30 min. | Quote feed tier; the label ignores `execution_viability_quote_feed_state`. | High | **New** |
| N4 | **THESIS_CONFIRMED does not mean confirmed.** No material move, or a move against the trade, becomes THESIS_ACTIVE, then EXECUTABLE_NOW, then THESIS_CONFIRMED. | 121 had no material move; 64 had moved against the trade. | `orchestrator/dynamic_validation.py:390–396`. D11 fixed the material adverse case only. | High (wording) | **New** |
| N5 | **Sector alignment is direction-blind.** The sector's long bias is shown unchanged on puts. A PUT in a lagging sector reads HEADWIND while the gate computes TAILWIND (SOFI, XLF). | 22 | `contracts/interpreter_macro_context.py:498` (`_sector_bias_lookup`) | Medium (display) | **New** |
| N6 | **IV percentile on 20–106 sessions labelled `IV_HISTORY_252D`.** The CHEAP/FAIR/EXPENSIVE labels follow from it. | 144/144. Against the one-year IVP: SOFI 48% vs 10%, AMZN 15% vs 62%, HIMS 39% vs 7%, SHOP 65% vs 34%, XLF 69% vs 38%. | Short IV history; label not tied to the window. | Medium–High | Known ("IV rank vs IVP mismatch"), not fixed |
| N7 | **Three conflicting hold horizons.** Move window 1–5d, planned hold 20 sessions, and a time stop computed on an assumed 30-DTE contract (SOFI "exit by 19 Oct", `ts_expiry` 31 Oct against a Dec-18 contract). Theta exit dated after expiry. | 142 with a 1–5d window and a 20-session hold; 140 where the time-stop expiry differs from the contract's; 48 with the theta exit after expiry. | Time-stop module not fed the selected contract. | Medium–High | **New** |
| N8 | **Gamma walls are max-OI strikes across the whole chain, including far-dated LEAPs.** | 36 call walls more than 25% from spot (XLF 75 at +40%, CELH 60 at +119%). | Wall not restricted to the trade's expiries or gamma-weighted. | Medium | **New** |
| N9 | **Q-Omega shows deprecated legacy expected moves.** 6.31 / 2.61 / 3.70 are labelled 1–5D / 6–10D / 11–20D; the governed cumulative 1σ values are 7.47 / 10.56 / 14.93%. | 144/144 | `l3_expected_move_legacy_deprecated=True` but still displayed. | Low–Medium | **New** |
| N10 | **`conflict_state` SOFT_CONFLICT carries no information.** It shows beside `direction_conflict_status` NO_CONFLICT. | 143/144 | Soft EIL flags roll into conflict_state. | Low | **New** |
| N11 | **Alternative contracts show OI 0** (SOFI Nov-13 puts, oi=0). Probably missing data shown as zero. | 75/144 | Needs a trace. | Low–Medium | **New**, to verify |
| N12 | **Wyckoff phase bucket MARKUP on distribution-phase puts.** It also enters the actuarial state key (SOFI was matched as MARKUP). | 7 | Wyckoff field mapping | Low–Medium | **New** |
| N13 | **DOI prefers a different contract;** the governed contract is absent from the DOI ranked list (SOFI Dec-18 16P). | 101 | Contract selection | Medium | Known (D05), open |
| F1 | **Invented 3R target and zero-risk R:R.** SOFI target 4.87 (−69%), "+962% on premium"; XLF 38.04 (−29%). | 104 with a 3R target; 104 with `RR_ANOMALY_ZERO_RISK`. 31 have a target more than 3σ away in 20 sessions. | D01/D13 | High | Fixed, next Evening |
| F2 | **Direction from one evidence item** (legacy direction) | 142 | Direction source | High | Fixed, next Evening (`beh001_v1`) |
| F3 | **Wyckoff OBSERVE_ONLY;** Phase/Event not categorised | all | D10 | Medium | Fixed, next Evening |
| F4 | **USMI SECTOR_UNMAPPED** | most | D03 | Medium | Fixed, next Evening |

## 3. Veteran read: SOFI PUT (GO / BUY_NOW, rank 5)

**Price structure (canonical bars):**
- SOFI has traded in a range of 14.88–20.13 since April.
- It fell 19% from the late-August high of about 19.5 to 15.84.
- That leaves it 6% above the range floor: the 29 July low of 14.88, the put wall at 15 and the gamma island at 15.
- Realised volatility has compressed (HV20 33% against HV60 53%). That is the VOL_COMPRESSION trigger, and it is valid on realised volatility.

**Verdict: not tradable as presented.**
- **Reward:**
  - The first realistic target is the range floor at 14.9–15.0, a 6% fall.
  - The 4.87 target is the invented 3R scenario.
  - The breakeven at expiry (14.49) sits below the range floor, so the put needs a range break to pay at expiry.
- **Risk:** the stop at 19.50 is the top of the range, 23% away. That is about 0.25 R:R to the first target.
- **Timing:** the move from 19.5 has already happened. Entering 6% above support is following the herd, not getting ahead of it.
- **Event:** earnings on 27 Oct fall inside the 20-session hold. The pipeline does not know this.
  - IV is low against its own year (IVP 10%) but high against recent realised volatility (IV/HV30 1.6). The October 30 expiry carries 57% IV against 45% for October 23: that is the earnings premium.
  - Holding through the report is a gap trade, not a structure trade.
- **Data confidence:** the quote was 22 minutes old on a delayed feed, and the "confirmed" morning label followed a move against the put.

**What would make it a trade** (from the pipeline's own levels):
- **Trigger:** a daily close below 14.88–14.93. The pipeline's own WBS phase-C trigger is 14.93.
- **Invalidation:** a close back inside the range, around 16.0–16.5, not 19.5.
- **Target:** about 12.3 (1.5σ over 20 sessions). The range-height projection is about 9.6, over a longer horizon.
- **Earnings:** an explicit choice to exit before 27 Oct, or to hold through it knowingly at a smaller size.

**XLF PUT (GO):**
- No trigger at all.
- Phase B, a range with no trend.
- Stop +9.6%, about 2σ at 16% IV.
- Target −29%, the invented 3R scenario.
- Call wall at 75 (+40%).
- Not tradable.

## 4. Can the book be traded today?

**No, not from the GO list as published.**
- **Half of the GO list has no eligible trigger (N1).** These rows are contract-repair or watch candidates that the Morning promoted because their quote was clean.
- **No row knows its earnings date (N2).**
- **Every option quote is delayed by up to 30 minutes (N3).**
- The first two are decision defects, not display defects.

**Until they are fixed, trade from the card only when all of these hold:**
1. The trigger is present and GO-eligible.
2. Earnings have been checked by hand against the hold and the expiry.
3. The contract has been re-quoted at the broker.
4. The invalidation and target make sense against the range (F1 is fixed from the next Evening).

**Recommended fix order** (each test-first, one at a time, against the outcome scorer):
1. **N1:** the Morning must not grant GO to rows without an eligible trigger, or in REPAIR_AT_OPEN / WATCH_ONLY. Rank, don't gate: they stay visible with their state.
2. **N2:** an earnings source with explicit UNKNOWN / NONE / DATE states, shown on the card against the hold and the expiry. Disclosure only (see the addendum).
3. **N3, N4:** say what was measured. "Quote delayed N min (feed)". THESIS_INTACT instead of THESIS_CONFIRMED unless the move was favourable and material.
4. **N7:** one hold horizon, with the time stop computed on the selected contract.
5. **N5, N6, N8, N9:**
   - side-aware sector alignment;
   - an IV-percentile label tied to its window;
   - walls from the trade's expiries;
   - remove the deprecated expected moves.

## Addendum (3 Oct 2026): ACK on catalysts; earnings source checked

**ACK:** "catalyst are added bonuses we should have enough data and functionality to produce a trade without any catalyst". The Polygon subscription has been restored.

**N2 is reclassified from Critical to Medium (risk disclosure):**
- A trade must stand on structure, trigger, levels and contract alone. The GO path does not depend on catalysts, and must not.
- An earnings date inside the hold or the contract's life is not a catalyst for the thesis. It is a position risk (gap, IV crush) that the trader must see. It is disclosed on the card and never gated or scored.
- UNKNOWN must still be shown as unknown, not as "no catalyst" (rule R1).

**Earnings source, tested read-only on SOFI:**
- **Polygon v2 snapshot** (the source `earnings_calendar_enricher.py` assumes): the response has no `earningsAnnouncement` field (keys: day, min, prevDay, ticker, todaysChange, todaysChangePerc, updated). That field name belongs to another vendor's quote API. **The enricher has never produced a date, with Polygon or without it.** Switching back to Polygon does not restore earnings.
- **Polygon Benzinga earnings:** 403, not in the plan.
- **MarketData `/v1/stocks/earnings/SOFI/`:** works on the current subscription. Fiscal Q3 2026, report date 2026-10-27, before the open, estimated EPS 0.17. This matches Tastytrade.

**Proposed design** (needs ACK approval before code):
- Feed `earnings_calendar_enricher` from the MarketData earnings endpoint, one call per ticker, cached per session.
- Publish `earnings_date`, `earnings_report_time`, `earnings_state` (DATE / NONE_SCHEDULED / UNKNOWN), `earnings_inside_hold` and `earnings_inside_expiry`.
- Show them on the trade card under "How long".
- Display only: no gate and no score.
