# Intelligence Lab QA Audit — Run `20260731_083130`

**Auditor role:** read-only QA. No source files were modified during this audit.
**Export under audit:** `pipeline_interpreter/MA_Inputs/lab_export/avshunter_signals_20260731_083130_2026-07-31_1640.csv` (96 rows)

---

## Verdict

**Not yet.** Two findings (F1, F2) trace to a single root cause in `intelligence_lab.py` that silently collapses non-directional (STRANGLE) setups into a single-leg CALL/PUT label while leaving the paired R:R and target numbers computed under the strangle framing — this corrupts 43 of 96 rows (45%), including 19 live `GO` verdicts, with a directionally-nonsensical structural target or a silently zeroed R:R. Separately, the `Vetoes_Count` safety field exports as blank instead of `0` due to a JavaScript falsy-zero bug, and `Priority_Rank` fuses two different upstream fields (verdict OR execution permission) without exposing that fusion, so the visible `Verdict` column does not explain the visible rank. Until the STRANGLE-collapse defect and the `Vetoes_Count` export bug are fixed, this export should not be treated as ground truth for automated downstream consumption (confidence: 90%).

---

## A note on reproducibility

Both `intelligence-lab/intelligence_lab.py` and `intelligence-lab/static/index.html` had pre-existing **uncommitted** changes in the working tree before this audit began (`git status` showed them modified; I did not create these edits and did not revert them, per the read-only rule). Separately, when I re-ran the Lab's merge logic live against the same run folder to trace field provenance, several fields that are **100% null in the audited CSV** (`Horizon_Action`, `Horizon_Source`, `Trigger_Price`, `Trigger_Primary/Quality/Codes`) came back **populated** in today's live run. This means the on-disk run-folder artifacts and/or Lab code changed after the 2026-07-31 16:40 export was generated, without a new run_id — the exact reproducibility failure mode the background section warned about (April 2026 field-mismatch incident). Where this affects a finding, I have flagged the confidence accordingly and treated the audited CSV, not my live re-derivation, as ground truth.

---

## F1 — R:R is zero for CALL setups where it is computable and positive

**Location:** `intelligence-lab/intelligence_lab.py:1262-1292` (`_normalise_direction_value`) and `:1358-1382` (`_sync_lab_display_fields`), consumed at `intelligence-lab/static/index.html:2014` (`['RR', s => parseFloat(s.rr||0).toFixed(4)]`).

**Mechanism:** `RR` is not computed in the Lab — it is a straight pass-through of the upstream `rr_options` field (`intelligence_lab.py:1493`, `sig.setdefault("rr", sig.get("rr_options",""))`), itself produced in Phase 7 (`scripts/avshunter_options_intelligence.py`). I cross-referenced all 96 exported rows against `eil_enriched_20260731_083130.csv`'s `options_direction` field:

| | RR computable & zero | RR computable & >0 |
|---|---|---|
| Rows with `options_direction == STRANGLE` | **14 / 14** | **0 / 32** |
| Rows with `options_direction` = CALL/PUT | 0 | 32 |

This is a perfect split — every one of the 14 zeroed, computable-CALL rows is a STRANGLE at the upstream layer, and no STRANGLE row anywhere has RR > 0. The one PUT-side anomaly the task also flagged (`RR==0` among computable PUTs) is the same STRANGLE tag.

Root cause: `_normalise_direction_value` (`intelligence_lab.py:1262-1292`) walks a priority list of direction-indicating fields to pick one canonical `CALL`/`PUT` for display. `options_direction` is checked at line 1275 and correctly resolves `STRANGLE` to `""` (not a side) via `_side_from_value` (line 1236, which explicitly excludes `"STRANGLE"`). But the loop does not stop there — it falls through to `options_strategy` (line 1280, e.g. `"LONG_PUT"` or `"LONG_CALL"`, the single leg Phase 7 chose to display/journal), and `_side_from_value("LONG_PUT")` returns `"PUT"` because the string contains `"PUT"`. `_sync_lab_display_fields` then commits this at line 1363: `sig["direction"] = canonical`, overwriting the row's authoritative direction with a single leg — while `rr_options`/`structural_target` remain whatever Phase 7 computed under the two-sided strangle framing (verified: `target_in_play` for these rows is computed against the wall on the side that ended up hidden, not the displayed leg).

**Classification:** Defect. The code path correctly identifies "this isn't directional" (returns `""` for STRANGLE) and then discards that finding by continuing down the fallback chain instead of treating `""` as "no coherent direction — flag, don't collapse."

