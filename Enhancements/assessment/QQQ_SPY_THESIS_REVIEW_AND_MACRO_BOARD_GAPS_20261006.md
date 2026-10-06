# Review: QQQ/SPY/ETF trading thesis (6 Oct 2026) and gaps in the ETF macro board

Reviewed: `OneDrive/AVSHUNTER_QQQ_SPY_ETF_Trading_Thesis_2026-10-06.docx`, the rebuilt edition.
Checked against the live packets in `dropbox/macro/`, the price store, the FRED master, the
option-chain store (`data/phantom/phantom_history.db`), the latest pipeline runs and
`macro_board/`.

## 1. Verdict on the thesis

The thesis is sound, and I agree with almost all of it. It is a decision-process document,
not a signal. Its main rules match AVSHUNTER's own:
- missing is not adverse;
- composites are not probabilities;
- advisory layers carry no authority;
- repeated coverage is not independent evidence;
- a correct direction is not the same as a profitable contract;
- the framework is unproven until it is measured point in time.

### Verified

| Claim | Check | Result |
|---|---|---|
| Option repricing table (section 8) | Black–Scholes recomputed: S=K=700, 14/365, IV 25%, r 4%, q 0.6%, ±$0.05 spread, $2 fees | All four P&Ls reproduce to the cent (−168.55, −272.81, +388.84, +518.25). Initial values 14.1205 / 13.2084, delta 0.5203 / −0.4795, gamma 0.01162 and vega 0.5461 all match. |
| Theta −0.5200 / −0.4549 | Analytic BS theta per calendar day | Matches. Full one-day repricing at unchanged spot and IV gives −0.529 / −0.464, the decay a holder actually sees. |
| Appendix A attribute paths (49 paths) | Read from live `avshunter_us_money_index.json` rev 22 | All exist. |
| Appendix C attribute paths | Read from live enrichment delta | All exist, including `source_scores` with zeros marked `UNSCORED_...`. |
| Money Index score 75/100; method "not a trade probability" | rev 22 | Confirmed. |
| 5 Oct S&P 500 +0.66%, Nasdaq Composite +1.05% | `cash_close_snapshot_2026_10_05` | Confirmed. The price store has QQQ +0.88% and SPY +0.67%, which supports "Composite is not QQQ". |
| `last_us_cash_session` dated 25 Sep inside a 6 Oct packet | rev 22 | Confirmed. |
| HY OAS 3.10% dated 2 Oct; older state 3.24% | FRED master and the packet | Confirmed. |
| VIX 15.52 vs older 16.31 qualifier; small-cap +$0.223bn | rev 22 | Both present. |
| Dealer gamma unknown | `dealer_gamma_gex.authoritative_inventory_available = false`, status UNCONFIRMED | Confirmed. |
| Event payload `forecast = null`; `evidence_quality` changes type across versions | 5 Oct payload: forecast null, evidence_quality a string | Consistent with the thesis's schema caveat. |
| Worked-scenario distances and the 8% × 3% = 0.24 pp holding example | Arithmetic | Correct. |

### Could not verify from the repository

- The **6 Oct 06:50 UTC event packet** (`…event_payload_2026-10-06(1).json`) and the
  **07:37 BST news packet** (`…enrichment_delta_2026-10-06_pre_london_0737BST.json`) do not exist
  anywhere under the repo, OneDrive or Downloads. `dropbox/macro/` holds older versions: the
  5 Oct event payload, and the 04:46 UTC news packet at fragility 4.7, not 4.6. Brent $99.49,
  WTI $88.43 and event confidence 91 therefore cannot be checked. Section 10 can't be
  reproduced from the repo, which conflicts with the thesis's own section 12 requirement for
  point-in-time packet versions.

### Where I would qualify the thesis

1. **Mechanism signs should be measured, not assumed.** Scenario A says inflation news is
   "adverse through discount rates" for QQQ. That is a textbook prior. On recorded history
   (Aug 2021 – Oct 2026), QQQ's 20-session forward return while the 10Y was RISING was
   +0.36% *better* than in other yield states (t 0.27, so no measurable effect). Section 4's
   Propose step should cite the measured sign for that ETF, or record "unmeasured".
2. **Uncertainty over a fixed minimum.** The thesis asks for uncertainty to be reported
   instead of a universal minimum sample count. The board shows t and window counts but no
   interval. Agreed: add intervals and keep the window count only as a label.
3. **Theta wording.** State that −0.52 is the instantaneous rate. The one-day repricing
   (−0.53) is what the table's method actually produces.
