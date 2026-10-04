# BEH-001 Phase 2: candidate-level handoff and duration (design, 1 Oct 2026)

**Parents:**
- `AVS_SD_BEH_001_BEHAVIOURAL_SIGNAL_CANDIDATES_20261001.md`
- A2 register and Part 4 decisions (C-01, C-02, C-03 handoff, C-04, C-05, C-07, RQ-3)

**ACK principles:**
- Assembly line: each stage adds value and imposes no constraint it doesn't own.
- Every ticker re-enters the line as new each run, even when a trade is open.
- Outcome or failure ends a stage, not the ticker.

## 1. Facts found (read-only maps, 1 Oct)

| Stage | Unit and identity today | Duplicate behaviour |
|---|---|---|
| Discovery → manifest / packages | one row per ticker; `canonical_manifest.py:275`, `build_packages_from_discovery.py:314` | silently keeps the first row |
| Vanguard | one package → one row per ticker; statistics come from a state-matched cohort, not candidate geometry | Phase 8.5 index is ticker-keyed, last row wins (`actuarial_enrichment_pass.py:809`) |
| C5 / C6 / C8 | `thesis_id = run:ticker:session:DISCOVERY`; 20-session caps (`expression_candidate_packet.py:133`, `expression_valuation_packet.py:61`) | raises on duplicate tickers |
| Options | one `ctx['direction']` per ticker; `thesis_id = TICKER:SIDE:session:OLM2`; chain cached once per ticker per session (110 days) | `merge on ticker` fans out (:10475); DOI `drop_duplicates('ticker')` (`dynamic_options_production.py:154`) |
| EOD, Morning, Lab | maps keyed by ticker, last row wins; trigger overlay raises; Morning modes already keyed by (ticker, thesis_id) | mixed |

**Population (eval_v3 replay, 276 tickers × 102 cuts):**
- 90% of read tickers have at least one live directed candidate on any day (p10–p90: 85–93%).
- Median 3 candidates per ticker (p90 6); 38% of tickers have both sides live.
- 14% of live candidates are ACTIVATED.

**Duration evidence** (`config/beh001_duration_evidence_v1.json`, 209 published groups) shows two things:
- Remaining time depends on age. For example, a daily campaign SOS→LPS aged 0–2 bars takes a median 9 bars to activation (80% within 22); aged 21+, a median 4 (80% within 15).
- Outcomes often run beyond 20 sessions. For daily SOS→LPS: median 14 bars, 80% within 45 bars after activation.

## 2. Consequences
1. **C-02 as written filters almost nothing.** "Survive if at least one directed candidate" puts about 90% of the universe into Vanguard and Options every run. Credits are affordable: about 1 credit per chain, against a 100k/day budget. Run time is not: Options, EOD and Morning would grow several-fold.
2. **A per-row switch would break or silently truncate at five or more stages.** Changing the unit from ticker to candidate everywhere at once is a rebuild, which CLAUDE.md rule 4 forbids, and a partial deployment.
3. **Vanguard's per-ticker statistics are a real per-ticker fact**, a cohort of similar market states. They should stay one row per ticker and be joined to each candidate, not duplicated.

## 3. Design: a candidate lane beside the ticker spine

The ticker spine (Discovery row → manifest → Vanguard → C5 → Options → EOD / Morning) is unchanged until increment 2C. Candidates travel in their own lane and join the spine where a stage owns a candidate fact.

### 2A. Candidate packet (additive; display and measurement only)
- **New frozen artefact** after Vanguard: `runs/{id}/forecast/behavioural_candidate_packet_v1/packet.json`, plus a CSV. Contents:
  - one record per **live directed** candidate (DETECTED or ACTIVATED) for **every ticker read**;
  - a separate `monitoring` list (MONITOR and OUTCOME_REACHED observations, C-02);
  - FAILED candidates are listed with their successor link.
- **Each record carries:**
  - candidate fields, including outcome, duration and ledger fields;
  - Discovery outcome, reason and tier as attributes (C-01: never a gate);
  - the ticker's Vanguard fields joined by ticker, or `VANGUARD_NOT_RUN: <reason>` (C-07);
  - `governance__*`.
