# AVS-SD-MI-001 — US Money Index as a governed advisory sidecar in the macro layer

**Date:** 2026-09-06 · **Status:** design for decision, not build authorisation · **Owner:** ACK
**Depends on:** AVS-THS-002 (regime routes, never gates), AVS-SD-002 §7 authority matrix, AR-003 §6.3 field states, AVS-FIX-001 Level 1 (this is a Level 2 / W3.10 item)
**Decision requested:** approve the sidecar pattern (§2), the schema (§3) and the consumer list (§5); reject the "replace the catalyst CSV" framing (§1).

---

## 1. Where the macro layer actually reads from today — and why "replace the catalyst CSV" is the wrong slot

| File | Location | Producer | Consumers | Authority today |
|---|---|---|---|---|
| `macro_intelligence_latest.json` | `dropbox\macro\` | `build_macro_json.py` (Colab CSVs → three `claude-sonnet-4-6` calls → `macro_contract_v1_0`) | `intelligent_orchestrator.py` preflight (`:1076` verifies required fields), `scripts\normalise_macro_contract.py`, `scripts\macro_quant_packet.py` (derives VIX/GEX/rates/USD impulses, freshness), `scripts\inject_macro_into_packages.py` (writes `pkg["macro"]["payload"]` and `pkg["regime_snapshot"]` — **Vanguard fails closed if `regime_snapshot` is absent**), Horizon Router (advisory only since P0-03), Lab `macro_*` columns, Interpreter | advisory; `horizon_routing.block_conditions` / `size_multiplier` are legacy fields the router no longer obeys |
| `bond_macro_state.json` | `dropbox\macro\` | `bond_macro_intelligence.py` | Morning Gate CHECK 4, advisory | advisory sidecar — **the precedent for what you want** |
| `avshunter_macro_enrichment_delta.json` | `dropbox\macro\` | GPT enrichment | Options macro delta (stamped zero) | advisory |
| `catalyst_calendar_latest.csv` | **`dropbox\inputs\`** | manual / GPT intake | `catalyst_truth_engine.py` at three stages (pre-Options, post-Options, pre-Morning); ticker-level: source, date/window, direction, route, risk | advisory; overlay "no longer required" per E2E-001 §3 |

Two consequences. First, the Money Index is a **market-level** state (rates, USD, oil, breadth, GEX, credit, flows, sector flow); the catalyst CSV is **ticker-level** event data. They answer different questions and are read by different stages. Second, `macro_intelligence_latest.json` cannot simply be replaced either: its required-field contract feeds the `regime_snapshot` gate that Vanguard fails closed on, and its `sector_rotation.sector_bias_map` is what the Lab's sector alignment reads. The safe slot is a **third file** beside it.

**Recommendation:** `dropbox\macro\us_money_index_latest.json`, sidecar pattern, optional (absence = `UNAVAILABLE`, never an abort), advisory authority stamped in the file itself. Leave `catalyst_calendar_latest.csv` untouched; if the catalyst overlay is truly retired, that is a separate retirement with its own reference scan.

---

## 2. Design principles (from THS-002, made concrete)

1. **Advisory only, by construction.** The file carries `authority: ADVISORY_ONLY` and every consumer asserts it. No field it contains may be read by Discovery membership, direction governance, contract selection, `capital_permission` or `final_action`. A test enforces that the executed path's authority writers do not import the sidecar.
2. **Computed where it can be, narrated only where it must be.** Every metric in §3 that can be derived from data the pipeline already holds (`historical_prices.sqlite`, FRED via `build_macro_json`, the option-chain store) is a *computed* field with a source and an observed-at timestamp. Narrative states (`US_CAPITAL_MAGNET = INTACT_NARROW`) are allowed but labelled `narrative: true` and never used in arithmetic.
3. **No new vocabulary where one exists.** `vol_mode`, `risk_on_off_switch`, `liquidity_pulse`, `regime_state` stay in `macro_intelligence_latest.json`. The sidecar adds only what those do not carry (breadth, sector flow divergence, gamma position, credit, the scenario tree, per-sector routing) and references the macro packet it was built alongside.
4. **Freshness is per-metric, not per-file.** Friday's close is authoritative for prices; Sunday's OPEC+ decision is fresh; GEX is `STALE_WEEKEND`. Each metric carries its own `as_of` and the packet computes `freshness` per metric via `macro_quant_packet.py`'s existing `_freshness_status`.
5. **Scenarios are testable predicates, not prose.** "SPX > 7,721 and VIX contained and SMH leads" is written as a machine-checkable condition set that Morning Gate evaluates against live data and reports `SCENARIO_A/B/C/UNRESOLVED` — a *context* field, never a permission.
6. **Lineage.** `packet_id`, `packet_sha256`, `source_fingerprint`, `built_by` (chat / script / human), `macro_packet_ref` (the `macro_intelligence_latest.json` it accompanies) — the same identity fields the Lab now carries for macro (`macro_packet_id`, `macro_packet_sha256`, 294/294 since IMP-003).

---

## 3. Schema — `us_money_index_v1_0` (draft, populated from the 6 Sep assessment)

```json
{
  "contract_version": "us_money_index_v1_0",
  "authority": "ADVISORY_ONLY",
  "packet_id": "usmi_20260906T1500Z",
  "packet_sha256": "<computed on write>",
  "built_by": "CHAT_ASSESSMENT",
  "built_at_utc": "2026-09-06T15:00:00Z",
  "market_as_of_session": "2026-09-04",
  "macro_packet_ref": "<macro_intelligence_latest.json packet_id it accompanies>",
  "next_session": "2026-09-08",
  "session_note": "US cash and options markets closed Mon 2026-09-07 (Labor Day); Friday close is the last authoritative print.",

  "state": {
    "us_money_index_state":  {"value": "SELECTIVE_US_CAPITAL_CONCENTRATION", "narrative": true},
    "us_capital_magnet":     {"value": "INTACT_NARROW",                      "narrative": true},
    "fed_impulse":           {"value": "HAWKISH",     "narrative": false, "basis": "sep_hike_prob_pct"},
    "rates_impulse":         {"value": "RESTRICTIVE", "narrative": false, "basis": "2y_10y_change_bp"},
    "usd_impulse":           {"value": "TIGHTENING",  "narrative": false, "basis": "dxy_change_pct"},
    "oil_risk":              {"value": "ELEVATED_EVENT_DEPENDENT", "narrative": true},
    "breadth":               {"value": "NEGATIVE",    "narrative": false, "basis": "spx_adv_dec"},
    "ai_hardware_flow":      {"value": "STRONG_POSITIVE", "narrative": false, "basis": "smh_vs_igv_1d"},
    "software_flow":         {"value": "NEGATIVE",    "narrative": false, "basis": "smh_vs_igv_1d"},
    "small_cap_confirmation":{"value": "SURPRISINGLY_RESILIENT", "narrative": true},
    "credit_stress":         {"value": "LOW",  "narrative": false, "basis": "hy_oas_pct"},
    "vix_stress":            {"value": "LOW",  "narrative": false, "basis": "vix_spot"},
    "spx_gex":               {"value": "POSITIVE_AGGREGATE", "narrative": false, "basis": "net_gex_bn_per_1pct"},
    "gamma_position":        {"value": "AT_FLIP_BOUNDARY", "narrative": false, "basis": "spx_close_vs_zero_gamma"},
    "dealer_regime":         {"value": "TRANSITIONAL", "narrative": true}
  },

  "metrics": {
    "spx_close":              {"value": 7718.6,  "unit": "index",  "as_of": "2026-09-04T20:00:00Z", "source": "<name>", "freshness": "EOD_CURRENT"},
    "spx_change_pct":         {"value": -0.38,   "unit": "pct",    "as_of": "2026-09-04T20:00:00Z", "source": "<name>"},
    "ndx_change_pct":         {"value": 0.21,    "unit": "pct",    "as_of": "2026-09-04T20:00:00Z", "source": "<name>"},
    "rut_change_pct":         {"value": 0.28,    "unit": "pct",    "as_of": "2026-09-04T20:00:00Z", "source": "<name>"},
    "spx_advancers":          {"value": 177,     "unit": "count",  "as_of": "2026-09-04T20:00:00Z", "source": "<name>"},
    "spx_decliners":          {"value": 322,     "unit": "count",  "as_of": "2026-09-04T20:00:00Z", "source": "<name>"},
    "smh_change_pct":         {"value": 2.61,    "unit": "pct",    "as_of": "2026-09-04T20:00:00Z", "source": "<name>"},
    "igv_change_pct":         {"value": -2.23,   "unit": "pct",    "as_of": "2026-09-04T20:00:00Z", "source": "<name>"},
    "ust_2y_pct":             {"value": 4.37,    "unit": "pct",    "change_bp": 3,  "as_of": "2026-09-04T21:00:00Z", "source": "<name>"},
    "ust_10y_pct":            {"value": 4.78,    "unit": "pct",    "change_bp": 1,  "as_of": "2026-09-04T21:00:00Z", "source": "<name>"},
    "ust_30y_pct":            {"value": 5.24,    "unit": "pct",    "change_bp": -1, "as_of": "2026-09-04T21:00:00Z", "source": "<name>"},
    "curve_2s10s_bp":         {"value": 41,      "unit": "bp",     "change_bp": -2, "as_of": "2026-09-04T21:00:00Z", "source": "<name>"},
    "dxy":                    {"value": 99.16,   "unit": "index",  "change_pct": 0.25, "as_of": "2026-09-04T21:00:00Z", "source": "<name>"},
    "vix_spot":               {"value": 14.53,   "unit": "index",  "as_of": "2026-09-04T20:15:00Z", "source": "<name>"},
    "wti_usd":                {"value": 91.18,   "unit": "usd_bbl","as_of": "2026-09-04T19:30:00Z", "source": "<name>"},
    "hy_oas_pct":             {"value": 2.65,    "unit": "pct",    "as_of": "2026-09-03T00:00:00Z", "source": "<name>", "freshness": "STALE_1D"},
    "sep_fomc_hold_prob_pct": {"value": 41.6,    "unit": "pct",    "as_of": "2026-09-04T21:00:00Z", "source": "<name>"},
    "sep_fomc_hike_prob_pct": {"value": 58.4,    "unit": "pct",    "as_of": "2026-09-04T21:00:00Z", "source": "<name>", "prior": 50.4},
    "spx_zero_gamma":         {"value": 7721,    "unit": "index",  "as_of": "2026-09-04T20:00:00Z", "source": "<name>", "freshness": "STALE_WEEKEND"},
    "spx_net_gex_bn_per_1pct":{"value": 3.66,    "unit": "usd_bn", "as_of": "2026-09-04T20:00:00Z", "source": "<name>", "freshness": "STALE_WEEKEND"},
    "spx_call_wall":          {"value": 7700,    "unit": "index",  "as_of": "2026-09-04T20:00:00Z", "source": "<name>", "freshness": "STALE_WEEKEND"},
    "spx_put_wall":           {"value": 7700,    "unit": "index",  "as_of": "2026-09-04T20:00:00Z", "source": "<name>", "freshness": "STALE_WEEKEND"},
    "us_equity_fund_flow_usd_bn":  {"value": -11.1, "unit": "usd_bn", "window": "latest_week", "source": "<name>"},
    "money_market_flow_usd_bn":    {"value": 49.0,  "unit": "usd_bn", "window": "latest_week", "source": "<name>"}
  },

  "events": [
    {"date": "2026-09-06", "type": "OPEC_PLUS_DECISION", "summary": "October output policy unchanged", "source": "<url>", "regime_effect": "OIL_RISK_PREMIUM_SUSTAINED"},
    {"date": "2026-09-05", "type": "GEOPOLITICAL", "summary": "US strikes Iranian tankers; Hormuz clashes", "source": "<url>", "regime_effect": "OIL_RISK_EVENT_DEPENDENT"}
  ],

  "sector_routing": {
    "note": "Advisory ordering only. Maps to Lab regime_alignment column. Cannot admit, drop, direct or authorise.",
    "CALL": {
      "SEMICONDUCTORS":        {"alignment": "ALIGNED",  "priority": 1, "requires": ["ADVERSE_REGIME_RS_POSITIVE"], "reason": "AI hardware absorbing higher yields/USD/negative breadth"},
      "ENERGY":                {"alignment": "ALIGNED",  "priority": 2, "requires": ["CRUDE_CONFIRMS"]},
      "SMALL_CAP_RS":          {"alignment": "NEUTRAL",  "priority": 3, "requires": ["ADVERSE_REGIME_RS_POSITIVE"]},
      "SOFTWARE":              {"alignment": "ADVERSE",  "priority": 9},
      "BROAD_INDEX":           {"alignment": "PENDING_REOPEN", "requires": ["SCENARIO_A"]}
    },
    "PUT": {
      "SOFTWARE":              {"alignment": "ALIGNED",  "priority": 1, "requires": ["RELATIVE_WEAKNESS_CONFIRMED"]},
      "RATE_SENSITIVE_REITS":  {"alignment": "ALIGNED",  "priority": 2},
      "HOUSING":               {"alignment": "ALIGNED",  "priority": 3},
      "CONSUMER_DISCRETIONARY_WEAK": {"alignment": "ALIGNED", "priority": 4},
      "TRANSPORT_TRAVEL":      {"alignment": "NEUTRAL",  "priority": 5, "requires": ["OIL_ACCELERATES"]},
      "BROAD_INDEX":           {"alignment": "PENDING_REOPEN", "requires": ["SCENARIO_C"]}
    }
  },

  "scenarios": {
    "evaluate_at": "MORNING_GATE",
    "A_CAPITAL_MAGNET_CONFIRMED": {"all": [{"spx_gt": 7721}, {"vix_lt": 18}, {"hy_oas_lt": 3.0}, {"smh_rel_ndx_gt": 0}, {"spx_breadth_ratio_gt": 1.0}]},
    "B_SELECTIVE_CONCENTRATION":  {"all": [{"spx_abs_dist_zero_gamma_lt_pct": 0.5}, {"spx_breadth_ratio_lt": 1.0}, {"smh_rel_igv_gt": 0}, {"vix_lt": 18}, {"hy_oas_lt": 3.0}]},
    "C_RISK_OFF_TRANSITION":      {"all": [{"spx_lt": 7700}, {"vix_change_gt": 0}, {"spx_breadth_ratio_lt": 1.0}, {"ust_10y_change_bp_gt": 0}, {"dxy_change_gt": 0}, {"hy_oas_change_gt": 0}]},
    "default": "UNRESOLVED"
  },

  "tier1_search_mode": {"value": "CAPITAL_CONCENTRATION + RELATIVE_STRENGTH_DIVERGENCE", "narrative": true},

  "computed_by_pipeline": {
    "note": "Filled by macro_quant_packet.py on ingest; not supplied by the author.",
    "shock_states": {},
    "ars_reference_windows": [5, 10],
    "freshness_summary": {}
  }
}
```

Fields the author must not supply: anything under `computed_by_pipeline`, and `packet_sha256`. Fields the author should always supply: every metric's `source` and `as_of` — a metric without both is loaded as `UNAVAILABLE`, not as a number.

---

## 4. What changes in the pipeline

| # | Change | File(s) | Size | Notes |
|---|---|---|---|---|
| C1 | **Contract module**: `contracts\us_money_index_contract.py` — enums for every `state` value above, the `sector_routing.alignment` set (`ALIGNED / NEUTRAL / ADVERSE / PENDING_REOPEN`), scenario predicate keys, `freshness` values reused from `macro_quant_packet` | new | S | prevents alias drift; all readers import from here |
| C2 | **Validator**: `scripts\validate_us_money_index.py` (pattern: `validate_macro_contract.py`) — schema, required per-metric `source`/`as_of`, authority literal, no numeric under `narrative: true`, scenario predicates well-formed; computes `packet_sha256` | new | S | run by orchestrator preflight; failure ⇒ sidecar `UNAVAILABLE`, run continues |
| C3 | **Ingest**: `macro_quant_packet.py` reads the sidecar if present; computes per-metric freshness; computes `shock_states` via the AVS-SD-002 §9.4 robust-z on `wti_usd`, `ust_10y_pct`, `dxy`, `vix_spot` against the last 60 sessions from canonical data; writes the packet under `macro_quant_packet["us_money_index"]` with identity fields | modify | M | the one place narrative becomes computed |
| C4 | **Injection**: `inject_macro_into_packages.py` carries the sidecar packet into `pkg["macro"]["us_money_index"]`; **does not touch `regime_snapshot`** (Vanguard's fail-closed gate stays keyed to the existing contract) | modify | S | absence must be harmless |
| C5 | **Lab columns**: `regime_alignment`, `regime_alignment_priority`, `regime_alignment_reason`, `usmi_packet_id`, `usmi_packet_sha256`, `usmi_scenario` (Morning only) — allow-listed **and mapped** in `contracts\lab_control.py` (the F29 lesson) | modify | S | sort within tier only |
| C6 | **Adverse-Regime RS**: `ars`, `ars_z`, `ars_window`, `ars_peer` computed from `historical_prices.sqlite` per THS-002 §5, published on Vanguard rows and carried to the Lab; the sidecar's `requires: ["ADVERSE_REGIME_RS_POSITIVE"]` reads `ars_z > 0` | new module `market_structure\adverse_regime_rs.py` | M | computed, lineaged; no threshold grants a tier |
| C7 | **Morning Gate context**: evaluate `scenarios` against live SPX/VIX/breadth/10Y/DXY/HY OAS where the pipeline has them; where it does not (breadth, HY OAS) the predicate resolves `UNAVAILABLE` and the scenario `UNRESOLVED`; write `usmi_scenario` to the Morning book | modify `morning_gate.py` | M | context column; **no CHECK reads it** |
| C8 | **Tier ordering** (after AVS-FIX-001 W3.5 exists): `regime_alignment` orders rows within Tier 1/2/3; `ADVERSE` with `ars_z ≤ 0` adds `tier_reason = REGIME_ADVERSE_RS_UNCONFIRMED` and places the row in Tier 2 at best | modify `contracts\opportunity_tier.py` | S | placement within/between Tier 1–2 only; never to/from ARMED/BLOCK |
| C9 | **Sector taxonomy bridge**: map the sidecar's sector keys (`SEMICONDUCTORS`, `SOFTWARE`, `ENERGY`, …) to the universe scanner's GICS/sector field; unmapped ⇒ `regime_alignment = NEUTRAL` with reason `SECTOR_UNMAPPED` | new table in C1 | S | required before any routing is trusted |
| C10 | **Authority tests**: (a) `final_action`, `capital_permission`, direction, selected contract identical with and without the sidecar on a production-shaped fixture; (b) Discovery output byte-identical with and without it (P0-03 regression); (c) a sidecar with an injected `final_action` key is rejected by the validator; (d) missing sidecar ⇒ run proceeds, columns `UNAVAILABLE` | new tests | M | the same shape as the macro-invariance tests |
| C11 | **Semantic audit rule**: `USMI_AUTHORITY_LEAK` — any row where `regime_alignment` is populated but `usmi_packet_sha256` is absent, or where a tier moved to/from ARMED/BLOCK on regime alone | `handoff_contract_audit.py` | S | keeps the router honest |
| C12 | **Producer**: a `build_us_money_index.py` in the `build_macro_json.py` pattern — takes the chat assessment (or a structured form) and the source URLs, emits the JSON, runs C2. Until it exists, the file is authored by hand and validated by C2 | new | M | optional for the first cycle |
| C13 | **Docs**: `docs\US_MONEY_INDEX_SIDECAR.md` — field dictionary, what may and may not read it, freshness rules; add to the authority matrix in AVS-SD-002 §7 as "US Money Index — advisory structural context — prohibited: membership, direction, capital" | new | S | — |

**Explicitly not changed:** `macro_intelligence_latest.json` and its contract; `regime_snapshot`; the catalyst CSV and Catalyst Truth engine; Discovery; direction governance; `select_best_contract`; Execution Gate; `MACRO_DIRECTION_SIZING` (already stamped default 0.75/0.75 and advisory — leave it; a separate item retires it).

---

## 5. Consumer map — who may read it

| Stage | Reads | May do | May not do |
|---|---|---|---|
| Preflight | validator result | mark sidecar `AVAILABLE`/`UNAVAILABLE` | abort the run |
| `macro_quant_packet` | whole file | compute freshness, shock states, identity | invent missing metrics |
| Discovery | **nothing** | — | — (P0-03) |
| Vanguard | `ars_z` inputs (prices only) | publish `ars_*` columns | change verdict, readiness, uplift |
| Options / contract selection | **nothing** | — | — |
| EOD candidate engine | `regime_alignment` | write it to the row | change status or capital permission |
| Morning Gate | `scenarios` | write `usmi_scenario` | feed any CHECK |
| Execution Gate | **nothing** | — | — |
| Lab | all advisory columns | order within tier; show provenance and freshness | upgrade any row |
| Interpreter | packet via handoff | explain regime vs thesis | fetch, direct, select, authorise |
| Decision/Outcome Ledger | `usmi_packet_id`, `regime_alignment`, `ars_z` at decision time | record for calibration | — |

---

## 6. Impact assessment

**On correctness of the current book:** none if built as specified — every consumer is advisory and the authority tests in C10 prove `final_action` is invariant to the sidecar. The risk is entirely in *presentation*: a trader reading `regime_alignment = ALIGNED, priority 1` beside a `MONETISABLE` semiconductor row may weight it more than its lineage justifies. Mitigation: the Lab shows `built_by: CHAT_ASSESSMENT` and per-metric freshness next to the alignment, and THS-002 §5's `ars_z` is the *computed* counterpart the trader should read first.

**On the funnel:** zero. The sidecar cannot recover a single one of the 727 spread-lost tickers or the 43 mis-selections; those are W3.1/W3.2. What it changes is the *order* of the 232 survivors. RCA-003's funnel should be sector-split (THS-002 §6.1) before the routing is trusted — if semiconductors are spread-dead in-band, `priority 1` routes to nothing.

**On the Morning path:** the scenario evaluation is the first machine-checkable form of the Money Index's own "critical decision tree". Tuesday's Morning run will resolve `A/B/C/UNRESOLVED` from live SPX, VIX and 10Y; breadth and HY OAS are not currently fetched by the pipeline, so on day one the predicates that need them resolve `UNAVAILABLE` and scenario A cannot fully confirm. That is honest; adding those two feeds is a later item.

**On provenance:** the pipeline would now consume two LLM-authored macro documents (`macro_intelligence_latest.json` via three Claude calls; the Money Index via a chat assessment). Both are advisory, but the Money Index carries numeric metrics from unnamed third-party sources (the SPX GEX snapshot, fund flows). C2's rule — no `source`, no number — is what keeps that from becoming "a neutral score that looks observed" (AR-003 §6.3).

**On freshness:** the file will routinely be built on a weekend from Friday prices plus weekend news. Per-metric `as_of` and the `STALE_WEEKEND` tag on GEX are what make that safe; a single file-level timestamp would misrepresent everything in it.

**On the catalyst CSV:** unaffected. If ACK wants the catalyst overlay retired, that is a reference scan of `catalyst_truth_engine` call sites and its three orchestrator stages, plus a Lab column review — a separate, small AVS-OPS item.

**On sequencing:** this is Level 2 (AVS-FIX-001 W3.10). It should not be built before Monday's run and Tuesday's Morning have closed Level 1; C6 (`ars_z`) and C5 (columns) are the first slices and could follow W3.5 (tier field) in the week of 14 September. Nothing here affects the MVP trading boundary.

---

## 7. Decision for ACK

1. Approve the **sidecar** slot (`dropbox\macro\us_money_index_latest.json`) and reject "replace the catalyst CSV". ☐
2. Approve the schema in §3 as `us_money_index_v1_0`, with the rule that every metric carries `source` and `as_of` or loads as `UNAVAILABLE`. ☐
3. Approve the consumer map in §5 — in particular that Discovery, direction, contract selection and Execution Gate read nothing from it. ☐
4. Confirm the `sector_routing` keys map to the scanner's sector field (C9) before any alignment is shown in the Lab. ☐
5. Sequence: after Level 1; first slices C1, C2, C6, C5; then C7 for the Morning path; C12 producer script when the format is stable. ☐
