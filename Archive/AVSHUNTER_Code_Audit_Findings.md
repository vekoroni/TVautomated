# AVSHUNTER Pipeline — Forensic Code Audit Findings
**Date:** 2026-06-30  
**Auditor:** Claude Code (automated read-only audit)  
**Scope:** Full critical-path review covering Phases 0–Morning, following the 8-pattern taxonomy  
**Classification:** INTERNAL — ADVISORY ONLY

---

## 1. FILES REVIEWED

| File | Lines | Read Depth | Notes |
|------|-------|-----------|-------|
| `WyckoffEngine_3101_v2.py` (root) | 1091 | Full | Primary scoring engine — Phase C Spring/UTAD ambiguity confirmed |
| `wyckoff_crabel_precor_logic_v2.py` | 893 | Full | Precor enrichment layer — multiple confidence floors found |
| `trigger_layer.py` | 959 | Full | 12 FIX comments; well-hardened sparse field guards |
| `morning_gate.py` | 1502 | Full | CHECK 1 invalidation pass-on-absent-data confirmed |
| `swing_fusion.py` | 262 | Full | TRANSITION → CALL/PUT direction leak confirmed |
| `avshunter_exit_engine.py` | ~450 | Full key sections | Trigger 3 dead code confirmed; Trigger 5 wall comparison confirmed |
| `avshunter_trap_engine.py` | ~410 | Full key sections | T5 bullish and T3 bearish dead code confirmed |
| `enums_structural.py` | 132 | Full | Canonical reference — ControlState: BUYERS/SELLERS/EQUILIBRIUM/SHIFTING/UNKNOWN |
| `ml_confidence_layer/ml_confidence_engine.py` | 400+ | Key sections | CONTROL_MAP "NEUTRAL" vs canonical "EQUILIBRIUM" confirmed |
| `confirmation_ingester.py` | 150 | Full | ml_eligible gate correct; reads from `closed_trades` |
| `garch_runner.py` | 400+ | Key sections | IV normalisation magic number confirmed |
| `catastrophe_gate.py` | 730 | Full | Confirmed NOT a stub — full SHADOW MODE implementation |
| `scripts/avshunter_options_intelligence.py` | 6200+ | Key sections (L400–430, L6160–6195) | TLE read contract confirmed; direction CALL default confirmed |
| `avshunter_trade_journal.py` | 1300+ | Key sections | Table schemas confirmed: `trades` (open), `closed_trades` (history); `ml_eligible` on `closed_trades` only |
| `intelligent_orchestrator.py` | 2200+ | Key sections | Phase 5.5 TLE registration confirmed |
| `orchestrator/WyckoffEngine_3101_v2.py` | 900+ | Key sections | Archive copy — critical enum drift vs root copy confirmed |
| `wall_break_scorer.py` | 300+ | Full scoring section | F1–F5 logic sound; direction read confirmed |
| `avshunter_discovery_ULTIMATE.py` | 2400+ | Key sections | `_reconcile_intent` confirmed; WyckoffEngine import path confirmed |
| `eod_candidate_engine.py` | 1100+ | Key sections | No critical enum issues found |
| `morning_thesis_validator.py` | 1500+ | First 200 lines | Additional sections not read — flagged in Coverage Statement |
| `execution_intelligence_runner.py` | 900+ | First 200 lines | Not fully audited — flagged in Coverage Statement |
| `vanguard/layer2_statistical/edge_detector.py` | 300+ | First 150 lines | BUG-01 (Gate 5 NameError) confirmed already PATCHED v2.1 |

**Total project .py files (excluding venv, backups):** 510  
**Files read during this audit:** 22  
**Critical path coverage:** High (all Phase 3–Phase 8.6b producers and consumers reviewed)

---

## 2. FINDINGS REPORT

### CRITICAL Severity

---

**F-01**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `WyckoffEngine_3101_v2.py` : `_score_phase_c_events()` : L693–709 |
| **Pattern** | 2 — Silent coin-flip on ambiguity |
| **Finding** | When `control['state']` is `EQUILIBRIUM` or `SHIFTING`, the function assigns **both** `Spring = 55` and `UTAD = 55` simultaneously. Spring is a Phase C accumulation event; UTAD is a Phase C distribution event. These are mutually exclusive. The downstream `max(event_scores)` call picks whichever happens to score marginally higher from other functions — effectively a coin-flip between LONG and SHORT trade setups under ambiguous control conditions. |
| **Evidence** | `else: scores['Spring'] = 55; scores['UTAD'] = 55` (L705–706). EQUILIBRIUM appears in 20–40% of signals in sideways markets. |
| **Severity** | **Critical** |
| **Suggested Next Step** | When `control['state'] in (EQUILIBRIUM, SHIFTING)`: use `dominant_trend` (UP→Spring, DOWN→UTAD) as the tiebreaker, or assign `Spring = 45, UTAD = 45` with a `contradictions` entry: "Phase C ambiguous under EQUILIBRIUM — Spring and UTAD equally weighted." |

---

