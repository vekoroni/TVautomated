# Item 7 — Option walls: concentration, dealer influence and observed price response (D5-2 / D5-3, enhanced)

Status: design for build (ACK 10 Oct 2026: "implement item 7", with ACK's call-wall review). Supersedes the D5-2 fix
text in OUTPUT_TRUST_FIX_DESIGN_20261009.md (fixed buckets <=7 / 8-45 / 46-110 days and a +/-30% band).

## Root cause (confirmed on data, not assumed)

`scripts/avshunter_options_intelligence.compute_oi_walls` takes the largest raw open interest on each side of spot,
summed over every expiry in the fetched chain (1-110 days), with no gamma weighting, no relevance rule and no
materiality test. SMCI 8 Oct (spot 42.77): put wall 3.0 = `SMCI270115P00003000`, a standard-root 15 Jan 2027 put with
58,551 OI and gamma 0.0001 - the largest put OI in the chain, almost no hedging relevance. On the same chain the
gamma-weighted measure finds a 40-42.5 put zone and a 43.5-45 call zone through a ~21-session exit, and 50 calls /
40, 35 puts after it. The chain also carries no contract multiplier (column empty), which must be stated, not assumed
silently.

## Principle (ACK review): three separate conclusions, never merged

| Conclusion | What it means | AVSHUNTER field family |
|---|---|---|
| Options concentration | Many outstanding contracts / material gamma-weighted exposure at a strike or zone | `wall_*` (unsigned) |
| Estimated dealer influence | A positioning model suggests hedging could matter there | `gamma_flip`, `gex_*` (sign is an assumption, labelled) |
| Observed support / resistance | Price action shows buying or selling around the level | `wall_*_price_status` |

A concentration never establishes support, resistance or direction by itself. Definition used throughout:
**a wall candidate is a material concentration of gamma-weighted open interest within one instrument, one expiry
basket and a relevant price region; its support or resistance role is unverified until price behaviour supports it.**
This is our own method, named `GAMMA_OI_CONCENTRATION_V1` - never presented as a provider's (e.g. SpotGamma) wall.

## 1. Instrument and contract validity (before any calculation)

- The chain's underlying root equals the ticker; other roots (adjusted / non-standard deliverables, e.g. `SMCI1`) are
  excluded and counted (`wall_excluded_contracts`, reason). QQQ walls come from QQQ options; NDX, SPX are never mixed
  in - an index view would be separate context with its own label.
- Contract multiplier: provider value when present; when absent, 100 for a standard root, labelled
  `MULTIPLIER_ASSUMED_100_NOT_PROVIDED`. Gamma units: per share per $1 move (MarketData), so the multiplier is applied
  once.
- Timestamps carried: underlying price as-of, quote / greeks as-of (`quote_timestamp_utc`), and the open-interest
  clearing date (prior completed session; OI is not updated intraday, so today's volume is never added to it).

## 2. Expiry baskets by actual dates (not a fixed day count)

| Basket | Contents | Purpose |
|---|---|---|
| `TODAY` | expiring this session | immediate intraday positioning |
| `THROUGH_EXIT` | after today through the planned exit date (planned hold in XNYS sessions -> date) | positioning that may change or vanish during the hold |
| `AFTER_EXIT` | after the exit date through the governed longer cutoff (config, 110 calendar days = the chain fetched) | positioning that survives the trade |
| `COMBINED` | all of the above, with each basket's share disclosed | broader context |

A wall that expires before the exit is never presented as support for the whole hold. No planned hold -> the exit
basket is stated as unavailable (`NO_PLANNED_EXIT`), not guessed.

## 3. Measure: gamma-weighted open interest, unsigned, per side

Per strike K and basket: `call_conc(K) = sum gamma_call * OI_call * M`, `put_conc(K) = sum gamma_put * OI_put * M`;
dollar-gamma scale for a 1% move: x S^2 x 0.01 (`wall_*_dollar_gamma_1pct`). Unsigned: long calls and long puts both
carry positive gamma; no dealer sign is implied.

## 4. Selection: material, relevant zones - never forced

- Calls: concentrations above spot; puts: below spot; plus the largest concentration within the near-spot band on
  either side (labelled NEAR_SPOT, not support or resistance).
- Zones: adjacent strikes within a governed width (config, in strike steps) merge into a zone (low, high, peak strike,
  share of the side's basket total).
- Material: zone share of the side's basket total >= governed threshold (config); otherwise `NO_QUALIFIED_WALL`.
- Relevant: within the basket's expected-move band `k x IV x sqrt(sessions to the basket's end / 252)` around spot
  (config k; IV = the ticker's ATM IV, labelled) - replacing the +/-30% rule; outside it -> `OUTSIDE_RELEVANT_RANGE`.
- The full ranked map (top N zones per side and basket) is kept as JSON for the drawer.
- A call concentration below spot is never labelled overhead resistance (it is a concentration below spot).
- Spot used and its time are recorded; the Morning can recompute with its own spot (gamma moves with spot) - recorded
  as the next step, not done in this build.

## 5. Estimated dealer influence (D5-3) - separate and labelled

`gamma_flip` keeps its method; it is shown with `gamma_flip_conf` and `gamma_flip_state`: below a governed confidence
the state is `LOW_CONFIDENCE` (shown as indicative, not used as a level). The dealer sign convention (calls +, puts -)
is published as `dealer_sign_assumption` = `ASSUMED_CUSTOMER_LONG_PUTS_SHORT_CALLS_UNVERIFIED`. Never "large put
concentration = dealers will buy = support".

## 6. Observed price response (the "Soul of the Chart" questions)

For each qualified zone, from completed daily bars (intraday later), measured with a tolerance of a governed fraction
of ATR(14):

| Price evidence | Status |
|---|---|
| no touch of the zone in the lookback | `UNTESTED_CONCENTRATION` |
| touches that closed back on the original side (rejections), with the trend of rejection strength (wick size) | `OBSERVED_RESISTANCE` / `OBSERVED_SUPPORT` (+ `_WEAKENING` / `_STRENGTHENING`) |
| closes beyond the zone, retest not yet seen | `BREACHED_ACCEPTANCE_ASSESSING` |
| breach, retest that held on the new side, follow-through | `CONTINUATION_SUPPORTED` |
| breach, then a close back inside and failure to recover | `FAILED_BREAK_ASSESSING` |
| touches on high relative volume with little net progress | `ABSORPTION_POSSIBLE` flag beside the status |

Crossing a level is never read as the positions being closed. Reuses the thesis engine's level-event logic where it
fits (break accepted / retest held / retest failed) rather than a second detector.

## 7. Display chain (card and drawer)

Instrument -> strike or zone -> expiry basket -> concentration method -> data timestamps -> dealer-sign assumption ->
observed price response -> current status. Example: "SMCI · put zone 40-42.5 (peak 41) · through 6 Nov · gamma x OI,
12% of basket · chain 8 Oct close, OI 7 Oct · dealer sign not estimated · touched twice, both rejected · observed
support".

## 8. Readers (decision for ACK before this part is switched)

Today `call_wall` / `put_wall` feed the Wall-Break scorer, the exit-plan T1 target, the OIS +/-5 points and the
SuperBrain runway veto. Recommended: these fields become the THROUGH_EXIT basket's qualified zone peak (hold-matched;
missing when none qualifies, with its state), and readers that treat a wall as a price level (exit T1, runway veto)
use it as a level only when its price status is OBSERVED_SUPPORT / OBSERVED_RESISTANCE; otherwise it is shown as an
unverified concentration. Built behind this decision; display and data first.

## Tests

SMCI fixture from the stored 8 Oct chain: no $3 put; zones as above; multiplier assumption labelled; adjusted root
excluded; a wall expiring before exit not in THROUGH_EXIT; NO_QUALIFIED_WALL when nothing is material; a call
concentration below spot never "resistance"; price statuses on synthetic bars for each row of section 6; the display
chain on the card.