4. **The pipeline already answers "What does the pipeline propose?" for ETFs.** The 5 Oct
   run has governed rows for DIA (PUT, ARMED), SMH (CALL, ARMED), XLK (ARMED), TLT (PUT,
   STAND_DOWN, target 76.76) and IWM (UNRESOLVED, STAND_DOWN) in
   `options/options_candidates_ranked.csv`. The thesis treats this as something to obtain;
   it is available now.

## 2. Board gaps, where I agree with the thesis

Status: ✓ covered · ◐ partial · ✗ gap.

| # | Thesis principle (section) | Board today | Gap and proposed fix | Data available? |
|---|---|---|---|---|
| G1 | Information clock: observation ≠ publication ≠ receipt ≠ decision (2, 10) | ◐ file-level as-of and age only | Show the **observation date on each condition tile** (yields and curve currently use FRED 2 Oct, two sessions old). In the intel panels, show the packet's inner dates: HYG close 10 Sep, `last_us_cash_session` 25 Sep, GEX 2 Oct. | Yes |
| G2 | Expectation basis; null forecast means no surprise (2, App. B) | ✗ shows surprise score | Show actual / forecast / previous. When forecast is null, show "no consensus – surprise not measurable". | Yes |
| G3 | Composites are not probabilities (10, App. A–C) | ◐ shown without caveats | Label 75/100, confidence 90 and fragility 4.7/5 as "uncalibrated". **Score the Money Index**: its `revision_history` has 22 timestamped scores (11 Sep – 6 Oct) that can go on the Scorecards tab now. | Yes |
| G4 | Point-in-time packet versions (12) | ✗ reads latest only; `dropbox/macro/Archive` uses ad-hoc names | On each build, the board saves a **content-addressed copy of every input it read** under `macro_board/output/inputs/<sha>`, so every board decision can be reproduced. Separately, the upstream automations should drop each version into a governed archive (an ops step outside the board). | Yes (board side) |
| G5 | "What does the pipeline propose?" (desk card) | ✗ | Read-only panel per ETF from the latest full run: canonical direction, options verdict, target, invalidation and the stand-down reason. Board-only display, no authority. | Yes |
| G6 | Separate the underlying opportunity from the contract (8) | ✗ no option data | From executable chain quotes, not a model: **ATM straddle implied move** per expiry vs the board's analog 10th–90th pct move, plus bid/ask spread %. Show quote age (chains to 2 Oct; provider IV null recently, so derive from mid). | Yes (phantom DB, SPY/QQQ/IWM/TLT/XLK/SMH …) |
| G7 | Stage of the move / entry has deteriorated (7, Scenario C) | ◐ raw returns only | "Move already made": 5d and 20d return in units of the ETF's own realised vol, distance to the 20d high/low, labelled descriptively ("extended" / "not extended"). | Yes |
| G8 | Classify the response as supporting / absorbing / mixed / insufficient (4) | ✗ | A descriptive label per ETF: measured headwinds active today (negative sensitivity with \|t\| ≥ 1) against the ETF's own response (trend, RS vs SPY). Uses measured signs, never textbook signs. Display only. | Yes |
| G9 | Translate into holdings; QQQ ≠ "tech" (6) | ✗ | Top-holding contribution to QQQ/SPY moves. **Needs a holdings-weight source** (Invesco/SSGA files); none found in `config/` or `dropbox/`. Constituent prices are already in the store. | **No — ACK decision** |
| G10 | Distinguish yield drivers: real vs breakeven, term premium, single-B (3) | ✗ | Add FRED DFII10, T10YIE, a term-premium series and single-B OAS to the Colab FRED master. The board then splits "yields rising" into its drivers. | **No — Colab producer change** |
| G11 | Report uncertainty, no invented minimum (12) | ◐ t-stat and window count | Add an 80% interval for analog and base means. Keep the window minimum only as a label. | Yes |
| G12 | Do not transfer to leveraged/inverse/vol products mechanically (14) | ◐ note only | Suppress 5d and 20d leans for the leveraged, inverse and volatility groups (path-dependent); keep 1d. | Yes |
| G13 | Unknown gamma stays unknown (5, App. A) | ◐ shows "NEGATIVE" regime | Relabel as a "model estimate, dealer sign assumed; authoritative inventory unavailable (Money Index)". Show its age (2 Oct). | Yes |
| G14 | Fed assets − TGA − RRP is a research proxy (App. C caveat) | ◐ named "Net liquidity" | Rename to "Net liquidity proxy". The board already subtracts only ON RRP, never both, as the thesis requires. | Yes |
| G15 | Decision record that can expose errors (11) | ◐ saves leans only | Desk decision card per ETF, pre-filled with the board's facts (what changed, lean, pipeline proposal, implied move). The trader completes the rest and downloads JSON to a journal folder. Later builds score journal decisions. | Yes |
| G16 | Repeated coverage ≠ independent evidence (2, 11) | ✗ | Show when several advisory panels cite the same underlying event (shared event IDs or tickers), e.g. the CENTCOM disclosure appearing in both the event and news packets. Display only. | Partly |
| G17 | Response is often intraday (Scenarios A/B) | ✗ daily only | SPY/QQQ intraday bars are not in the store (only IWM and XLF among index ETFs). Needs the intraday backfill extended. | **No — data** |
| G18 | Show what macro adds beyond price (12, ablation) | ◐ "excess vs base" column | Score the board's leans against a price-only baseline lean (unconditional drift) on the same dates. | Yes |