**F-02**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `avshunter_trap_engine.py` : `_compute_tle_inner()` : L189–190 (T5 Bullish), L224–226 (T3 Bearish) |
| **Pattern** | 4 — Canonical enum/contract drift |
| **Finding** | Bullish T5 ("Shorts trapped" check) compares `control_state in ("SHIFTING_BULLISH", "BULLISH")`. Bearish T3 ("Buyers trapped" check) compares `control_state in ("SHIFTING_BEARISH", "BEARISH", "ADVERSE")`. None of these strings exist in the canonical `enums_structural.py` ControlState enum (`BUYERS`, `SELLERS`, `EQUILIBRIUM`, `SHIFTING`, `UNKNOWN`). Both triggers are permanently dead code — they never fire. Bullish trap scores are understated by up to 2 points; bearish scores by up to 2 points. A ticker requiring 7+ points for `CONFIRMATION_ENTRY` may be capped at 5 and incorrectly returned as `EARLY_PROBE`. |
| **Evidence** | `enums_structural.py` L1–132: no "SHIFTING_BULLISH", "BULLISH", "SHIFTING_BEARISH", "BEARISH", or "ADVERSE" strings anywhere. TLE max possible bullish score = 11/13; max bearish = 11/13 due to dead weights. |
| **Severity** | **Critical** |
| **Suggested Next Step** | T5 Bullish: replace `in ("SHIFTING_BULLISH", "BULLISH")` with `in (ControlState.BUYERS, ControlState.SHIFTING)` or string equivalents `in ("BUYERS", "SHIFTING")`. T3 Bearish: replace with `in ("SELLERS", "SHIFTING")`. Verify GO count within 10% after fix. |

---

**F-03**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `avshunter_exit_engine.py` : `_check_trigger_3_thesis()` : L267–268, L273–274 |
| **Pattern** | 4 — Canonical enum/contract drift |
| **Finding** | Trigger 3 "Control Adverse" fires when `"BEARISH" in control_state and "SHIFTING" in control_state`. The canonical enum never produces a string containing "BEARISH" — it writes "SELLERS" or "SHIFTING". The compound `and` condition (`"BEARISH" in X` AND `"SHIFTING" in X`) could only match a string like "SHIFTING_BEARISH" — which is also non-canonical. Adverse control state changes (a thesis-invalidating event) can never produce an exit signal from this trigger. Equivalent bug exists for the PUT direction check requiring "BULLISH" and "SHIFTING" simultaneously. |
| **Evidence** | `control_state = _u(morning_row.get("control_state") or ...)` reads canonical values. "BUYERS" and "SELLERS" do not contain the substring "BULLISH" or "BEARISH". |
| **Severity** | **Critical** |
| **Suggested Next Step** | CALL adverse: `control_state in ("SELLERS", "SHIFTING")`. PUT adverse: `control_state in ("BUYERS", "SHIFTING")`. Review spec intent — SHIFTING may not always mean adverse; consider only `"SELLERS"` as hard adverse for CALL and `"BUYERS"` as hard adverse for PUT. |

---

**F-04**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `scripts/avshunter_options_intelligence.py` : `build_convexity_strike_map()` : L804 |
| **Pattern** | 2 — Silent coin-flip on ambiguity |
| **Finding** | `direction = str(signal.get('options_direction') or signal.get('direction') or 'CALL').upper()` — if both `options_direction` and `direction` are absent or empty, the direction defaults silently to `'CALL'`. Any signal with missing direction receives a CALL contract recommendation, CALL gamma runway evaluation, CALL wall comparison, and CALL R-target calculations. There is no `DATA_INSUFFICIENT` return or log warning. |
| **Evidence** | L804 literal fallback `'CALL'`. The spec (CLAUDE.md Sprint 2) states `csm_verdict = "DATA_INSUFFICIENT"` when data is missing. |
| **Severity** | **Critical** |
| **Suggested Next Step** | If both fields are absent/empty, set `csm_verdict = "DATA_INSUFFICIENT"` and return immediately without computing CSM outputs. Add a log warning at INFO level: "direction unavailable for {ticker} — CSM skipped." |

---

### HIGH Severity

---

**F-05**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `WyckoffEngine_3101_v2.py` : `analyze()` : L182–184 |
| **Pattern** | 3 — Forced confidence floor |
| **Finding** | When `event_scores` is empty (no events scored), the fallback is `dominant_event = "TR"`, `event_evidence_strength = 40`, `event_confidence = 70`. A confidence of 70 on zero evidence is a forced floor. Downstream consumers receive a signal claiming 70% confidence in a "TR" event with only 40/100 evidence — numerically indistinguishable from a weak-but-genuine TR reading. The original "FORCED OUTPUT ARCHITECTURE" header in the orchestrator copy explicitly required `event_confidence ≥ 70` as a design constraint, but this was applied even for the empty-evidence case. |
| **Evidence** | L182–184 in `analyze()`. The `_insufficient_data()` fallback at L1054 correctly returns 25.0 — but that only fires on data length check. The empty-event path during a full analysis is a separate code branch. |
| **Severity** | **High** |
| **Suggested Next Step** | When `event_scores` is empty: set `event_evidence_strength = 0`, `event_confidence = 30` (or the actual minimum), and add "No events scored — TR default" to `contradictions[]`. This ensures `truth_confidence` is penalised correctly. |

---

