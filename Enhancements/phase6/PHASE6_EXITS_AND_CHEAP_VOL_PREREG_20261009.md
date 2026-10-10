# Phase 6 pre-registration: exits into strength (E) and cheap volatility against forecast (V)

**Date:** 9 Oct 2026, written before any result was computed. **Approved scope:** ACK, "start phase 6 with exits and
cheap volatility". **Edge being tested:** buy from the market makers before the herd, sell into the herd
(`project_edge_definition_pre_herd`), judged on expectancy, not hit rate.

## Data (read-only)

| Source | Use |
|---|---|
| `Enhancements/lean_path_test/lp2_trades.parquet` | The pre-registered universe-test trades (7 Oct). Policy **X1** rows only: entry Friday at the **ask**, X1 herd / invalidation / time exit at the **bid**. LEAN (setup) trades at **ATM** and **0.35 delta**; PLACEBO (random entry, same ticker and Friday) at ATM |
| Canonical daily bars (`read_bars`) | Underlying high / low / close between entry and exit; returns for the volatility forecast |
| `layer3_forward_variance._har_rv_forecast` | The pipeline's own HAR-RV forecast, reused, on daily log returns **up to the entry date** (no look-ahead) |

**Periods (unchanged from the universe test):** original to 2025-06-27; **test 2025-07-04 to 2026-08-21**.
Statistics: 4-Friday block bootstrap (B = 5,000, ≥ 8 blocks), one-sided, Holm at 0.05 within each family, and the
same sign in both halves of the test period. Return = exit price / entry ask − 1, every loser counted.

## Study V: cheap volatility against the forecast

- **Feature:** `vol_ratio = entry ATM IV / HAR-RV 20-session forecast` (both annualised).
- **Groups:** quintile cut-points computed on the **original period only** (LEAN and PLACEBO pooled); CHEAP =
  bottom quintile, RICH = top quintile, applied unchanged to the test period.
- **Family V (ATM, test period):**
  - **V1:** mean X1 return of CHEAP LEAN trades > 0.
  - **V2:** mean return CHEAP − RICH, LEAN trades, > 0.
  - **V3:** mean return CHEAP − RICH, PLACEBO trades, > 0 (cheap volatility on its own, no setup).
- 0.35 delta: the same three quantities reported side by side (descriptive, outside the Holm family).

## Study E: exits into strength

**Option value between Fridays (model):** Black-Scholes, r = q = 0, IV = the contract's own implied vol solved from
its entry mid, held constant; underlying at each day's favourable extreme (high for calls, low for puts) and close.
Sellable value = model value × (1 − half the entry spread fraction).

**Model check, reported first:** at each trade's actual X1 exit Friday, model sellable value vs the actual exit bid
(median ratio and bias, by side). The model is used regardless; the check states how far to trust it.

**Rules,** each applied to every LEAN X1 trade from the session after entry to its X1 exit date (inclusive); if not
triggered, the trade keeps its actual X1 result:

| Rule | Exit |
|---|---|
| **E1 TP+50** | A resting sell at 1.5 × entry ask: filled at that price on the first day the sellable value at the day's extreme reaches it |
| **E2 TP+100** | The same at 2 × entry ask |
| **E3 TP+200** | The same at 3 × entry ask |
| **E4 Trail** | Once the sellable close value has reached 1.5 × entry ask, exit at the first close where it falls to ≤ 0.75 × its peak close value, at that sellable value |

- **Family E (ATM, test period, paired on the same trades):** **E-k:** mean (return under E-k − return under X1) > 0,
  for k = 1…4.
- Reported side by side: the absolute mean return under each rule, 0.35 delta, and PLACEBO (descriptive).
- **Descriptive combination:** CHEAP × the best exit rule.

## Known limits (stated before results)

- The model holds IV constant: in rallies call IV often falls and in sell-offs put IV often rises; the model check
  shows the net bias.
- A resting limit that is touched is assumed filled at its price; daily extremes are a single print, so fills at the
  very high may be optimistic. Reported, not adjusted.
- Weekly chain data before May 2026: the actual option is only observed on Fridays.
- Results are descriptive of these rules on this history; they grant no authority (rule 5, gates G1–G4).