Already covered: missing ≠ adverse; next-open forward returns; held-out check; relative vs
absolute direction; advisory authority labels; latest-macro-wins scoring of packets;
leveraged-product warning text.

## 3. Recommended order

1. **Board, data in hand (small):** G1, G2, G3 (labels and the Money Index scorecard), G4,
   G11, G12, G13, G14.
2. **Board, data in hand (medium):** G5 pipeline proposals, G6 implied move vs analog move,
   G7 extension, G8 response label, G18 baseline.
3. **Needs ACK or an upstream change:** G9 holdings source, G10 extra FRED series, G17
   SPY/QQQ intraday, and landing every automation packet version in `dropbox/macro` with a
   governed archive. G15 decision card once G5 and G6 exist.

## 4. Status after implementation (6 Oct 2026, ACK approved the small and medium fixes)

| Gap | Status |
|---|---|
| G1 observation dates | Done. Tiles show the observation date and sessions old (yields and curve: 2 Oct, 1 session; liquidity: 30 Sep, 3 sessions). The Money Index card lists its inner dates. |
| G2 expectation basis | Done. Actual / forecast / previous are shown; a null forecast reads "no consensus · surprise not measurable". |
| G3 uncalibrated composites | Done. Labelled. The Money Index is scored by its own ladder (22 revisions → 13 sessions; all bands still below 8 independent windows). |
| G4 input archive | Done. 16 inputs are archived per build under `macro_board/output/inputs/`, with the manifest in the snapshot. |
| G5 pipeline proposals | Done. Plus remaining opportunity from today's close: SPY CALL has used 53% of its entry→target move. |
| G6 implied move | Done. 76 ETFs; e.g. SPY 20d priced 2.95% vs analog 2.96% (1.00×), QQQ 1.24×, XLK 1.73×. |
| G7 move already made | Done. TLT is −2.2σ over 20 sessions (extended down). |
| G8 response label | Done. SPY 20d: absorbing pressure (headwinds: realised vol, curve level; tailwind: breadth). |
| G11 intervals | Done (80%). |
| G12 path-dependent products | Done. 5d/20d leans withheld; evidence still shown. |
| G13 dealer gamma | Done. Labelled as a model estimate with assumed sign; the Money Index's "authoritative inventory unavailable" is shown. |
| G14 liquidity proxy | Done. Renamed. |
| G18 price-only baseline | Done. Recorded in snapshots and scored beside the board's leans. |
| G9 holdings | **Done (rev c).** Issuer daily files (ACK): State Street SPY/DIA, Invesco QQQ. Start-of-window weights reconcile with the ETF return (20d: SPY +0.69% vs +0.60%, DIA −4.02% vs −4.11%, QQQ +4.87% vs +5.18% with 3.9% weight unpriced). Earlier note: | The Polygon/Massive `etf-global` constituents endpoint exists but returns 403 "not entitled" on the current plan. MarketData.app has no ETF-holdings endpoint. Needs the ETF Global add-on or issuer holdings files (ACK decision). |
| G10 extra FRED series | Pending. ACK will upload the Colab script once the board is finished. |
| G15 decision card, G16 shared-event flag, G17 SPY/QQQ intraday | Open. |

### Rev c additions (6 Oct 2026)

- **tastytrade market metrics** were added to the board (ACK). The repo's read-only bridge
  `bridge/tastytrade_readonly_mcp.py` gained one allow-listed read tool,
  `tastytrade_get_market_metrics`, with a `market_metrics()` method. Order, position and
  balance tools remain refused, as tested in `tests/test_tastytrade_readonly_mcp.py`
  (7 passed, plus `tests/test_tastytrade_go_quote_capture.py`, 5 passed).
- The broker OAuth environment is not set in the user's Windows environment, so today's
  snapshot came from the Claude session's read-only tastytrade connection: 102 of 115 ETFs.
  13 inverse/leveraged products fail inside the tastytrade MCP server's output schema.
- The holdings method was corrected test-first. End-of-window issuer weights overstated SPY's
  20-session move by ~0.9 pp, so weights are now drifted back to the window start. A holding
  whose last price is older than the session counts as unpriced.