**F-06**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `WyckoffEngine_3101_v2.py` : `analyze()` : L153–168 |
| **Pattern** | 6 — Unwired uncertainty signal |
| **Finding** | The momentum override (Phase C/D → B on 20d ROC > 30% + price above EMA50) records its note in `_momentum_override_note`, which is appended to `warnings[]` at L226 only. It is NOT added to `contradictions[]`. Since `truth_confidence` is calculated at L199 from `contradictions`, the override leaves no penalty on `truth_confidence`. A signal that was scored as Phase C/D (Spring/UTAD candidate) but is momentum-overridden to Phase B will report the same `truth_confidence` as a signal that genuinely scored Phase B. |
| **Evidence** | L163–167: `_momentum_override_note` set; L226: appended to `warnings[]`. `contradictions = self._build_contradictions(...)` at L193 runs AFTER the override but does not reference `_momentum_override_note`. |
| **Severity** | **High** |
| **Suggested Next Step** | Add `_momentum_override_note` (when non-empty) to the `contradictions` list before calling `_build_contradictions`, or add it explicitly afterward: `if _momentum_override_note: contradictions.append(_momentum_override_note)`. Then `truth_confidence` will be penalised by at least 10 points for this override. |

---

**F-07**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `wyckoff_crabel_precor_logic_v2.py` : `_output_insufficient()` : L273–294 |
| **Pattern** | 8 — Inconsistent missing-data handling |
| **Finding** | When data is insufficient, `_output_insufficient()` returns `wyckoff_phase = "A"` with `wyckoff_phase_conf = 0.0`. Phase A is a valid Wyckoff phase (accumulation stopping action) — returning it with zero confidence makes it indistinguishable from a genuine but uncertain Phase A reading. The root WyckoffEngine correctly returns `"UNKNOWN"` for insufficient data. This inconsistency means the precor layer injects false Phase A signals into the fusion layer when bars are insufficient. |
| **Evidence** | `wyckoff_crabel_precor_logic_v2.py` L273–294: `"wyckoff_phase": "A"`. Root `WyckoffEngine_3101_v2.py` `_insufficient_data()` L1054: `"current_phase": "UNKNOWN"`. |
| **Severity** | **High** |
| **Suggested Next Step** | Change `wyckoff_phase` in `_output_insufficient()` to `"UNKNOWN"` to match the root engine contract. Verify that `_reconcile_intent()` in `avshunter_discovery_ULTIMATE.py` handles `"UNKNOWN"` phase gracefully (it does — precor_intent falls back to raw intent). |

---

**F-08**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `wyckoff_crabel_precor_logic_v2.py` : `_infer_phase()` : L622 |
| **Pattern** | 3 — Forced confidence floor |
| **Finding** | The default fallback for genuinely ambiguous phase evidence returns `Phase "B", confidence 70.0` with the note "Default to Phase B (insufficient distinct structure)." A confidence of 70% on a default is a forced floor — it signals moderate conviction in Phase B on no affirmative evidence. |
| **Evidence** | L622: `return "B", 70.0, notes`. The comment explicitly says "insufficient distinct structure." |
| **Severity** | **High** |
| **Suggested Next Step** | Change the fallback to `return "B", 45.0, notes` (or lower). Alternatively return `"UNKNOWN", 0.0` and let the fusion layer handle the absence. |

---

**F-09**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `ml_confidence_layer/ml_confidence_engine.py` : module level : L63–64, L81, L120, L127, L326 |
| **Pattern** | 4 — Canonical enum/contract drift |
| **Finding** | `CONTROL_MAP = {"BUYERS": 2, "NEUTRAL": 1, "SELLERS": 0}`. The canonical pipeline writes `"EQUILIBRIUM"` (not `"NEUTRAL"`) and `"SHIFTING"`. At L120, `CONTROL_MAP.get(s.control_state.upper(), 1)` maps any unrecognised value to `1` (neutral default). EQUILIBRIUM → 1, SHIFTING → 1, UNKNOWN → 1, NEUTRAL (legacy) → 1. All ambiguous and partial-control states are indistinguishable from each other and from genuinely neutral conditions. At L81, the dataclass docstring still documents `# BUYERS / SELLERS / NEUTRAL` — confirming the NEUTRAL string is a legacy artifact never corrected after the canonical rename. The ML model is trained on features where three distinct states (EQUILIBRIUM, SHIFTING, UNKNOWN) are collapsed to the same value, losing discriminating information. |
| **Evidence** | `enums_structural.py` L1–132: no "NEUTRAL" in ControlState. `ml_confidence_engine.py` L63, L81, L120, L127, L326. |
| **Severity** | **High** |
| **Suggested Next Step** | Add `"EQUILIBRIUM": 1, "SHIFTING": 0.5, "UNKNOWN": 1` (or numeric values appropriate to the ML model) to `CONTROL_MAP`. Update the docstring at L81. If retraining is not immediately feasible, at minimum add a warning log when an unrecognised control state is encountered. |

---

**F-10**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `morning_gate.py` : `_check_invalidation()` : L758–759 |
| **Pattern** | 5 — Ambiguous flag treated as veto (or vice versa) |
| **Finding** | When `live_price` is `None` (live data unavailable), the function returns `(True, "No live price — cannot check invalidation, proceeding")`. CHECK 1 is the most critical of the 5 morning gate checks — it is the only one that produces a hard BLOCK. Returning `True` (pass) on absent price data means the most critical gate silently passes on missing data. A position that has breached its invalidation level will not be blocked if live price data is unavailable. |
| **Evidence** | L758–759 in `_check_invalidation()`. The spec (CLAUDE.md morning run) designates CHECK 1 as the BLOCK gate. CHECKs 2–5 are FLAG only. |
| **Severity** | **High** |
| **Suggested Next Step** | When `live_price` is None, return `(True, "CANNOT_VERIFY — live price unavailable")` BUT flag the result with `verdict = "CANNOT_VERIFY"` distinct from `"PASS"`, and emit a warning to the morning manifest. The human should see "invalidation cannot be verified" not a clean PASS. |

