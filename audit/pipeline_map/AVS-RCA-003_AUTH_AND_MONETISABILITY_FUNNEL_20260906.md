# AVS-RCA-003 — Two root-cause investigations

**Issued:** 2026-09-06
**Agent:** Claude Code — read-only on the repository and on the Worker 3 package; writes only under the output root
**Repository:** `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`
**Worker 3 package:** `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\worker3_foundation\`
**Interpreter:** `C:\Python314\python.exe`
**Output root:** `audit\rca\AVS-RCA-003\`
**Two questions, two independent parts.** Deliver Part 1 first (it is short), then Part 2. They share constraints, not evidence.

> **Part 1.** Why is Anthropic API authentication failing for Worker 3 (HTTP 401 on the only live attempt)?
> **Part 2.** At what downstream stage do valid Discovery candidates cease to be monetisable — and is that attrition caused by genuine economics or by pipeline design?

---

## 0. Constraints (both parts)

- **Never execute the pipeline.** No `--evening`, `--morning`, no stage scripts, no Lab server, no Interpreter commands, no MarketData/Polygon/FRED calls.
- **Production code, run data, backups and the Worker 3 package are read-only.** Analysis scripts live under the output root and import production modules read-only.
- **Secrets.** Never print, log, write or echo any API key, token or `.env` value. You may report a key's *prefix pattern* (e.g. "starts with `sk-ant-api03-`"), its *length*, and whether it contains whitespace or a trailing CR/LF. Nothing else. Redact `x-api-key`, `Authorization` and `token=` in every logged request.
- **Part 1 network budget: at most 3 HTTPS requests**, all to `api.anthropic.com`, all specified in §1.4, none of which generates model output or spends tokens beyond a trivial amount. Count them; stop at 3.
- **Part 2 makes zero network requests.** Everything is computed from stored run artefacts and source.
- **Three-direction discipline** in Part 2: every count is split CALL / PUT / OTHER.
- **Evidence standard.** Source claims cite file:line; run claims cite artefact path + filter + count. A claim sheet, a README or this prompt's framing is never evidence.
- **Defects are filed, not fixed.**

---

## PART 1 — Anthropic authentication failure

### 1.1 Known facts (verify each; do not assume)

- `SLICE10_LIVE_AI.md` records one live attempt on 6 Sep: model `claude-sonnet-4-6`, `max_tokens` 2,048, 45 s timeout, result **HTTP 401**, elapsed 327 ms, request hash `7de28efc…`, no retry.
- The transport is `worker3/adapters/anthropic_http.py`, which the notes say reads `ANTHROPIC_API_KEY` at call time, optionally `ANTHROPIC_WORKSPACE_ID`, "does not load production `.env` files", uses "documented Anthropic headers and Messages endpoint", HTTPS only, no redirects.
- The repository's `.env` carries an `ANTHROPIC_API_KEY` that **was previously pasted into a chat conversation and was flagged for rotation** (AVS-INV-001 R-05 and the project's own key-hygiene note). Whether it was rotated, and whether `.env`'s value and the process environment's value are the same key, is unknown.
- Claude Code itself authenticates through its own mechanism, which is unrelated to `ANTHROPIC_API_KEY`; a working Claude Code session proves nothing about that variable.

### 1.2 Hypotheses to test, in order of prior likelihood

| # | Hypothesis | How it would produce 401 | Test |
|---|---|---|---|
| H1 | **The key was revoked** after being exposed in chat, and never rotated in `.env`/the environment | Valid-looking key, rejected server-side | §1.4 request A with the environment key; compare the error body's `error.type`/`message` (`authentication_error` vs `permission_error` vs `invalid_request_error`) |
| H2 | **Wrong variable or empty at call time.** The smoke script ran in a PowerShell session where `ANTHROPIC_API_KEY` was unset, or set from a different `.env` than the one in the repo, or the transport reads a differently-named variable | Header sent empty or absent | Read `anthropic_http.py`: exact variable name(s), fallback order, what happens when unset (should raise before sending — if it sends anyway, that is a defect). Check the smoke script `live_worker3_smoke.py` for how it seeds the environment |
| H3 | **Header form.** The Messages API expects `x-api-key: <key>` plus `anthropic-version: 2023-06-01`. A transport that sends `Authorization: Bearer <key>` instead (OAuth form), or omits `anthropic-version`, or sends both, can 401 | Wrong auth scheme | Read the header construction; compare with the receipt's redacted headers in `03_run_log.txt`/receipt store if retained |
| H4 | **Key type mismatch.** An Admin API key (`sk-ant-admin…`), a Console session token, or a Claude Code OAuth token used where a standard API key (`sk-ant-api03-…`) is required | Wrong credential class | Prefix pattern + length only |
| H5 | **Malformed value.** Trailing `\r`, `\n`, quotes or a BOM from a Windows-edited `.env`; `set`/`$env:` quoting in PowerShell adding literal quotes | Server sees `"sk-ant…"` or `sk-ant…\r` | Byte-level inspection of the value as the transport reads it: `len`, `repr(value[:1])`, `repr(value[-1:])`, presence of `"`/`'`/`\r`/`\n`/`\ufeff` — report booleans only |
| H6 | **Workspace/org scoping.** `ANTHROPIC_WORKSPACE_ID` set to a workspace the key does not belong to, or a header name the API does not accept | 401/403 on scope | Read how the workspace id is sent; test with and without (requests B/C) |
| H7 | **Model name.** `claude-sonnet-4-6` — if the identifier is wrong the API returns 404 `not_found_error`, not 401; if the key's org lacks access it returns 403/`permission_error`. Rule this in or out from the recorded status code and body | — | Body inspection from request A |
| H8 | **Proxy / TLS interception** on the machine rewriting or stripping headers | Header lost in transit | Check `HTTPS_PROXY`/`HTTP_PROXY`/`NO_PROXY` env, Windows proxy settings, and whether `urllib` honours them in the transport |

