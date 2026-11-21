# Magnitude and relative-strength study: results (7 Oct 2026)

- **Pre-registration:** `MAGNITUDE_AND_STRENGTH_STUDY_PREREG_20261007.md`.
- **Script:** `magnitude_strength_study.py`.
- **Raw output:** `magnitude_strength_study_20261007.json`.
- **Post-hoc check:** `magnitude_posthoc_normal_vol.py` / `_20261007.json`, labelled exploratory.
- **Scope:** read-only.
- **Universe:** survivorship-free point-in-time top 3,122. 100 cuts, 2022-10-11 → 2026-09-23; 312,200 name-cuts.

## Pre-registered results (top 100, episodes)

| Test | Result [95%] | Halves | Pre-registered verdict |
|---|---|---|---|
| **M1, coiled** (low ATR for the name, weekly ADX < 20) | P(±3 current ATR in 20 sessions) **80.5% vs 63.4% base, +16.0** [+13.9, +18.2] | +15.7 / +16.4 | Passed. **Overturned below** |
| M2, volume pressure at a 20-session edge | 49.9% vs 63.4%, **−13.3** [−14.9, −11.7] | −14.3 / −12.1 | Not accepted |
| R1, 12-1 momentum (100 strongest UP, 100 weakest DOWN) | relative 60-session return −0.2 points [−6.6, +4.2] | +1.8 / −2.7 | Not accepted (Holm p 0.96) |
| R2, 52-week-high proximity | −2.6 [−7.2, +0.3] | −0.8 / −4.5 | Not accepted |

## Why M1's pass is not an edge (post-hoc, exploratory)
- **The flaw:** the pre-registered event is measured in the name's **current** ATR, and M1 selects names whose current ATR is unusually low. So "3 ATR" shrinks for exactly the names selected. Volatility returning to normal hits it mechanically.
- **The rescale:** using each name's **normal** volatility (median ATR of the previous 250 sessions) instead:

| Signal | P(±3 normal ATR in 20 sessions), top 100 | Excess [95%] | Move vs normal volatility |
|---|---|---|---|
| M1, coiled | 56.0% vs 64.3% base | **−6.7** [−9.9, −4.0] | −0.06 [−0.10, −0.03] |
| M2, volume pressure | 61.2% | −3.1 [−4.3, −1.7] | −0.01 (not significant) |

- **Coiled names move less than average, not more.** The pre-registered pass is withdrawn: **M1 is rejected.** The lesson goes into every future pre-registration: **never scale an outcome by the variable a signal selects on.**

## What this means
1. **Every price-only signal tested so far fails.** Four studies cover:
   - the pipeline's setups;
   - five side rules;
   - a top-down trend read;
   - compression;
   - volume pressure;
   - 12-1 momentum;
   - 52-week-high proximity.
   On a survivorship-free universe of liquid US stocks over 3.5–4 years, none predicts direction or magnitude beyond what the market already shows.
2. **Not tested: information beyond price.**
   - implied vs realised volatility (whether an option is cheap for the move that follows);
   - earnings and event reactions;
   - options flow and positioning.
   These need historical options data (MarketData) or event data, and are where a long-options edge would have to come from.