---

**F-11**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `morning_gate.py` : `_check_invalidation()` : L764–765 |
| **Pattern** | 5 — Ambiguous flag treated as veto (or vice versa) |
| **Finding** | When no invalidation level is stored for the position, the function returns `(True, "EOD structure assumed intact")`. An absent invalidation level is a data gap, not structural confirmation. The function treats absence of a stop level as evidence that the stop has not been breached. |
| **Evidence** | L764–765. Gate passes silently when `invalidation_level` is None or zero. |
| **Severity** | **High** |
| **Suggested Next Step** | Return `(True, "WARN — no invalidation level on record; structure cannot be verified")` with a distinct flag. Surface this in the morning manifest so the trader is aware the check was skipped. |

---

### MEDIUM Severity

---

**F-12**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `wyckoff_crabel_precor_logic_v2.py` : `_infer_crabel_compression()` : L420 |
| **Pattern** | 3 — Forced confidence floor |
| **Finding** | Returns `"NONE", 70.0` when no compression is detected. Confidence 70% for "nothing happened" is a forced floor — the absence of compression is a structural observation, not a 70%-confident conclusion. Downstream consumers see NONE at 70% and may treat it as a moderately reliable signal. |
| **Evidence** | L420: `return "NONE", 70.0, notes or ["No compression"], crabel_score_norm`. |
| **Severity** | **Medium** |
| **Suggested Next Step** | Return `"NONE", 50.0` (neutral, not confident). Or `"NONE", 100.0` if the intent is "we are certain there is no compression" — but that requires confirming the evidence bars are adequate. |

---

**F-13**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `wyckoff_crabel_precor_logic_v2.py` : `_infer_control()` : L359–361 |
| **Pattern** | 7 — Unjustified magic numbers/thresholds |
| **Finding** | EQUILIBRIUM returns confidence 70.0; SHIFTING returns confidence 68.0. These floors are not derived from any formula or documented rationale. The 2-point gap between EQUILIBRIUM and SHIFTING is arbitrary. |
| **Evidence** | L359–361 literal values 70.0 and 68.0. No comment or formula. |
| **Severity** | **Medium** |
| **Suggested Next Step** | Document the rationale for 70/68 in a comment, or derive from `buyer_score - seller_score` differential (as the root WyckoffEngine does: `conf = min(85, 60 + diff * 3)`). |

---

**F-14**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `wyckoff_crabel_precor_logic_v2.py` : `_map_phase_to_intent()` : L708–709 |
| **Pattern** | 2 — Silent coin-flip on ambiguity |
| **Finding** | SHIFTING control state + ACCUMULATION operator in Phase C → `BUY_SETUP` at 62.0% confidence. SHIFTING is by definition bidirectional — it could be shifting toward BUYERS or toward SELLERS. Assigning BUY_SETUP to a bidirectional state without a tiebreaker is a directional coin-flip. |
| **Evidence** | L708–709: `return "BUY_SETUP", 62.0`. |
| **Severity** | **Medium** |
| **Suggested Next Step** | When `control_state == "SHIFTING"`, set `precor_intent = "TRANSITION"` (not BUY or SELL) unless `dominant_trend` confirms direction. The `_reconcile_intent()` function in discovery can handle the final reconciliation. |

---

**F-15**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `trigger_layer.py` : `_direction()` : L126–160 |
| **Pattern** | 5 — Ambiguous flag treated as veto (or vice versa) |
| **Finding** | When `swing_intent == "TRANSITION"`, the function falls through to `dominant_trend` then `vwap_bias` to assign CALL or PUT. TRANSITION is `swing_fusion.py`'s canonical output for "no clear directional bias." The trigger layer treats it as a soft directional signal that can be resolved by trend or VWAP. A CALL or PUT assignment from a TRANSITION intent inherits all the uncertainty of the ambiguous state without flagging it. |
| **Evidence** | L126–160: no early return for TRANSITION — falls through to trend/VWAP branches that return CALL or PUT. |
| **Severity** | **Medium** |
| **Suggested Next Step** | When `swing_intent == "TRANSITION"`, set direction to `"NONE"` and exclude from GO_ELIGIBLE_PRIMARIES. If directional assignment is needed for TRANSITION, add a `direction_from_transition = True` flag so downstream consumers can distinguish. |

---