### 1.3 Static investigation (0 requests)

1. Read `worker3/adapters/anthropic_http.py` end to end. Document: endpoint URL; every header name and its source; the credential variable name(s) and read order; behaviour when the variable is unset/empty; how `ANTHROPIC_WORKSPACE_ID` is used; `anthropic-version` value; timeout; body shape (`model`, `max_tokens`, `messages`, `system`); how the receipt hashes the request; whether error bodies are retained anywhere (the notes say error bodies are not logged — confirm, and if so note that H1/H7 discrimination needs request A).
2. Read `live_worker3_smoke.py` and `tests/test_live_semantic.py`: how the smoke run is invoked, what it does with `--live`, how it seeds the environment, what it prints.
3. Locate every place a key could come from on this machine, **without reading values**: `.env` in the repo (line present? one line or two?), `.env.txt` (should be deleted per AVS-OPS-001 — confirm), user/system environment variables (`Get-ChildItem Env:` filtered by name only), any `.env` under the Worker 3 package. Report presence, source and the prefix/length/whitespace booleans of each. If two sources disagree in length or prefix, that is a finding.
4. Compare the transport's header construction against the API contract as you know it (`x-api-key`, `anthropic-version`, `content-type: application/json`; the Messages endpoint `POST /v1/messages`). List every discrepancy.

### 1.4 Live discrimination (≤ 3 requests)

Only after §1.3. Each request is minimal and logged with redacted headers, status, latency and the **full error body** (error bodies contain no secret and are the diagnostic).

- **Request A — the cheapest possible authenticated call:** `GET https://api.anthropic.com/v1/models` with `x-api-key` from the environment value the transport would use and `anthropic-version: 2023-06-01`. A 200 proves the key is live and lists the models the org can see (check whether `claude-sonnet-4-6` appears). A 401 with `authentication_error` → H1/H4/H5. A 403 → scoping. This costs no tokens.
- **Request B — only if A returned 200:** the same `GET /v1/models` with the `ANTHROPIC_WORKSPACE_ID` header exactly as the transport sends it. Discriminates H6.
- **Request C — only if A and B returned 200:** a minimal `POST /v1/messages` through the transport's own code path (`max_tokens: 8`, one-word user message, the model the smoke run used). This reproduces the original failure conditions exactly. If it succeeds, the 6 Sep failure was environmental (H2/H5) and the notes should say so.