- **Handoff status per candidate:** `ROUTED_TO_EXPRESSION`, `DEFERRED_RESOURCE:<rank>`, `MONITOR_ONLY`, or `NOT_ROUTED:<reason>`. Resource deferral is never behavioural rejection (C-07).
- **Owner:** a new pure builder `domain/structure_behaviour/handoff_packet.py`, plus a writer in the orchestrator next to the C5 freeze. No other stage reads it in 2A except the Lab, for display.

### 2B. Expression search per candidate inside Options (measurement; existing outputs untouched)
- For each ticker already in Options scope, the chain is fetched once (existing cache). Each routed candidate on that ticker is evaluated with the existing contract selection, using the candidate's side, invalidation, outcome level and remaining-duration evidence as attributes.
- **Runway is unchanged:** the existing runway policy stays the authority. The candidate's duration is shown beside it; using duration to set runway is C-06, phase 3.
- **Output:** `options_candidate_expressions_{run}.csv`, one row per candidate, with contract or no-fit reason and liquidity verdict (C-01: liquidity is an Options attribute).
- The existing per-ticker `options_intelligence_*.csv` and everything downstream stay byte-identical. A test pins this.

### Capacity and ordering (R11: rank, don't gate)
- Options' existing scope (tier and Vanguard support) decides which tickers get chains today. That is an existing constraint, recorded on each candidate, not new.
- **Ordering inside scope:**
  1. ACTIVATED first, since the trigger has fired;
  2. then DETECTED by the shortest median remaining time to activation;
  3. then Candidate_ID.
  This uses behaviour and time only; no unvalidated "edge" score.
- **Capacity:** `config/beh001_handoff_v1.json → expression.max_candidates_per_run`. Beyond it, candidates are `DEFERRED_RESOURCE` with their rank.

### 2C. Candidate authority downstream (requires ACK approval; not built in 2A/2B)
- **Thesis identity becomes candidate-aware:**
  - `thesis_id = run:ticker:session:CAND:<sha12(Candidate_ID)>` for C5 and Options;
  - OLM `TICKER:SIDE:session:<sha12>:OLM3`, with the legacy id kept as an alias.
- **Every ticker-keyed join is re-keyed to `thesis_id`.** Sites: C5 / C6 / C8 duplicate checks; Options merge and enriched merge; DOI `drop_duplicates`; Phase 8.5 index; EOD maps and trigger overlay; Morning maps; Lab maps; handoff finalizer.
- **C-01 / C-02 survivor switch** happens only here, with the capacity ordering above, so the population never exceeds what the line can process. The projected run time is measured first, on a full-universe dry run with `--plan-only` plus an offline Options timing.
- **The 20-session caps in C6 and C8 become candidate duration evidence** (C-04 completion). This amends ACK D2 and TEV-001 §5.2.

### Duration (C-04, C-05, RQ-3): built in phase 2
- `domain/structure_behaviour/duration.py` attaches remaining time to activation (DETECTED) or to outcome (ACTIVATED), by age bucket, then all ages, then UNESTIMATED, and only if the evidence is causal.
- Evidence builder: `Enhancements/direction_evidence/beh001_duration_evidence.py`.
- The existing Vanguard 5/10/20 statistics stay as supplementary, unchanged.
- **Promotion of the evidence builder** into the pipeline (refreshing evidence on a schedule) is deferred. The evidence file is versioned and hashed; refreshing it is an offline step until then.

## 4. Order and acceptance
1. **Duration:** done; tests `tests/test_beh001_duration.py` (7).
2. **2A candidate packet:** tests first.
   - Every live directed candidate of every read ticker appears exactly once.
   - Monitoring is separate.
   - Vanguard fields join by ticker without duplicating Vanguard.
   - The C5 packet and Vanguard outputs are byte-identical before and after.
   - A packet failure never fails the Evening; it is recorded in the manifest.
3. **2B expression search:** tests first.
   - One row per routed candidate; the chain is fetched once per ticker.
   - The existing Options outputs are byte-identical.
   - Opposite-side candidates on one ticker are both evaluated.
   - Deferral is recorded with its rank.
4. **2C:** separate approval. Then build with a characterisation test at every re-keyed site, and replay one stored run end to end.

Production direction stays on `legacy_rollback` throughout 2A and 2B.