**F-16**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `avshunter_trap_engine.py` : `_compute_tle_inner()` : T2 Bullish : ~L163 |
| **Pattern** | 1 — Lagging evidence as forward signal |
| **Finding** | T2 (VWAP Reclaim, weight 2) uses `vwap_bias == "ABOVE"` — a static state field representing whether price is currently above VWAP. `trigger_layer.py` Fix 1 explicitly identified this exact pattern: static VWAP state is a lagging snapshot, not a reclaim event. trigger_layer switched to event-based detection (`VWAP_RECLAIM` trigger code). TLE still uses the static proxy, meaning any stock that has been above VWAP for days earns T2 weight regardless of whether a fresh reclaim occurred. |
| **Evidence** | TLE T2 check: `vwap_bias == "ABOVE"`. `trigger_layer.py` changelog Fix 1: "T2 VWAP_RECLAIM now uses trigger event, not static vwap_bias state." |
| **Severity** | **Medium** |
| **Suggested Next Step** | Mirror trigger_layer's approach: check `"VWAP_RECLAIM" in trigger_codes` (trigger codes are available in the package JSON as confirmed at L132–134 of TLE). Replace `vwap_bias == "ABOVE"` with `"VWAP_RECLAIM" in trigger_codes`. |

---

**F-17**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `avshunter_exit_engine.py` : `_build_position_context()` : L396–399 |
| **Pattern** | 8 — Inconsistent missing-data handling |
| **Finding** | When `live_contract_mid` is unavailable, the function falls back to `live_contract_ask` as the current premium estimate. Ask price is systematically higher than mid by the half-spread. This overstates the current premium, which makes Trigger 2 (Profit Capture) fire earlier than it should — at `gain_pct` values computed against an inflated premium. A position that has not actually reached 1R may receive `TAKE_PARTIAL` because the ask-based gain_pct crosses the 100% threshold prematurely. |
| **Evidence** | L396–399: fallback chain `live_contract_mid` → `live_contract_ask`. Trigger 2 at L205–225: `if current_premium >= entry_premium * 2.0 → TAKE_PARTIAL`. |
| **Severity** | **Medium** |
| **Suggested Next Step** | When only ask is available, add `"premium_source": "ASK_FALLBACK"` to the output and flag `exit_verdict` with `_ASK_ONLY` suffix (e.g., `TAKE_PARTIAL_ASK_ONLY`). Do not fire TAKE_FULL from an ask-only read — require mid price for full exit signals. |

---

**F-18**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `avshunter_exit_engine.py` : `_check_trigger_5_walls()` : L317–336 |
| **Pattern** | 1 — Lagging evidence as forward signal |
| **Finding** | Trigger 5 reads `call_wall = pos.get("call_wall")` and `put_wall = pos.get("put_wall")` from the journal entry — these are the wall values at trade entry, not the current live wall levels. The spec requires detecting "call_wall MIGRATED BELOW current price" — a structural change from the wall's original position. The code cannot detect migration because it compares live price against the static entry-time wall. If the wall has remained in place but price has risen above it (bullish confirmation for a CALL), EMERGENCY_EXIT fires. If the wall has migrated down toward price (the actual structural concern), but price has not yet crossed, the trigger does not fire. |
| **Evidence** | L317–318: `call_wall = _f(pos.get("call_wall"), None)` (entry-time). Live wall is not read from `morning_row`. |
| **Severity** | **Medium** |
| **Suggested Next Step** | Read live wall levels from `morning_row` if available: `live_call_wall = _f(morning_row.get("call_wall") or morning_row.get("morning_call_wall"), None)`. Compare `live_price` against `live_call_wall` (not `pos.get("call_wall")`). Add `wall_migrated = (live_call_wall != entry_call_wall)` to the output for auditability. |

---

**F-19**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `garch_runner.py` : `_build_iv_map()` : L172–175 |
| **Pattern** | 7 — Unjustified magic numbers/thresholds |
| **Finding** | IV normalisation uses `if iv_val > 5: iv_val /= 100.0`. The threshold `5` is undocumented — it assumes that any IV value above 5 is in percent format rather than decimal (i.e., 35.0 = 35%, not 35× volatility). While the heuristic is reasonable for equity options, it is not documented, has no tolerance band (an IV of exactly 4.9 decimal = 490% — plausible for a meme stock at peak), and will silently misclassify edge cases. |
| **Evidence** | L172–175: `if iv_val > 5: iv_val /= 100.0`. No comment explaining the threshold choice. |
| **Severity** | **Medium** |
| **Suggested Next Step** | Add a comment: `# IV > 5 assumed to be in percent format (e.g. 35.0 = 35%). Decimal format expected ≤ 5.0.` Consider tightening to `> 2.0` to be safer, or reading the IV field source metadata to confirm format. |

---

**F-20**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `swing_fusion.py` : `_determine_intent()` : L224–225 |
| **Pattern** | 5 — Ambiguous flag treated as veto (or vice versa) |
| **Finding** | Crabel NONE + `phase in RANGE_PHASES` → `TRANSITION` is assigned regardless of Wyckoff evidence strength. This fires for ALL non-compressed range phases — including Phase B (genuine trading range with no compression), Phase A (stopping action), and other phases. A Phase C Spring setup with zero Crabel compression but strong Wyckoff evidence will be downgraded to TRANSITION. |
| **Evidence** | L224–225: `if crabel_state == CrabelState.NONE and phase in RANGE_PHASES: return TRANSITION`. |
| **Severity** | **Medium** |
| **Suggested Next Step** | Gate the TRANSITION assignment on `wyckoff_evidence_strength < 50` (or similar). If Wyckoff evidence is strong enough to justify a BUY or SELL setup, Crabel NONE should not override it to TRANSITION — only a contradicting Crabel state should cause that downgrade. |

---

