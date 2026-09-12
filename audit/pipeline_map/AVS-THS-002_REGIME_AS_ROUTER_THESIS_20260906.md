# AVS-THS-002 — Regime as router: a thesis on the two-probability pipeline and the US Money Index

**Date:** 2026-09-06
**Companion to:** AVS-THS-001 (which assessed the "signal starvation / tiered set" thesis against RCA-003 evidence). This document does not repeat that assessment; it takes the two ideas THS-001 endorsed — the objective "find the money → strongest expression → cheapest convexity → rank", and regime as a *router* rather than a *gate* — and states what they mean for AVSHUNTER as built, using the 6 Sep US Money Index Watch as the worked case.
**Status:** thesis, not authorisation. Nothing here changes an authority.

---

## 1. The thesis in one paragraph

AVSHUNTER is two probability problems wearing one pipeline: **P(move)** — will the underlying travel to the structural target inside the planned hold — and **P(monetise | move)** — will the selected contract convert that travel into an acceptable return before spread, theta, IV and liquidity consume it. Discovery, Vanguard, direction governance and geometry are the P(move) machine; Options Intelligence, the contract lifecycle, viability and monetisability are the P(monetise | move) machine. Neither is calibrated, because the ledger has 294 decisions and one outcome. The regime — rates, USD, oil, breadth, GEX — is evidence about **where P(move) is concentrated today**, and the correct place for it is therefore *ranking within the P(move) machine and sizing at the Execution boundary*, never membership, direction or capital. A day's regime read should change which candidates sit at the top of the book and how large a probe is; it should never change whether a candidate exists. That is what AVS-SD-002's "macro is an advisory sidecar" already says; this thesis makes it operational.

---

## 2. What the Money Index Watch gets right, tested against the pipeline

| Claim in the Watch | Assessment |
|---|---|
| OPEC+ held October unchanged; Hormuz disruption persists; oil shock probability rises | **Factually grounded** (checked 6 Sep: OPEC+ October policy unchanged; US strikes on Iranian tankers 2–5 Sep). |
| Regime label tightened to `RISK_ON_STRUCTURE / MONETARY_HEADWIND / OIL_SHOCK_PERSISTENCE` | Reasonable as a *narrative* state. It is not a pipeline vocabulary — `macro_intelligence_latest.json` carries `regime_state`, `vol_mode`, `risk_on_off_switch`, `liquidity_pulse`. A new three-part label is a fourth vocabulary unless it maps onto those fields. AR-003 §7 on alias drift applies. |
| "No fresh GEX/breadth until the options market reopens — do not invent a gamma regime" | **Exactly right**, and the pipeline already enforces it: `macro_freshness` reads STALE over a weekend and Morning Gate treats macro as display-only. The Watch's discipline matches the code's. |
| Energy/defence calls `PRIORITY_UPGRADE`; rate-sensitive growth calls `ADVERSE_REGIME_RS_REQUIRED`; airlines/transports puts `PRIORITY_WATCH`; broad-index puts `NOT_YET_CONFIRMED` | Correct **as routing** — none of these is a veto. But the labels do not exist in the pipeline, and the Watch does not say *where* they attach. §4 below says where. |
| "Mega-cap AI should not be downgraded; if it keeps outperforming after the market prices the weekend, that is Adverse-Regime Relative Strength" | The most valuable idea in the note, and **the pipeline can compute it deterministically** from canonical daily prices with lineage — it does not need a narrative to assert it. §5. |
| Fund flows: ~$11bn out of US equity funds, ~$49bn into money markets | Plausible context; unverifiable from the pipeline's own data and irrelevant to any field it governs. Advisory narrative only. |
| "Find the money → strongest expression → cheapest convexity → rank" | Endorsed in THS-001. It is the right objective statement and it is *sequential*: regime informs where to look, relative strength finds the expression, contract selection finds the convexity, tiering ranks. Each step is a different authority. |

The one thing the Watch does not address, and the thing that will decide Tuesday: **the pipeline does not currently know whether its monetisable set is *in* the sectors the regime favours.** RCA-003 measured the funnel by direction, not by sector. If the energy and defence names the Watch wants upgraded are among the 426 tickers with no tradeable spread in-band, the routing recommendation is moot until W3.2 (contract repair) lands. That is the first measurement §6 asks for.

---

## 3. Why regime must route and not gate — the evidence, not the principle

Three facts from this week's audits settle the design question empirically:

1. **Macro vetoes were removed on Thursday and the book got better, not worse.** P0-03 made Discovery tiers, Vanguard floors and Horizon routing macro-invariant; the next run's direction mix (190 CALL / 104 PUT, 129 STRANGLE stood down) was cleaner and its lineage held 294/294. Nothing macro-shaped appears in RCA-003's loss table. The gate was never protecting anything.
2. **The losses that matter are microstructure, not macro.** 727 of 1,293 Discovery-to-Lab losses fall on option spread; 94.4% of those are genuinely untradeable contracts. No regime label changes a 62%-of-mid quote. Routing the regime *into contract selection* would be pointless; routing it into *ranking among the 232 that survive* is where it has leverage.
3. **The regime's own inputs are stale for most of the day it is meant to govern.** GEX and breadth are end-of-session artefacts; the Watch itself says so. A router tolerates stale input (it demotes, it does not delete); a gate on stale input is a veto by accident — which is exactly the failure AR-003 P1-06 documented for quote age.

So the regime belongs in three places and nowhere else: as a **ranking overlay** on the monetisable set (which sector/direction sits higher today), as a **sizing input** at the Execution boundary (probe size within AVS-MVP-001 §5, manual for now), and as a **Morning Gate context** (did the overnight move confirm or contradict the regime the thesis was built under). It is excluded from Discovery membership, from direction governance, from contract selection and from `final_action`.

---

## 4. Where each routing label attaches — a concrete mapping

The Watch's labels, translated into fields the pipeline governs, so that no fifth vocabulary is created:

| Watch routing | Pipeline home | Mechanism | Authority |
|---|---|---|---|
| Energy / defence calls `PRIORITY_UPGRADE` | Lab **tier ordering** within Tier 1/2 (THS-001 §4) via a `regime_alignment` advisory column: `ALIGNED` / `NEUTRAL` / `ADVERSE` from `macro_intelligence_latest.json` sector fields × the row's sector | sorts within tier; cannot move a row between tiers | advisory |
| Rate-sensitive growth calls `ADVERSE_REGIME_RS_REQUIRED` | The same column reads `ADVERSE`, **and** a computed `adverse_regime_rs` field (§5) must be positive for the row to sit in Tier 1; otherwise Tier 2 with `tier_reason = REGIME_ADVERSE_RS_UNCONFIRMED` | tier placement, not eligibility | advisory |
| Airlines / transports / discretionary puts `PRIORITY_WATCH` | `regime_alignment = ALIGNED` on PUT rows in those sectors; surfaces them in the Lab's PUT view first | ordering | advisory |
| Broad-index puts `NOT_YET_CONFIRMED` | Index ETFs are not single-name theses; SPY/QQQ/IWM rows carry `regime_alignment = PENDING_REOPEN` until fresh breadth/GEX exist | ordering | advisory |
| Dealer GEX `STALE_WEEKEND` | Already `macro_freshness = STALE`; Lab shows it; nothing reads it for permission | existing | existing |
| Regime label `RISK_ON_STRUCTURE / MONETARY_HEADWIND / OIL_SHOCK_PERSISTENCE` | Map to existing `regime_state` + `risk_on_off_switch` + a new advisory `shock_state` drawn from the AVS-SD-002 §9.4 vocabulary (`PRICE_SHOCK` / `VOLATILITY_SHOCK` / `OUT_OF_DISTRIBUTION`) computed by robust-z on oil, 10Y and USD — **computed, not narrated** | context | advisory |

Every row of this table lands in the Lab as a column with lineage (`macro_packet_id`, `macro_packet_sha256` — both now populated 294/294 after W1/IMP-003). None touches `final_action`, `capital_permission`, direction or the selected contract.

---

## 5. Adverse-Regime Relative Strength — the one new computation worth building

The Watch's best idea is that a stock refusing to fall under a regime that should push it down is evidence of accumulation. That is a measurable property, not a narrative:

```
ars_window      = 5 completed sessions (matches the 1_5d hold; recompute for 10)
peer_return     = sector ETF return over the window (XLK for semis, etc.), or the ticker's Discovery sector basket
ticker_return   = ticker close-to-close return over the window
regime_pressure = sign expected from the regime on that sector: −1 (adverse), 0 (neutral), +1 (aligned)
ars             = (ticker_return − peer_return) × (−regime_pressure)        # positive only when the ticker beats its peers *against* the regime
ars_z           = robust_z(ars over the last 60 sessions)                    # AVS-SD-002 §9.4 form, no new vocabulary
```