If request A returns 401, **stop** — B and C cannot add information, and the answer is H1/H4/H5 discriminated by the body and the static checks.

### 1.5 Deliverable — `PART1_AUTH_RCA.md`

- Root cause as one hypothesis ID with the evidence chain; alternatives ruled out with the evidence that ruled them out.
- The exact fix, stated for the operator: rotate the key in the Anthropic Console (**recommended regardless of root cause**, because the key was exposed), place it in the single agreed location, remove any duplicates, and re-run `live_worker3_smoke.py --live` once.
- Any transport defects found (e.g. sending an empty header instead of raising; missing `anthropic-version`; not surfacing the error body) filed to `DEFECTS.csv`.
- Requests made (≤ 3) with redacted logs.

---

## PART 2 — Where do valid Discovery candidates stop being monetisable, and why?

### 2.1 The question, made precise

"Monetisable" in this project means (AVS-AUD-001, AR-003 §7.10, AVS-SD-003 F11): **directionally honest + economically eligible + executable + timely + positive-expectancy**, with execution viability a hard authority and scenario profitability advisory. The pipeline turns ~3,300 tickers into ~1,600 Discovery survivors into ~290 Lab rows, of which roughly 110 are `MONETISABLE`, 105 `NOT_MONETISABLE`, 22 `DATA_MISSING`, 19 `LIMITED` (run `20260905_151448` figures from RCA-002/QT-001 — recompute them), and zero carry `BUY_NOW`/`BUY_SMALL` until Morning. The operator's question is where in that funnel a candidate that Discovery correctly identified loses monetisability, and — for each loss — whether the reason is:

- **ECONOMIC** — the option market genuinely does not offer a positive-expectancy long single-leg structure for that thesis (spread too wide relative to expected move, premium too large relative to target, insufficient DTE for the hold, no liquid strike near the geometry);
- **DESIGN** — the pipeline's own rules, data contracts or ordering discard it (a threshold that is an artefact, a missing field defaulting to a fail, a gate applied on the wrong quantity, a valuation model that cannot represent time value, an alias mismatch, a stage running before its input exists);
- **DATA** — the provider did not supply what the rule needs (no chain, no quote, stale bars), so the rule could not evaluate.

A candidate lost to DESIGN or DATA is opportunity cost the operator can recover; one lost to ECONOMIC is the market telling the truth. Getting this classification right per stage is the deliverable.

### 2.2 Inputs

**Runs** (all read-only): `20260905_151448` (primary — latest, post-cycle-1), `20260904_122358` (cycle-1 code, different session), `20260904_004338` (pre-build baseline, for contrast). If a run after the DDD closure exists when you start, add it and make it primary.

**Per run:** Discovery output and `dropoff_audit_*.json`; Vanguard `vanguard_signals_enriched_*`; Options Intelligence CSV plus `governed_direction_records_*.jsonl`, contract selection diagnostics, stand-down reasons, the option-chain datasets referenced in `dataset_registry`; EIL/execution stage CSVs; `eod_candidate_*` and `eod_dropoff_audit_*`; `morning_candidates_*`; the Lab book; `handoff_contract_audit_*`; `run_meta.json`, `final_run_manifest.json`. For the Morning path, the most recent Morning artefacts that exist (`20260901_082437` is the last accepted; note its code age).

**Source:** `avshunter_discovery_ULTIMATE.py` (what "selected" means, the `win_probability` heuristic), `scripts\avshunter_options_intelligence.py` (contract selection `select_best_contract` and its quality gates, `compute_trade_economics`, `derive_verdict`, the target ladder `:4138-4158`), `contracts\selected_contract_economics.py` (monetisability — the **expiry-intrinsic** valuation AR-003 §7.10 flagged), `contracts\long_option_policy.py` (spread/quote thresholds), `execution_gate.py`, `eod_candidate_engine.py` (status ladder, candidate filter, `max_candidates`), `morning_gate.py` (Morning economics recompute), `macro_horizon_router.py` (hold), `contracts\lab_control.py`.