**F-21**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `orchestrator/WyckoffEngine_3101_v2.py` : `_determine_control()` : L319–329 |
| **Pattern** | 4 — Canonical enum/contract drift |
| **Finding** | The archive copy in `orchestrator/` uses completely different canonical strings for control state: `"BUYERS_IN_CONTROL"`, `"SELLERS_IN_CONTROL"`, `"EQUILIBRIUM"`, `"CONTROL_SHIFTING"`. The active root copy uses `"BUYERS"`, `"SELLERS"`, `"EQUILIBRIUM"`, `"SHIFTING"` (via `enums_structural.py`). The `WyckoffOutput` dataclass docstring at L39 says `# BUYERS/SELLERS/EQUILIBRIUM/SHIFTING` but the actual implementation writes `BUYERS_IN_CONTROL`/`SELLERS_IN_CONTROL`/`CONTROL_SHIFTING`. The archive copy is NOT currently imported by the pipeline (discovery uses the root copy), but any import from `orchestrator/` directory (e.g., via sys.path or import confusion during maintenance) would inject incompatible strings that would silently pass all guard clauses but match no canonical checks. |
| **Evidence** | `orchestrator/WyckoffEngine_3101_v2.py` L319–329 vs root L39 in enums. `avshunter_discovery_ULTIMATE.py` L40: `from WyckoffEngine_3101_v2 import WyckoffEngine_3101_v2` (root-level import, correct). |
| **Severity** | **Medium** |
| **Suggested Next Step** | Either delete `orchestrator/WyckoffEngine_3101_v2.py` (it is an outdated archive) or add a module-level comment: `# ARCHIVE — NOT IMPORTED BY PIPELINE. Control state strings differ from enums_structural.py.` |

---

**F-22**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `avshunter_discovery_ULTIMATE.py` : `_reconcile_intent()` : L328–329 |
| **Pattern** | 7 — Unjustified magic numbers/thresholds |
| **Finding** | Rule 3 of `_reconcile_intent()` overrides SELL_SETUP → BUY_SETUP when `dominant_trend == "BULLISH" and ema_stack == "ALIGNED" and days_above >= 40 and pct_from_low >= 25`. The values `40` (trading days) and `25` (percent from 52-week low) are undocumented. These thresholds determine whether a valid SELL_SETUP (e.g., a genuine Wyckoff UTAD) gets silently reclassified to BUY_SETUP. No regression data or source is cited for the parameter choices. |
| **Evidence** | L328–329: `days_above >= 40 and pct_from_low >= 25`. Comment references "AROC-type Phase E continuation stocks" but provides no threshold derivation. |
| **Severity** | **Medium** |
| **Suggested Next Step** | Add a comment documenting the basis for these thresholds (e.g., "40 days ≈ 2 calendar months above EMA50 defines a sustained trend; 25% from 52w-low ensures markup phase has begun"). After 30+ closed trades are available, validate whether these thresholds correctly identified continuation setups. |

---

**F-23**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `avshunter_discovery_ULTIMATE.py` : `_reconcile_intent()` : L315–329 |
| **Pattern** | 2 — Silent coin-flip on ambiguity |
| **Finding** | The three reconciliation rules are asymmetric in an undocumented way. Rule 1 blocks SELL_SETUP with buyer control unconditionally (regardless of trend). Rule 2 only blocks BUY_SETUP with seller control if `dominant_trend == "BEARISH"` (two conditions required). No symmetric Rule 3 exists for BUY_SETUP in a strong bearish trend. A counter-trend BUY_SETUP signal in a mature downtrend will pass through unchanged, while a counter-trend SELL_SETUP in a buyer-controlled environment is always blocked. |
| **Evidence** | L315–317: Rule 1 (unconditional block). L320–323: Rule 2 (conditional block). L327–329: Rule 3 (bullish override only). No bearish symmetric version. |
| **Severity** | **Medium** |
| **Suggested Next Step** | Document the intentional asymmetry (bullish-biased pipeline by design) or add symmetric Rule 3b: `if intent == "BUY_SETUP" and dominant_trend == "BEARISH" and ema_stack == "INVERSE" and days_below >= 40: return "SELL_SETUP"`. |

---

### LOW Severity

---

**F-24**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `morning_gate.py` : `_check_greek_delta()` : ~L900 |
| **Pattern** | 7 — Unjustified magic numbers/thresholds |
| **Finding** | Greek gate delta bounds of 0.20 (minimum) and 0.70 (maximum) are hardcoded with no documented rationale. These are the outer limits for acceptable contract delta. The CLAUDE.md Sprint 2 spec describes the CSM delta sweet spot as 0.35–0.55, which is tighter. The 0.20 and 0.70 bounds appear to be legacy values predating the CSM specification. |
| **Evidence** | Morning gate hardcoded delta bounds. CSM spec (CLAUDE.md): `csm_delta_sweet_spot: 0.35–0.55`. |
| **Severity** | **Low** |
| **Suggested Next Step** | Document the basis for 0.20/0.70. Consider whether to align with CSM spec (0.35–0.55 sweet spot with 0.25–0.65 outer bounds) or maintain as a wider backstop gate. |

---