Publish `ars`, `ars_z`, `ars_window`, `ars_peer` as advisory columns with `ADVISORY_ONLY` authority and a calculation version. It costs nothing at the provider — every input is already in `historical_prices.sqlite` — and it turns "mega-cap AI is resilient" into a number the ledger can later test against outcomes. Until the ledger has outcomes, `ars_z` orders rows within a tier; it never creates one.

What it must not become: a Discovery input (P0-03), a direction input (direction governance is closed), or a threshold-gated permission. The temptation will be to say "ars_z > 1.5 ⇒ Tier 1"; the honest form is "ars_z is published, Tier 1 requires the existing governed conditions, and the ledger tells us in a month whether ars_z predicted anything."

---

## 6. What to measure before acting on the Watch — and what Tuesday's run will show

1. **Sector-split the funnel.** Re-cut RCA-003's `02_cohort_20260905_151448.csv` by sector: for energy, defence, semis, airlines/transports, discretionary — how many Discovery candidates, how many reached the Lab, how many are `MONETISABLE`, and how many were lost to spread (economic) versus band (recoverable). If the regime-favoured sectors are spread-dead, the routing has nothing to route until W3.2. One afternoon, offline.
2. **Compute `ars_z` retrospectively** on `151448`'s 232 monetisable rows against Friday's regime read and rank them; compare with the Lab's current order. This is a dry run of the overlay with zero production change.
3. **Tuesday's Morning run is the regime test the Watch itself defines**: "does US capital continue buying the strongest equities despite persistent oil, higher-rate and geopolitical pressure?" The pipeline answers it mechanically — how many `MONETISABLE` rows survive Morning viability, and whether survivors skew to `ars_z > 0`. That single artefact will say more about the router thesis than any narrative can.
4. **If the regime does flip** (oil ↑ + yields ↑ + USD ↑ + VIX ↑ + credit widening + QQQ/IWM weakness, per the Watch's own criterion), the pipeline's response should be *observable in the book* — PUT share rising, `regime_alignment` flipping sector by sector — not a veto. If it is not observable, the overlay is not wired; if the book empties, a gate has crept back in.

---

## 7. Limitations of this thesis

- The Watch's narrative — and `macro_intelligence_latest.json` itself — is produced by a three-prompt LLM sequence (`build_macro_json.py`). It is a model output feeding a model. Everything in §4 treats it as advisory context precisely because its own accuracy is unmeasured; §5 exists so that the one claim worth acting on has a computed, lineaged form.
- No outcome data. P(move) and P(monetise | move) are both uncalibrated; every ranking rule here is policy until the ledger matures. The ledger started capturing candidates on Friday; nightly outcome maturation (AVS-FIX-001 W3.9) is implemented and awaiting its first run.
- Sector taxonomy: the pipeline's sector fields come from Discovery's universe scanner; the mapping to "defence" or "oil services" needs checking before any sector-level routing is trusted.
- The Money Index composite itself (10Y, USD, oil, breadth, GEX, flows) is a research construct; it has no field in the pipeline and should not acquire one until its components are each lineaged inputs.
- Morning attrition is unmeasured (RCA3-D09); the router's most important effect — what survives the open — is unknown until Tuesday.

---

## 8. Recommendation

Adopt the objective and the router principle; adopt nothing that creates a new vocabulary or a new authority. Concretely, and only after Level 1 is declared: add `regime_alignment` and `ars_z` as advisory Lab columns with lineage (one small slice), sector-split the funnel offline this week to see whether the regime's favoured sectors are even tradeable, and let Tuesday's Morning run be the first test of "does capital keep buying the strongest names". The Watch is a good analyst's note. The pipeline's job is to turn its one testable claim into a number and then wait for the ledger to grade it.

Sources for the factual checks: [OPEC+ keeps October policy unchanged (CNBC, 6 Sep 2026)](https://www.cnbc.com/2026/09/06/opec-oil-output-october.html) · [OPEC+ pauses output hikes (Nairametrics)](https://nairametrics.com/2026/09/06/opec-pauses-oil-output-hikes-after-four-straight-monthly-increases/) · [US strikes Iranian tankers after Navy ships targeted (NPR, 5 Sep)](https://www.npr.org/2026/09/05/nx-s1-5959159/us-iran-warships-targeted) · [Iran claims attacks on US-linked vessels as Hormuz clashes intensify (Euronews, 5 Sep)](https://www.euronews.com/2026/09/05/iranian-media-report-us-strike-on-iranian-oil-tanker-near-kharg-island) · [Two tankers hit Hormuz mines (CNBC, 2 Sep)](https://www.cnbc.com/2026/09/02/us-iran-war-trump-hormuz-irgc-jordan-bahrain.html)