**Prior findings to verify, not inherit:** AVS-FIND-001 (Aug 2026) named live-quote hydration failure as the #1 monetisability blocker (58.6% of dropoff rows) and `select_best_contract()` failing ~55% of candidates; AR-003 §7.10 says intrinsic-only monetisability "can classify an ATM/OTM option as not monetisable even though delta, remaining time and IV would give it positive market value at the target before expiry"; AVS-REV-003 found `derive_verdict` demoting on legacy R:R (since removed — confirm) and unit chaos across spread bases; RCA-002 A4 found 22 `DATA_MISSING` monetisability rows all with a missing structural target.

### 2.3 Method

**Step 1 — Define "valid Discovery candidate".** From `avshunter_discovery_ULTIMATE.py` and the Discovery CSV: the exact selection rule, and the split of the ~1,600 selected by tier, direction (CALL/PUT/UNRESOLVED at Discovery), composite band and sector. Also state what Discovery *cannot* know (it has no options data) so that "valid" is understood as *thesis-valid*, not *trade-valid*.

**Step 2 — Build the per-ticker cohort table.** One row per Discovery-selected ticker per run, keyed on ticker (and `trade_idea_id`/`thesis_id` where it exists), with a column for its state at every boundary:

`discovery_selected → vanguard_row → vanguard_verdict → options_row → direction_at_options → contract_selected (Y/N + reason) → economics_state → options_verdict → eil/execution_verdict → eod_status → capital_permission → lab_row (Y/N) → monetisability_state + reason → execution_viability_state → final_action`

Every transition where a ticker leaves the funnel gets a `loss_stage` and the **exact reason code the pipeline recorded** (not your inference). `02_cohort_<run_id>.csv`.

**Step 3 — The funnel.** From the cohort table, produce `03_funnel_<run_id>.csv` and a Sankey-style table in the report: survivors and losses at each boundary, three-direction split, and losses grouped by reason code with counts. Reconcile: every Discovery-selected ticker appears exactly once as a survivor or a loss (`input = processed + excluded + deferred + exceptions` at every boundary — flag any boundary that does not reconcile, that is itself a design finding).

**Step 4 — Classify every reason code.** For each distinct loss reason in Step 3, decide ECONOMIC / DESIGN / DATA with a one-paragraph justification citing the source line that emits it and the rule it applies. Where a reason code is a *mixture* (e.g. `NO_CONTRACT_PASSED_QUALITY_GATES` bundles spread, OI, delta band, DTE and missing-quote failures — RCA July 2026 said its sub-causes were never broken out), **break it out** by re-evaluating the individual gates on the stored chain data for the affected tickers and attribute each ticker to the first gate that failed. Produce `04_reason_classification.csv`: `reason_code, stage, source_file:line, rule, class, tickers_affected (C/P/O), justification`.

**Step 5 — Test the biggest DESIGN suspects quantitatively.** These are hypotheses; measure them.