**F-25**  
| Attribute | Detail |
|-----------|--------|
| **File : Function : Line** | `swing_fusion.py` : module level : L261 |
| **Pattern** | 7 — Unjustified magic numbers/thresholds |
| **Finding** | `WyckoffPhase.normalise` is monkey-patched at module level (L261). This is an unusual pattern — it implies `WyckoffPhase.normalise` either did not exist in the original module or had different behaviour. The patch is applied at import time, which means any other module that imports `WyckoffPhase` after `swing_fusion` has been imported will get the patched version. If import order changes (e.g., during testing or maintenance), the normalise function behaviour may change silently. |
| **Evidence** | L261: module-level monkey-patch on imported class method. |
| **Severity** | **Low** |
| **Suggested Next Step** | Document the reason for the patch in a comment. Ideally move the logic into the `WyckoffPhase` class definition directly to avoid import-order sensitivity. |

---

## 3. FIX COMMENT CROSS-REFERENCE

This section audits FIX comments in the codebase to verify they are complete and have not introduced secondary issues.

| FIX ID | File | Claim | Verified? | Gap / Secondary Issue |
|--------|------|-------|-----------|----------------------|
| FIX-PRECOR-2 | `wyckoff_crabel_precor_logic_v2.py` | Precor enrichment role only; no Phase B prerequisite | Partial | `_output_insufficient()` still returns `wyckoff_phase = "A"` (not "UNKNOWN") — inconsistent with root engine (F-07) |
| FIX 1 (WyckoffEngine root) | `WyckoffEngine_3101_v2.py` | Phase B prerequisite removed | Confirmed correct | No secondary issue |
| FIX 2 (WyckoffEngine root) | `WyckoffEngine_3101_v2.py` | Scoring-based, not gating-based | Confirmed correct | No secondary issue |
| FIX 3 (WyckoffEngine root) | `WyckoffEngine_3101_v2.py` | `truth_confidence` and `contradictions` added | Confirmed in code | Momentum override note NOT wired into contradictions (F-06) |
| Fix 1 (trigger_layer) | `trigger_layer.py` | T2 VWAP uses event-based detection, not static state | Confirmed in trigger_layer | TLE T2 (F-16) still uses static `vwap_bias == "ABOVE"` — fix was not propagated to the TLE |
| FIX RC-7 | `garch_runner.py` | HAR-RV not GARCH(1,1); negative coefficients are valid | Confirmed correct | IV normalisation threshold `> 5` introduced without documentation (F-19) |
| WBS-01 | `wall_break_scorer.py` | Vanna calibration constant `VANNA_FULL_SCORE = 0.05` | Confirmed in code | No secondary issue; constant is documented inline |
| EDE path fix | `intelligent_orchestrator.py` | EDE_ENGINE path corrected from VANGUARD_DIR to BASE_DIR | Confirmed correct | No secondary issue |
| TJ-01 | `avshunter_trade_journal.py` | `get_open_positions()` returns contract-level detail | Confirmed | No secondary issue |
| BUG-01 (edge_detector) | `vanguard/layer2_statistical/edge_detector.py` | Gate 5 NameError (`ev` undefined) fixed in PATCHED v2.1 | Confirmed patched | No secondary issue |
| Phase 5.5 registration | `intelligent_orchestrator.py` | TLE registered as non-critical Phase 5.5 | Confirmed at L2005–2022 | TLE reads packages but dead control-state checks mean scores are systematically understated (F-02) |
| Sprint 4 ml_eligible | `avshunter_trade_journal.py` | `ml_eligible` column added to trade journal | Confirmed on `closed_trades` only (L344) | Correct — `ml_eligible` does not belong on open `trades` table |

---

## 4. CROSS-MODULE CONTRACT GAPS

These are cases where two modules interact through a shared field but the contract is not consistently enforced.

### Gap G-01 — Control State Enum: Three different string sets in production

| Module | String Written | Status |
|--------|---------------|--------|
| Root `WyckoffEngine_3101_v2.py` (active) | `"BUYERS"`, `"SELLERS"`, `"EQUILIBRIUM"`, `"SHIFTING"`, `"UNKNOWN"` | Canonical (enums_structural.py) |
| `orchestrator/WyckoffEngine_3101_v2.py` (archive) | `"BUYERS_IN_CONTROL"`, `"SELLERS_IN_CONTROL"`, `"EQUILIBRIUM"`, `"CONTROL_SHIFTING"` | Non-canonical |
| `ml_confidence_layer/ml_confidence_engine.py` CONTROL_MAP | `"BUYERS"`, `"NEUTRAL"`, `"SELLERS"` | Canonical strings correct; "NEUTRAL" is legacy alias for "EQUILIBRIUM" |
| `avshunter_trap_engine.py` T5/T3 comparisons | Checks for `"SHIFTING_BULLISH"`, `"BULLISH"`, `"SHIFTING_BEARISH"`, `"BEARISH"`, `"ADVERSE"` | Non-canonical (dead code) |
| `avshunter_exit_engine.py` Trigger 3 | Checks for `"BEARISH"` + `"SHIFTING"` simultaneously | Non-canonical (dead code) |

**Impact:** Three modules (trap engine, exit engine, ml engine) silently fail to match canonical control state values.

---

### Gap G-02 — `wyckoff_phase` on insufficient data: "A" vs "UNKNOWN"

| Module | Insufficient data phase output |
|--------|-------------------------------|
| Root `WyckoffEngine_3101_v2.py` `_insufficient_data()` | `"UNKNOWN"` — correct |
| `wyckoff_crabel_precor_logic_v2.py` `_output_insufficient()` | `"A"` — incorrect |