**Consequence for a trader:** A structurally sound, computable-positive R:R is displayed as `0.000`, indistinguishable from "no edge." A trader filtering on `R:R > 0` (a filter button exists in the UI for exactly this) will silently discard the same 14 rows the export made look worthless.

**Fix recommendation (not implemented):** In `_normalise_direction_value`, when the first CALL/PUT-capable signal in priority order (`options_direction`, `opt__options_direction`) explicitly resolves to `""` because it is `STRANGLE`, stop and mark the row `lab_coherence_status = "STRANGLE_NONDIRECTIONAL"` rather than continuing to `options_strategy`. Surface `options_direction` itself as an exported column so STRANGLE rows are visibly distinct from single-leg rows, and suppress/relabel `RR` for STRANGLE rows instead of exporting a bare `0.0000`.

**Confidence:** 95% (mechanism traced to file:line, correlation verified against all 96 rows with 100% separation).

---

## F2 — 29 rows have Structural_Target on the losing side of the strike

**Location:** Same root cause as F1 — `intelligence-lab/intelligence_lab.py:1262-1292, 1358-1382`. Exported at `static/index.html:2025` (`['Structural_Target', s => getOpt(s,'structural_target') || '']`).

**Mechanism:** I checked all 29 losing-side rows (per the task's own reconciled formula) against `options_direction` in `eil_enriched_20260731_083130.csv`:

```
total mismatched (losing side): 29
of which options_direction == STRANGLE: 29
non-strangle mismatches: 0
```

100% of the mismatched rows — including the AVGO, FCX, MCD examples given — are STRANGLE setups at the upstream layer whose direction was collapsed to a single leg (`LONG_PUT`) by the exact mechanism described in F1. `T` (the correctly-behaving example) has `options_direction == 'PUT'` — a genuine single-directional setup — which is why its `structural_target` correctly sits below its strike.

**Determination requested by the task ("overloaded field vs. genuine mismatch"):** Neither, precisely. `Structural_Target` is not overloaded — it is a real, coherent value that Phase 7 computed for the strangle as a whole. The defect is that `Direction` (and therefore the reader's frame for interpreting `Structural_Target`) was force-collapsed to one leg by the Lab, after which the two fields no longer describe the same trade.

**Classification:** Defect (same code path as F1).

**Consequence for a trader:** 19 of these 29 rows carry `Verdict = GO`. A trader reading "LONG_PUT, strike $390, target $411.12" for AVGO sees a profit target *above* a put strike — a structurally impossible thesis for a single-leg put — and either (a) loses trust in the whole export, or worse, (b) doesn't notice and enters a put believing the stock will rally to $411.

**Fix recommendation (not implemented):** Same fix as F1 — do not collapse `STRANGLE` to a single leg for display. If a single-leg execution decision must be made downstream of a strangle-classified setup, that decision should be made explicitly and re-derive/re-validate `structural_target` for the chosen leg, not inherit the two-sided value unchanged.

**Confidence:** 95%.

---

## F3 — EV is exported at 4dp and loses its sign

**Location:** `intelligence-lab/static/index.html:2015` (`['EV', s => getEv(s).toFixed(4)]`), `getEv()` defined at `static/index.html:1109-1125`.

**Mechanism:** I pulled the underlying `ev2_ev_conf_adj` (and its aliases `fd_ev_used`, `ev_final`, `ev_net`, `ev`) for all 19 rows exporting `0.0000`/`-0.0000`:

```
FXI  -0.0000 AVOID  ev2_ev_conf_adj = -2.8e-05
IWM  -0.0000 AVOID  ev2_ev_conf_adj = -1.1e-05
VTI  -0.0000 AVOID  ev2_ev_conf_adj = -2.0e-05
DUK  -0.0000 AVOID  ev2_ev_conf_adj = -2.0e-05
PLNT  0.0000 WEAK   ev2_ev_conf_adj =  4.1e-05
... (15 rows total, all magnitude 2.2e-05 to 4.9e-05)
```

Every one of the 4 negative and 15 positive rows has a true magnitude between 1.1×10⁻⁵ and 4.9×10⁻⁵ — an order of magnitude below the resolution `.toFixed(4)` can represent (1×10⁻⁴). Full precision **is** available in memory (`ev2_ev_conf_adj` carries the real float); it is discarded at the point of string formatting, not before. `EV_Decision` (`ev2_decision_hint`) is sourced independently and correctly retains `AVOID` vs `WEAK`.

**Classification:** Defect (export formatting, not a computation error — the decision layer is unaffected).

**Consequence for a trader:** Only a consumer that filters/sorts on the numeric `EV` column rather than the categorical `EV_Decision` column is affected — but the task background and the Lab UI both expose an `EV > 0` quick-filter button (`static/index.html:337`, `toggleQuick('ev',this)`), which is exactly this failure mode: it would treat 4 genuinely `AVOID` rows as passing.

**Fix recommendation (not implemented):** Export EV at higher precision (e.g. 6dp, or scientific notation below a threshold, as `formatEv()` already does for on-screen display via basis-point conversion at `static/index.html:1150-1157` — that display-only helper is not used by the CSV export and should be).

**Confidence:** 98%.

---

## F4 — 15 of 64 columns are 100% null

**Location:** Export column definitions at `static/index.html:1979-2044`.

Per-field determination (checked against `eil_enriched_20260731_083130.csv`, `options_intelligence_latest.csv`, `vanguard_signals.csv`/`vanguard_signals_enriched_*.csv`, and `morning_validated_trades_20260731_083130.csv`):

| Field | Classification | Evidence |
|---|---|---|
| `Vetoes` / `Vetoes_Count` | **(a) not produced upstream**, compounded by an independent **defect** | `contract_validity` — the sole field these derive from (`intelligence_lab.py:1526-1529`) — is `None` for all 952 rows in today's live universe; it is never written by any upstream phase in this run. Independently, `static/index.html:2030` exports `Vetoes_Count` as `s.sb_vetoes_count || ''` — since JS `0` is falsy, a legitimate `sb_vetoes_count = 0` is exported as an **empty string**, indistinguishable from missing. This is the field the task correctly flags as most dangerous: a downstream `Vetoes_Count == 0` safety check would pass every row, but it would also pass every row even if the upstream defect were fixed and some rows legitimately had 0 vetoes, because the export can't tell "zero" from "absent." |
| `EIL_Verdict` / `EIL_Raw_Verdict` / `EIL_Composite` | **(b) produced, but the Lab reads the wrong field name** | The real columns in `eil_enriched_*.csv` are `eil_raw_verdict` and `eil_composite_score` — single underscore, because EIL is the *base* signal table (bare column names) in the v2.0 architecture per the file's own header comment (`intelligence_lab.py:6-11`). The export instead reads `s['eil__raw_verdict']`, `s['eil__composite_score']`, `s['eil__composite']` (double underscore) — the `eil__` prefix convention used for *secondary, joined* sources (`opt__`, `vg__`, `wbs__`). This is a literal leftover from the pre-v2.0 architecture and never matches. Notably, `intelligence_lab.py:1504` already aliases `sig.setdefault("composite", sig.get("eil_composite_score",""))` — a correctly-named bare fallback exists in `sig` and is simply never checked by the export helper. This is the exact "field name mismatch" pattern called out in the background (`expected_move_10d` vs `l3_expected_move_6_10d`). |
| `MV_Drift_Pct` | **(a) not produced upstream** | `morning_validated_trades_20260731_083130.csv` has no drift-percentage column at all (only categorical `regime_drift_status`). |
| `Days_To_Trigger` | **(a) not produced upstream** | No candidate key (`opt__days_to_trigger`, `days_to_trigger`, `opt__trigger_days`, `trigger_days`) exists anywhere in the merged signal for any of 952 rows in today's universe. |
| `Verdict_Reason` | **(c) read but empty for this handoff slate** | `sb_verdict_reason` is aliased from `sig.get("reason","")` (`intelligence_lab.py:1514`); a live check shows this alias is set but empty for all 952 rows — `reason` itself is not populated in this run's EIL output. |
| `Horizon_Action` / `Horizon_Source` | **Indeterminate — reproducibility gap** | 100% null in the audited CSV, but the same candidate fields (`eod__horizon_action`, `vg__horizon_action`, etc.) are populated in 752/952 rows (79%) when I re-ran the Lab's merge live today. I cannot confirm whether this reflects a real fix already made upstream since 2026-07-31, a since-changed run-folder artifact, or something specific to the 96-row morning-validation handoff subset that differs from the full 1262-row universe. Flagged as **not determined** rather than guessed. |
| `Horizon_Pressure` | Same reproducibility caveat, but notably: live re-derivation shows this field populated for **100%** of rows today (952/952) — the strongest of the horizon fields. | |
| `Trigger_Price` / `Trigger_Primary` / `Trigger_Quality` / `Trigger_Codes` | Same reproducibility caveat as Horizon fields — populated today (100%, 22%, 22%, 22% respectively) but 0% in the audited export. | |
| `WBS_Grade` / `WBS_Score` (78/96 null, not 100%) | **(a) not produced upstream for most tickers** | `wall_break_scores_*.csv` (Phase 8's WBS engine) only covers 65 of 1262 tickers this run by design (docstring: "9 BUY_NOW tickers" historically, 65 scored this run) — most tickers simply have no WBS row to join. This one is intended/expected sparsity, not a defect. |

The Lab's `_read_csv` (`intelligence_lab.py:81-89`) does catch-and-return-`[]` on any read error, which could mask a missing/misnamed file per the background's April-2026 concern — but I confirmed all of the relevant source files (`eil_enriched`, `options_intelligence_latest`, `morning_validated_trades`) load successfully (non-empty) for this run, so that specific masking did not occur here for F4. It remains a latent risk (see Incidental Observations).

**Consequence for a trader:** `Vetoes_Count`'s inability to distinguish "0" from "missing" is the most serious — it removes a safety gate. The `EIL_Verdict`/`EIL_Composite` name-mismatch hides genuinely-available upstream verdict/quality data that the Lab already has in memory under a different key.

**Fix recommendation (not implemented):** Change `eil__raw_verdict`/`eil__composite_score`/`eil__composite` reads to the correct bare names (or the already-existing `composite` alias). Change `Vetoes_Count`'s export to `s.sb_vetoes_count ?? ''` (nullish coalescing, not `||`) so `0` survives. Investigate why `contract_validity` is unpopulated in Phase 7's output (out of scope to fix here, flagged for Phase 7 owner).

**Confidence:** 90% for Vetoes/EIL/MV_Drift/Days_To_Trigger (stable null both historically and live); 40% for Horizon_*/Trigger_Price/Trigger_Primary/Quality/Codes (reproducibility gap prevents a confident historical mechanism).

---

## F5 — Trigger fields look hardcoded (`Trigger_Score = 55.0` on every row)

**Location:** `static/index.html:2011` (`['Trigger_Score', s => firstSignalValue(s, ['trigger_score', 'eod__trigger_score', 'vg__trigger_score', 'opt__trigger_score'])]`).

**Mechanism:** `55.0` is not a literal hardcoded in the Lab's JS or Python (I grepped both; the only literal `55` in `intelligence_lab.py:1523` is an unrelated position-sizing bucket, `sb_position_size_pct`, coincidentally in the same numeric neighborhood but a different field entirely). It is a genuine upstream value: `options_intelligence_latest.csv`'s own `trigger_score` column is **binary** across the whole universe — `709` rows at `0.0`, `553` rows at exactly `55.0` — and `55.0` co-occurs 1:1 with `trigger_state == 'TRIGGER_EARLY_PROBE'` for every ticker I sampled. This looks like a fixed placeholder Phase 7 assigns for one categorical trigger state rather than a computed score, separate from Phase 8.6b's real, continuous `trigger_score` in `eil_enriched.csv` (0.0 / 2.0 / 3.5 / 4.0 / etc. — confirmed present and varied for this run, e.g. via `trigger_layer_summary_20260731_083130.csv`).

Two distinct fields share the name `trigger_score` at different layers, and the export's fallback order lists the real one first. When I re-ran the Lab's merge live today, the higher-priority real field (`trigger_score = 0.0` for ticker T) correctly won and would export as `0.0`, not `55.0` — meaning **today's code, run against today's data, would not reproduce the audited CSV's uniform 55.0.** I could not determine what state produced the historical export: either the real Phase 8.6b trigger layer's output had not yet been merged into `eil_enriched.csv` at export time (in which case the field genuinely fell through to the Phase-7 placeholder), or something about the specific 96-row handoff subset differs from what I tested. `Trigger_Evidence = "TRIGGER 55"` on every row is internally consistent with this: `getTriggerEvidenceDisplay()` (`static/index.html:1493-1518`) builds its label from the same `trigger_score` fallback chain, so whatever field resolved to 55 for `Trigger_Score` also drove `Trigger_Evidence`.

**Classification:** Defect — two upstream concepts collide under one field name, and the fallback chain has no way to prefer "real but zero" over "placeholder but present." I cannot classify this a naming problem alone, because a genuine `0.0` score is informationally different from an untriggered placeholder, and the current chain cannot tell them apart even when both are technically valid non-empty values.

**Consequence for a trader:** Every row appears to carry identical, moderate trigger conviction, destroying the field's use as a differentiator, and potentially masking rows where the real trigger layer scored 0 (no trigger at all) versus 4.0 (strong trigger).

**Fix recommendation (not implemented):** Namespace Phase 7's own `trigger_score` under `opt__trigger_score` only (it already is) and never let it leak into the bare `trigger_score`/`vg__trigger_score` fallback chain that's meant to represent Phase 8.6b's real trigger layer. Confirm at export time whether Phase 8.6b's output was actually joined for the run (`result["run_health"]` already tracks file presence — surface it).

**Confidence:** 55% on the precise historical mechanism (reproducibility gap acknowledged above); 90% that the field-collision itself (two `trigger_score` concepts, one upstream layer's placeholder able to leak into the other's namespace) is real and worth fixing regardless.

---

## F6 — Priority_Rank is not ordered by Priority_Score

**Location:** `intelligence-lab/intelligence_lab.py:811-850` (`_lab_priority_bucket`) and `:852-886` (`_finalise_lab_priority_ranking`). Exported at `static/index.html:2021`.

**Mechanism:** Rank is a global sort by `(lab_action_bucket, -research_priority_score, ticker)` (`intelligence_lab.py:877-884`) — bucket first, score only breaks ties within a bucket. The bucket function (`_lab_priority_bucket`, line 836) grants bucket `0` ("ACTIONABLE", the top rank tier) on an **OR** across two independent fields:

```python
if verdict in {"GO", "GO_LIMIT"} or permission in {"GO", "GO_LIMIT"}:
    return 0, "ACTIONABLE"
```

`verdict` here is the row's thesis-level verdict; `permission` is the *separate* `morning_execution_permission` field. I checked every row the export labels `Verdict = ARMED`:

```
VZ    rank=2   Morning_Permission=GO
FXI   rank=8   Morning_Permission=GO
IWM   rank=9   Morning_Permission=GO
FISV  rank=50  Morning_Permission=GO
XOM   rank=57  Morning_Permission=GO
```

All five — 100% — have `Morning_Permission = GO`, which is exactly the second branch of the OR. Their thesis verdict is genuinely `ARMED` (not yet `GO`), but their independently-granted execution permission pushes them into the same top rank bucket as true `GO` rows, producing the interleaving the task observed (`ARMED` ranks 2-57 overlapping `GO`'s 1-67).

**Classification:** Naming/contract problem, not a raw defect — the ranking logic is internally consistent and arguably a deliberate design choice (permission can independently unlock execution priority even ahead of full verdict promotion). But it is **undocumented in the export**: the single `Verdict` column a trader reads does not disclose that rank also depends on `Morning_Permission`, so the rank order looks arbitrary against the visible column.

**Consequence for a trader:** Sorting/reading by rank while trusting `Verdict` as the explanation for that rank will misread why an `ARMED` row outranks a `CONTRACT_REPAIR` or lower-scored `GO` row.

**Fix recommendation (not implemented):** Export the resolved `lab_action_bucket_label` (already computed server-side at `intelligence_lab.py:863`) as its own column, so the trader can see the actual ranking dimension instead of inferring it from `Verdict`.

**Confidence:** 90%.

---

## F7 — Verdict columns disagree, and several are collinear

**Location:** `static/index.html:1190-1195` (`finalLabVerdict`), `:1197-1211` (`displayCampaign`), `:1288-1312` (`getExecutionCategory`), `intelligence_lab.py:393-406` (`_extract_execution_category`).

**Mechanism, per collinear pair:**
- **`Verdict` / `Lab_Verdict`** — both exported columns call the identical function `finalLabVerdict(s)` (`static/index.html:1982-1983`). This is a literal duplicate column, not a coincidence.
- **`Verdict` / `Campaign`** — `displayCampaign(s)` (`static/index.html:1197-1211`) computes `finalLabVerdict(s)` as its first step, then applies a fixed one-to-one lookup table (`GO→READY_EXECUTE`, `ARMED→ARMED`, etc.). Every `Verdict` value maps to exactly one `Campaign` value by construction.
- **`Exec_Category` / `Morning_Permission`** — `getExecutionCategory(s)` (`static/index.html:1288-1312`) lists `s.display_execution_category` first, then `getMorningExecutionPermission(s)` itself as the second candidate. Server-side, `display_execution_category` is set via `_extract_execution_category` (`intelligence_lab.py:393-406`), whose *own* first-priority key is `display_morning_execution_permission` / `morning_execution_permission`. In `MORNING_VALIDATION` mode (confirmed the mode for this run — `Lab handoff: MORNING_VALIDATION via morning_validated_trades | 952/1262`), every row has a permission value, so this first candidate is essentially always populated, making `Exec_Category` a copy of `Morning_Permission`.
- **`Exec_Category` / `MV_Verdict`** — `MV_Verdict` is `s['mv__verdict']`, the raw verdict field from `morning_validated_trades_*.csv`. Since `Exec_Category` traces back to `morning_execution_permission`, and the morning validator (Phase 10, out of scope) sets that permission *from* its own verdict decision, both columns are two labels emitted by the same upstream decision rather than two independent checks.

**Determination requested by the task:** `MV_Verdict` is **not** an independent confirmation of `Exec_Category` — both derive from the same morning-validation decision, just exposed under different field names. Treating agreement between them as "two systems confirming the same trade" is false comfort; it is one system's output read twice.

**Classification:** Naming/contract problem (the derivation is deterministic and traceable, not a bug), but its practical effect is the same as a bug if a trader or downstream consumer treats these as independent checks.

**Consequence for a trader:** A trade that looks "triple-confirmed" (`Verdict=GO`, `Campaign=READY_EXECUTE`, `MV_Verdict` agreeing) may in fact be a single decision reflected three times, with zero independent corroboration.

**Fix recommendation (not implemented):** Document in the export (a header comment row, or a data dictionary) which columns are independently sourced vs. derived aliases. Consider dropping the fully-duplicate `Lab_Verdict` column entirely.

**Confidence:** 85%.

---

## F8 — Vol_State and IVP_Label contradict

**Location:** `static/index.html:2036` (`Vol_State`) and `:2020` (`IVP_Label`, via `getOpt(s,'ivp_label')`).

**Mechanism:** These are two genuinely different metrics that happen to share a CHEAP/FAIR/EXPENSIVE vocabulary:

- `IVP_Label` (`opt__ivp_label`) is a bucketed function of **IV percentile rank** (`iv_rank`) — where current implied vol sits relative to its own history. For ticker `T`: `IVP = 65.7` → `EXPENSIVE` (matches the task's own stated thresholds, ≥65.2).
- `Vol_State` is a bucketed function of **GARCH's forward tailwind score** (`garch__l3_iv_tailwind_score`) — a model-relative judgment of whether priced-in vol is cheap or rich versus GARCH's own forecast. For `T`: `l3_iv_tailwind_score = -0.091`, well below the `-0.03` cutoff → `CHEAP`.

I verified both computations execute correctly against their own inputs — there is no code defect in either formula. `T` genuinely has historically-high current IV (expensive by percentile) while GARCH's model judges the vol being charged as cheap relative to what it expects to realize (a classic "IV rank high, but vol risk premium still underpriced vs. forecast" situation — plausible and not contradictory once the two reference frames are understood).

**Classification:** Naming/contract problem, not a defect. These are legitimately different concepts — a percentile-rank view and a model-relative-value view — sharing an unsafe vocabulary (`CHEAP`/`FAIR`/`EXPENSIVE`/`EXP`) with zero disambiguating label in the export.

**Consequence for a trader:** Seeing `Vol_State=CHEAP` next to `IVP_Label=EXPENSIVE` (true for 20/96 rows, ~21%) reads as an obvious data-quality bug and erodes trust in the export, even though both values are individually correct.

**Fix recommendation (not implemented):** Rename `Vol_State` to something that names its actual basis, e.g. `GARCH_Vol_Bucket` or `Vol_Tailwind_State`, to stop implying it measures the same thing as `IVP_Label`.

**Confidence:** 85%.

---

## F9 — Fields absent from the export entirely (`live_data_mode`, `trade_idea_id`)

**Location:** Export column list, `static/index.html:1979-2044` (neither field appears); merged signal confirmed via live `_load_run` trace.

**`trade_idea_id`:** **(b) held by the Lab, never read at export.** A live trace of the merged signal for ticker `T` shows `trade_idea_id = "20260731_083130:T:PUT:23.0:2026-08-21"` — a fully-formed, non-empty value present in memory. It is simply not among the ~55 columns the `exportCSV()` column list writes out. This is a clean, unambiguous gap.

**`live_data_mode`:** **(a) not produced upstream, for this run.** The literal field is defined and referenced in `morning_thesis_validator.py` (`LIVE_FIELDS` list, line 96; written at lines 2859-2868 via `live_data.setdefault("live_data_mode", live_data_mode)`), which is the correct upstream owner (Phase 10, out of audit scope). However, the actual output file for this run, `data/output/runs/20260731_083130/morning_validation/morning_validated_trades_20260731_083130.csv` (537 columns), **does not contain a `live_data_mode` column at all** — confirmed by direct inspection. The closest present field is `live_data_source = "POLYGON_SNAPSHOT"`, which records data provenance, not the LIVE/PAPER/SIMULATED/REGIME_WATCH mode enum the documented eligibility rule requires. The Lab cannot expose a field it was never handed. (Note: `live_data_source` is also not exported by the Lab, compounding the gap — same class of issue as `trade_idea_id`.)

**Comparison against `/api/run/{run_id}`:** I did not start the Flask server to query the live endpoint directly, but `_load_run()` (the function backing that endpoint) is the same function I traced directly in Python — its output confirms `trade_idea_id` is present in the in-memory payload and `live_data_mode` is not, under any prefix, for any of the 952 rows in this run's handoff slate.

**Classification:** `trade_idea_id`: defect (export omission). `live_data_mode`: not producible by the Lab as audited — the defect, if any, is in Phase 10's CSV-writing step, out of scope; flagged for the Phase 10 owner rather than diagnosed further here.

**Consequence for a trader:** Without `trade_idea_id` in the export, a trade in this CSV cannot be mechanically joined back to the journal/database record that shares that ID — manual reconciliation only. Without `live_data_mode`, the documented "must be LIVE to be eligible" rule cannot be checked from the export at all; a trader has no way to tell from this file whether a row's price data was a live quote, a paper/simulated fallback, or a regime-watch placeholder.

**Fix recommendation (not implemented):** Add `trade_idea_id` to the exportCSV column list — trivial, in-scope, no upstream dependency. For `live_data_mode`, escalate to whoever owns `morning_thesis_validator.py`'s CSV-writing step to confirm why a documented `LIVE_FIELDS` member is absent from the written file for this run.

**Confidence:** 95% for `trade_idea_id`; 85% for `live_data_mode`'s upstream-absence (limited to this one run's artifact; I did not check other runs).

---

## Severity ranking

**P0 — can make an unsound trade look sound, or silently discard a sound one:**
1. **F1 + F2 (same root cause)** — STRANGLE-to-single-leg collapse corrupts R:R and/or structural target on 43/96 rows (45%), including 19 live `GO` verdicts with a directionally impossible profit target.
2. **F4 — `Vetoes_Count` falsy-zero export bug** — a safety gate (`Vetoes_Count == 0` check) cannot distinguish "no vetoes" from "veto data never existed," compounding an already-broken upstream `contract_validity` field.
3. **F6 — Priority_Rank fuses verdict and permission without disclosure** — a trader can misjudge why a lower-conviction row outranks a higher-scored one.

**P1 — removes a safety signal or hides a defect:**
4. **F3 — EV sign loss** — defeats the `EV > 0` quick-filter for 4 genuinely negative-EV rows (though the categorical `EV_Decision` remains correct).
5. **F5 — Trigger_Score field collision** — a real, differentiating signal (Phase 8.6b's trigger layer) can be overshadowed by a Phase 7 placeholder sharing its name.
6. **F7 — Verdict collinearity** — creates false confidence that a trade is independently double/triple-confirmed when it is one decision shown multiple times.
7. **F9 — `trade_idea_id` / `live_data_mode` missing** — breaks mechanical journal reconciliation and removes the ability to check the documented LIVE-data eligibility rule from the export.

**P2 — robustness only:**
8. **F8 — Vol_State / IVP_Label vocabulary collision** — both fields are individually correct; the shared CHEAP/EXPENSIVE vocabulary is confusing but not misleading once understood.
9. **F4 (remaining null fields)** — `Horizon_*`, `Trigger_Primary/Quality/Codes`, `Days_To_Trigger`, `EIL_Verdict/Raw_Verdict/Composite`, `MV_Drift_Pct` are informational/context fields, not gating fields — their absence degrades context, not decision safety.

---

## The single highest-value fix

**Fix the STRANGLE-collapse in `_normalise_direction_value` / `_sync_lab_display_fields` (`intelligence_lab.py:1262-1292, 1358-1382`).** It is the direct cause of both F1 and F2 — 43 of 96 rows, the two highest-severity, most concretely evidenced findings in this audit — with a single, well-localized change: stop the direction-priority fallback from continuing past an explicit `STRANGLE`/non-directional result, and refuse to display a single-leg `Direction` label when the upstream layer marked the setup as non-directional. Every other finding in this report affects a smaller row count, a lower-severity failure mode, or sits partly/fully upstream of the Lab's scope. This one fix is inside the Lab, addresses the largest blast radius, and directly serves the fitness-for-purpose question the task asked.

---

## What I could not determine

- **F5's exact historical mechanism.** I established that two distinct `trigger_score` concepts exist and can collide, but re-running the Lab's live merge today does not reproduce the audited CSV's uniform `55.0` for ticker T (today's live merge correctly resolves to the real, low `0.0` value). I cannot rule out that the historical export reflects a transient state of the run folder (e.g., Phase 8.6b's output not yet merged) versus a since-changed code path. Flagged as 55% confidence rather than guessed higher.
- **F4's `Horizon_Action`/`Horizon_Source`/`Horizon_Pressure`/`Trigger_Price`/`Trigger_Primary`/`Trigger_Quality`/`Trigger_Codes` historical null cause.** Same reproducibility gap as F5 — these fields are populated in a live re-derivation today but 100% null in the audited export. I could not determine whether this is a timing issue specific to the 96-row morning-validation handoff subset, a since-fixed upstream gap, or a since-changed run-folder artifact.
- **Whether the pre-existing uncommitted changes in `intelligence_lab.py` and `static/index.html`** (present in the working tree before this audit started, not made by me) were in place when the audited CSV was generated on 2026-07-31. The uncommitted diff adds `NEGATIVE_RR`/`EOD_CAUTION` verdict overlays and new `Trigger_Price`/`Trigger_Display`/`Trigger_Evidence` export columns — the presence of those exact column headers in the audited CSV indicates the diff (or an equivalent prior version of it) was active at export time, but I cannot confirm the diff's exact state then versus now.
- **Whether the `NEGATIVE_RR` verdict (added client-side in `finalLabVerdict`, `static/index.html:1190-1195`, and referenced server-side in `_is_lab_audit_only`/`_display_campaign_for`/`_display_execution_mode_for`) is ever actually written into `lab_verdict` upstream**, or exists only as a client-side display override that the server-side ranking/bucketing logic cannot see. I found no code path that sets `sig["lab_verdict"] = "NEGATIVE_RR"`; if none exists, the server-side handling of that literal string is currently dead code. Worth a follow-up, not chased further here as it falls outside the nine assigned findings.

---

## Incidental observations (out of scope — not acted on)

- **Phase 7 (`avshunter_options_intelligence.py`), noted only because it is the direct upstream cause of F1/F2:** `target_in_play` (line 5622-5629) gates on whether the structural target clears the *call/put wall*, not whether it is simply on the profitable side of the strike. This is a real, separate design decision (conservative: don't credit R:R if a wall would cap the move) that is orthogonal to the STRANGLE-collapse bug — even after fixing the Lab's direction handling, wall-gated R:R will still zero out some genuinely-profitable-by-strike setups without saying why. Worth exposing `target_in_play`/`call_wall`/`put_wall` in the export so a trader can tell "no edge" from "wall-capped edge."
- **`_read_csv`'s (`intelligence_lab.py:81-89`) catch-all exception handling returns `[]` silently on any read error**, printing only to console (not surfaced in the API response body beyond `run_health.missing_optional`). This is the exact April-2026 masking pattern the background section warned about; it did not manifest for the files I checked in this run, but nothing prevents it from recurring undetected on a future run.
- **`morning_validation` path resolution** (`_morning_handoff_paths`, `intelligence_lab.py:121-141`) tries three fallback locations before giving up. I did not find evidence of the specific "read from wrong folder" April bug recurring in this run (the correct file was found on the first try), but the fallback chain itself remains a latent source of silent wrong-file reads if a future run's directory layout shifts.
- **`sb_position_size_pct`'s hardcoded bucket thresholds** (`intelligence_lab.py:1521-1523`: 100/75/55/35 for eil_composite ≥85/70/55/else) are a coincidental numeric neighbor to F5's `55.0` but are unrelated to it — confirmed by tracing both to different fields entirely. Flagging only because it was the first hit when searching for the literal `55` and could mislead a future investigator the same way it initially did me.

---

## Done-when checklist

- [x] All nine findings have a `file:line`, a mechanism, and a classification.
- [x] The fitness question is answered directly with a confidence percentage (Not yet, 90%).
- [ ] `git status` clean apart from this report — **not fully achievable**: `intelligence-lab/intelligence_lab.py` and `intelligence-lab/static/index.html` carry pre-existing uncommitted changes from before this audit began (documented above); I made no edits to any source file during this audit.
- [x] Nothing has been fixed.