- **S1 — Intrinsic-only monetisability (AR-003 §7.10).** For every `NOT_MONETISABLE` Lab row with a selected contract and a live-enough quote, re-value the option **at the structural target on the planned hold's final session** with time value retained (Black–Scholes with the quote's implied vol held constant, rate ≈ 0, dividends ignored; state assumptions), and recompute R:R and the profit floor. Report how many flip to `MONETISABLE`/`LIMITED` under a time-value model, by direction and by moneyness/DTE bucket. If the flip rate is large, the loss is DESIGN (valuation model), not ECONOMIC. Also run the reverse: how many `MONETISABLE` rows would fail under the time-value model (intrinsic can also *over*-state).
- **S2 — Contract selection.** For tickers where `select_best_contract` failed or chose a contract whose economics then failed, examine the stored chain: did a strike/expiry exist that would have passed the quality gates *and* the economics? Count "a viable contract existed but was not chosen" (DESIGN) vs "no contract on the chain could pass" (ECONOMIC) vs "chain absent/empty" (DATA). Look specifically at the DTE band relative to the governed hold and at the delta band — are the bands appropriate for a 1–5-session hold?
- **S3 — Target ladder and geometry.** RCA-002 showed PUT targets fall through to the stop-dependent rung far more often than CALL (42 vs 12 blank targets). Quantify how many PUT candidates lose monetisability *because* the target is derived from `3 × stop_dist` rather than from a structural level, and whether the resulting R:R is systematically different from CALL's. A direction-asymmetric loss with symmetric market conditions is DESIGN.
- **S4 — Spread and quote thresholds.** For rows failing spread (`long_option_policy`): distribution of spread-as-%-of-mid by direction and by underlying price. Is the 15% (or whatever the live threshold is) a cliff that a slightly different denominator or a size-aware rule would change materially? Compare against the actual fill-quality evidence in the trade journal, if any exists.
- **S5 — Ordering effects.** Horizon runs after Options (AR-003 §5.1); GARCH is patched after EIL. Identify any candidate whose economics were computed with a hold/DTE assumption that the later Horizon stage then changed. If the count is non-zero, that loss is DESIGN (stage order).
- **S6 — Data availability.** For every DATA-classified loss: which provider field was absent, whether the canonical cache had it for another session (i.e. transient), and whether a retry/defer would have recovered it. Split provider `no_data` (market truth) from adapter/identity failures (pipeline).
- **S7 — Morning attrition.** On the most recent Morning artefacts: of rows that were `MONETISABLE` at EOD, how many stay viable at Morning, and what kills the rest — overnight gap through invalidation (ECONOMIC), quote no longer executable (ECONOMIC/DATA), Morning recomputing economics on a different basis than EOD (DESIGN — AVS-REV-003 mechanism 2), contract identity mismatch (DESIGN)?

**Step 6 — Expectancy check on the survivors.** For the rows that *are* `MONETISABLE` and viable: what does the pipeline claim about them (R:R, target distance in ATR, DTE vs hold, premium as % of underlying) and is there *any* realised-outcome evidence (trade journal — 14 closed trades, dormant since 18 Jul; the Decision/Outcome Ledger if it has captured anything since the DDD integration) that speaks to whether "monetisable" rows have made money? Be explicit that n is too small for inference; report what exists.

### 2.4 Deliverable — `PART2_MONETISABILITY_RCA.md`

1. **The answer to the question in two sentences**: the stage(s) where most valid candidates cease to be monetisable, and the ECONOMIC / DESIGN / DATA split of that loss with counts, for the primary run.
2. The funnel table with three-direction splits and reconciliation.
3. The reason-code classification, ordered by tickers lost.
4. The S1–S7 results, each with method, numbers and a verdict.
5. **Recoverable opportunity**: how many Discovery-valid candidates per run are lost to DESIGN or transient DATA, and what single change would recover the most (ranked).
6. **What is genuinely economic**: the losses the operator should accept, and what they say about the universe/strategy fit (e.g. if most losses are wide spreads on low-priced names, that is a universe-definition question, not a pipeline defect).
7. Defects filed (`DEFECTS.csv`), each with severity, file:line, the design clause violated, and the tickers/rows that demonstrate it. Design questions that are not defects (e.g. "should monetisability use a time-value model?") go in a separate **decisions-for-ACK** list with the evidence for each option.
8. Limits: what could not be determined without a Morning run on current code, without a warm-cache rerun, or without outcome data.

---

## 3. Output layout

```
audit\rca\AVS-RCA-003\
  environment.json
  PART1_AUTH_RCA.md
  part1_requests_redacted.jsonl        (≤ 3 entries)
  PART2_MONETISABILITY_RCA.md
  02_cohort_<run_id>.csv               (one per run)
  03_funnel_<run_id>.csv
  04_reason_classification.csv
  05_s1_timevalue_revaluation.csv
  05_s2_contract_selection.csv
  05_s3_target_asymmetry.csv
  05_s7_morning_attrition.csv
  scripts\                              (read-only analysis scripts)
  DEFECTS.csv
  DECISIONS_FOR_ACK.md
```

Finish Part 1 by printing the root-cause hypothesis ID, the fix, and the request count. Finish Part 2 by printing the two-sentence answer, the top three recoverable losses, and the top three genuinely economic ones.