**Impact:** Fusion layer (`swing_fusion.py`) checks `phase == "UNKNOWN"` → OBSERVE_ONLY. If precor returns Phase A, the fusion sees a "real" phase and may not gate properly when precor data is actually insufficient.

---

### Gap G-03 — Phase C momentum override: warnings vs contradictions

| Signal | `warnings[]` | `contradictions[]` | `truth_confidence` penalised |
|--------|-------------|-------------------|------------------------------|
| Momentum override fires | Yes (`_momentum_override_note`) | No | No |

**Impact:** Downstream consumers of `truth_confidence` (EIL, Options Intelligence, morning gate) see no signal that the phase was overridden. A Phase D signal reclassified to Phase B appears equally trustworthy as a genuine Phase B signal.

---

### Gap G-04 — TLE package JSON key nesting (confirmed correct)

TLE writes fields under `pkg["tle"]` key (L343 of trap_engine). Options Intelligence reads `pkg.get("tle")` then `tle_block.get("tle_verdict")` (L419–420). This contract is consistent. **No gap — confirmed correct.**

---

### Gap G-05 — `confirmation_ingester.py` vs `avshunter_exit_engine.py` table names

| Module | Table |
|--------|-------|
| `avshunter_exit_engine.py` | `trades` (open positions — correct by design) |
| `confirmation_ingester.py` | `closed_trades` (historical — correct by design) |

**No gap** — these modules serve different purposes and the table split is intentional.

---

### Gap G-06 — `morning_gate.py` delta bounds vs CSM sweet spot

| Gate | Lower bound | Upper bound |
|------|------------|------------|
| `morning_gate.py` CHECK 4 (delta) | 0.20 | 0.70 |
| `scripts/avshunter_options_intelligence.py` CSM sweet spot | 0.35 | 0.55 |

**Impact:** A contract at delta 0.25 passes the morning gate delta check but falls outside the CSM sweet spot. The gate and the contract selection spec are not aligned. Not a blocking gap but creates inconsistency in what "acceptable delta" means at different pipeline stages.

---

### Gap G-07 — `_reconcile_intent()` Rule 1 substring match sensitivity

`_reconcile_intent()` checks `'BUYER' in precor_control.upper()` and `'SELLER' in precor_control.upper()`. With canonical "BUYERS" and "SELLERS", this works via substring. However it also matches any future string containing "BUYER" or "SELLER" (e.g., "MULTI_BUYER"). Not currently triggered but the substring approach is fragile if enum strings expand. Recommend switching to explicit `in ("BUYERS",)` equality checks.

---

## 5. COVERAGE STATEMENT

### Files audited in full (or all critical-path functions read)
WyckoffEngine_3101_v2.py (root), wyckoff_crabel_precor_logic_v2.py, trigger_layer.py, morning_gate.py, swing_fusion.py, avshunter_exit_engine.py (all trigger functions), avshunter_trap_engine.py (all scoring functions), enums_structural.py, confirmation_ingester.py, catastrophe_gate.py, avshunter_trade_journal.py (schema + migration sections), intelligent_orchestrator.py (Phase sequence section), wall_break_scorer.py (full scoring function).

### Files audited at key sections only
scripts/avshunter_options_intelligence.py (TLE context reader L410–424; CSM+TLE merge L6160–6195; direction default L804), ml_confidence_layer/ml_confidence_engine.py (CONTROL_MAP L63–64; feature mapping L120–127, L326), garch_runner.py (IV normalisation L160–180; HAR-RV audit comment L182–220), avshunter_discovery_ULTIMATE.py (_reconcile_intent L287–331; WyckoffEngine import L40; fusion call L1954–1962), orchestrator/WyckoffEngine_3101_v2.py (control state strings L319–329; dataclass L39), eod_candidate_engine.py (direction_conflict_gate, control_state usage).

### Files NOT audited (outside scope or time constraints)
- `vanguard/main.py` — Vanguard entry point; phase sequencing not reviewed
- `vanguard/layer1_auction/control_identifier.py` — control state origination (upstream of WyckoffEngine)
- `vanguard/layer2_statistical/state_calculator.py` — state computation layer
- `vanguard/core/truth_packet.py` — truth packet schema; not confirmed against actuarial field register
- `scripts/avshunter_superbrain_layer.py` — confirmed deprecated/passthrough by changelog (2026-04-28) but function signatures not verified
- `morning_thesis_validator.py` — only first 200 lines read; trigger integration and exit engine call site not reviewed in full
- `execution_intelligence_runner.py` — only first 200 lines read (version + changelog); scoring logic not audited
- `scripts/avshunter_monetisation_policy.py` — not audited

### Findings not attributable to named patterns
- Catastrophe Gate runs in SHADOW MODE (confirmed in full read). Prior documentation claiming it is a "no-op stub" is incorrect. The gate computes CT fields and writes them to CSV but `ct_position_size_scalar` is NOT consumed by SuperBrain. This is intentional (activate-live flag required). No code finding — but a documentation accuracy issue.
- PSE is confirmed retired (`pse_final_size = 0.0` always). No finding.
- `tastytrade_client.py` was not read (non-trading placeholder per CLAUDE.md). No finding expected.

---

*End of audit. Total findings: 25. Critical: 4. High: 7. Medium: 12. Low: 2.*
