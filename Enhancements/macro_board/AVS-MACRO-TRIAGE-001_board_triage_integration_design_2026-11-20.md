# AVS-MACRO-TRIAGE-001: ETF Macro Board ↔ Lane B triage integration

**Status:** approved by ACK on 20 Nov 2026 (open points 1 and 2: "Approved"; pre-open build moved to 12:00 UK). T1, T2, T3, T5, T6 and T7 built 20 Nov 2026 (not committed); T4 is prompt text for ACK.
**Owner:** Claude Code (ACK, 20 Nov 2026: "I want Claude Code to make the enhancements because I want to integrate the Update board with the triage board").
**Authority:** CLAUDE.md rule 6 as amended 20 Nov 2026. The board identifies, explains and orders. It never changes a pipeline gate, score, rank, contract selection or trade direction, and never places or sizes a trade. The Lab rank (`lab_rank`), contract and side in the hand-off are untouched.
**Acceptance (working rules, 20 Nov 2026):** a change is accepted when it shows the source data correctly and serves the human review, checked against the source files. Nothing is scored.

## 1. Problem

The Lane B triage (four Claude chats, one per batch, from the daily triage prompt) fills five macro columns by hand: `money_tag`, `macro_sector_agreement`, `macro_scenario_ids`, `macro_kill_switch` and `sector_check`.

The chats are told to read "the macro board". That is the 6.6 MB board HTML with its data embedded, so they take macro facts from it loosely and mostly fall back on the LLM macro packet. On 19 Nov:
- `macro_scenario_ids` and `macro_kill_switch` held the same packet summary on every row.
- `sector_check` was a pre-market price note.
- The merged weekly triage board took its sector stances (LEAN IN / AVOID / MIXED), side fit and MACRO RE-CLASS from the packet's lead and avoid lists alone.

The packet said LEAN IN for XLY. By 14:42 ET XLY was the worst sector (-2.2%). None of the board's measured intelligence reached the triage: money flow and its record, reasons for and against with sources, live scenario triggers, events, option footprints. Nothing showed that the stance came from a single LLM source with measured evidence against it.

Timing makes it worse:
- The triages ran around 10:20 UK, before the pre-open board build (then 09:05 ET, 14:05 UK). They read the previous evening's build, or an older one if that failed. **ACK, 20 Nov 2026: the pre-open build moves to 12:00 UK** (07:00 ET; `config/macro_build_schedule_v1.json` `pre_open_minutes` 25 → 150), so a triage started after about 12:10 UK reads that morning's macro.
- The merge then re-aligns to the newer macro by hand.

## 2. Design

### 2.1 Board build writes its per-ETF intelligence (macro_board)

Every current board build writes `macro_board/output/etf_intelligence/etf_intelligence_<as_of_session>_<build_kind>.json` and `etf_intelligence_latest.json`, using an atomic write. They hold a compact, versioned projection (`etf_intelligence_v1`) of what the board already computes, per sector and industry ETF (the 26 in `config.rotation`). Nothing new is measured.

Build metadata: `as_of_session`, `build_kind` (MORNING / EVENING / OFF_SESSION), `built_at_utc`, `next_session`, `macro_packet_id`, and the source as-of times.

Per ETF:

| Field | From (existing owner) | Source label |
|---|---|---|
| `flow`, `flow_text`, relative 1/5/20 | `day_story.money_flow` | MEASURED |
| `flow_record` (FOLLOWS / REVERSES / NO_CLEAR_RECORD / THIN) and its text | `day_story.persistence_verdict` / `persistence_text` | MEASURED |
| `stance_measured` (LEAN IN = in / turning in; AVOID = out / leaving a leader; NEUTRAL = no flow; MISSING) | derived from `flow` | MEASURED |
| `stance_packet` (TAILWIND / HEADWIND / MIXED / NONE) and the packet's lead/avoid membership | `rotation.packet.bias`, `intel.packet.sector_lead` / `sector_avoid` | LLM (macro packet) |
| `stance_agreement` (AGREE / DISAGREE / ONE_SOURCE / MISSING) | the two above | — |
| `reasons_for`, `reasons_against`: top 2 each, as text plus source | `day_story` drivers (fit), footprint, published items | MEASURED / PUBLISHED (LLM) |
| `echo_note` | an LLM item (USMI, events, news) that only repeats the measured read is marked "echo of our measured sheet", not confirmation | — |
| `live_scenarios`: id, state, side, verdict, whether it beats the tries | `scenario_watch.live` | MEASURED |
| `events_next_close` | `decision_points.calendar` (`sessions_ahead` ≤ 1) | MEASURED (FRED calendar) / PUBLISHED |
| `decision_scenarios`: continuation, reversal, alternative, stand aside; each with trigger, invalidation and horizon in sessions | `day_story.trade_idea` (continuation and invalidation), `flow_record` (reversal), the strongest cross-asset driver (alternative), flow NONE / MISSING (stand aside) | MEASURED |
| `kill_level`: the ETF level that voids the measured stance | the trade idea's invalidation level | MEASURED |
| `build_age_note` | build kind and time | — |

Missing is never neutral: a field without data says MISSING with the reason.

### 2.2 Join step: one macro row per hand-off name (new module `macro_board/triage_context.py`)

A CLI that is read-only on its inputs:

```
venv\Scripts\python.exe -m macro_board.triage_context --handoff <folder>
```

It reads `handoff.csv`, its `receipt.json` and `etf_intelligence_latest.json`. It writes `triage_macro_context_<session>.csv` and a `.json` with the build metadata into the hand-off folder (atomic write, overwritten on refresh). Reused:
- `day_story.candidate_links` for the side-versus-flow reading;
- the price store and the board's correlation code for stock-to-ETF links.

One row per hand-off row (row count = `handoff.csv` rows, keyed by `lb_ledger_id`):

| Column | Meaning |
|---|---|
| `session`, `ledger_id`, `ticker`, `side`, `lab_rank`, `lb_batch`, `lb_order` | copied from the hand-off |
| `sector_etf` | the hand-off's `sector_etf`; MISSING when absent |
| `board_as_of_session`, `board_build_kind`, `board_built_at_utc` | which build fed the row |
| `link_corr_60d`, `link_beta_60d`, `link_state` | the stock's daily-return link to its sector ETF (LINKED ≥ 0.4, WEAK, MISSING); reuses the 0.4 config value |
| `side_fit_measured` | WITH_FLOW / AGAINST_FLOW / STOCK_SPECIFIC / NO_FLOW_READ / NO_SECTOR (`candidate_links`) |
| `side_fit_packet` | WITH / AGAINST / MIXED / NO_READ from `stance_packet` against the side |
| `money_tag` | one word for the side: WITH, MIXED or AGAINST. Measured and packet agree → that word; they disagree → MIXED; one missing → the other, with a note; stock-specific → MIXED with a note |
| `money_why` | one line citing both readings and their sources |
| `macro_sector_agreement` | `stance_agreement`, with the two stances |
| `macro_scenario_ids` | the ETF's live scenario ids and states, plus decision-scenario labels |
| `macro_kill_switch` | the ETF `kill_level` sentence, e.g. "measured AVOID on XLK void above 205.30 (15:50 ET close)" |
| `sector_check` | flow text, volume, record and build time |
| `reasons_for`, `reasons_against`, `echo_note` | from the ETF, with source labels |
| `events_next_close` | from the ETF |
| `macro_view_order` | an ordering by fit (WITH → MIXED → AGAINST → no read), then `lab_rank`. Display only; it never replaces `deep_mine_rank` or `lab_rank` |

### 2.3 When it runs

- **`avs_day.ps1`:** before the triage, the step that prepares packs (or a new `macro` step) runs the join for the session's hand-off. `Write-Context` adds `macro_context` (path) and `macro_context_built` (board build time) to `today_context.json`.
- **`Run-MacroInputs.ps1`:** after the board step, it refreshes the join when the next session's hand-off exists. That way the 12:00 UK pre-open build refreshes the file shortly after the hand-off exists (from about 10:40 UK), before the triage and the merge. Trade-off: the 08:30 ET (13:30 UK) releases arrive after this build; the opening check and material-change builds pick up the cash reaction.
- **`avs_day.ps1 board`:** runs the join after its rebuild. The "re-tag money by hand" message is replaced by "macro context refreshed: N names changed money_tag".

### 2.4 Triage prompt (text ACK pastes; no file change)

Replace "the macro board" in each batch prompt with:

> the board's macro context for this session (`macro_context` in today_context.json, one row per hand-off name by ledger_id). Fill money_tag, macro_sector_agreement, macro_scenario_ids, macro_kill_switch and sector_check from that name's row, keeping its source labels and build time; do not write macro text by hand.

The merge instruction ("merge <date>") gains:
- Read the latest `macro_context`.
- Take the sector summary and "Where the money is today" from its ETF rows, each line labelled MEASURED or LLM (macro packet).
- Each MACRO RE-CLASS cites the field that changed between the triage's build and the latest one.

### 2.5 `check_triage.py`: new check `macro` (WARN only, never FAIL)

For each triage row with a `ledger_id` in the macro context file:
- the first word of `money_tag` equals the file's `money_tag`;
- `macro_kill_switch` and `macro_sector_agreement` contain the file's values;
- the file's `board_built_at_utc` is the newest build available when the triage was written.

A hand-typed or stale value is a WARN with the file's value beside it. When the file is missing, the WARN says the board context was not available.

### 2.6 Board shows the triage (Day story)

The Day story "Ticker impact" section reads the macro context file for the next session when it exists, instead of `options_candidates_ranked.csv`. It lists the triaged names by batch against their ETF's flow and scenarios, and links each name to its deep-dive card when the hand-off folder has one.

## 3. Out of scope (ACK, 20 Nov 2026)

- Options monetisation (stays with the tradeability track).
- Scoring, edge tests and outcome attribution.
- Changes to the three ChatGPT automations or their schedules.
- The local News Terminal code and the M&A cockpit.

## 4. Build order (one step at a time, each checked before the next)

| Step | What | Files |
|---|---|---|
| T1 | Per-ETF intelligence file written by every board build | `macro_board/build_board.py`, new `macro_board/etf_intelligence.py`, config `etf_intelligence` |
| T2 | Join step and per-name file | new `macro_board/triage_context.py` |
| T3 | Context wiring and refresh | `data/scratch/workaround/avs_day.ps1`, `Run-MacroInputs.ps1` |
| T4 | Prompt sentence and merge instruction (ACK pastes) | none |
| T5 | `macro` check | `data/scratch/workaround/check_triage.py` |
| T6 | Day story ticker impact from the triage | `macro_board/day_story.py`, template |
| T7 (after T1–T6) | Intelligence items from the 20 Nov review, added to the same projection: surface the event file's market perception, alternative explanation, invalidation, consensus and beneficiaries (tolerant field-name reader); USMI counter-evidence and triggers; peer and sector benchmarks | `review.py`, `build_intel`, `etf_intelligence.py` |

The 10-session clean-up (`config/macro_retention_v1.json`) adds `macro_board/output/etf_intelligence` as an age target. The per-name files live in the hand-off folders, which Lane B owns.

**T1 status (20 Nov 2026): BUILT, verified, not committed.**
- `macro_board/etf_intelligence.py`: `project()` and `write()`; `build_board.write_etf_intelligence` runs after the board HTML and the Lab macro desk publication. A failure prints `ETF INTELLIGENCE NOT WRITTEN` and keeps the board.
- Config section `etf_intelligence` (version and max_reasons); horizon from `day_story.driver_horizon`.
- Stances: measured LEAN_IN / AVOID / NEUTRAL (measured, no edge) / MISSING. Packet stance comes from the lead/avoid lists plus the rotation bias; CONFLICTED when they oppose. Agreement: AGREE / PARTIAL (one side neutral) / DISAGREE / ONE_SOURCE (packet silent) / PACKET_CONFLICTED / MISSING. PARTIAL and PACKET_CONFLICTED were added to the design's list: a neutral side is not a disagreement and not an agreement.
- Retention: an `age` target can `keep` named files, so `etf_intelligence_latest.json` is never aged out.
- Tests: `macro_board/tests/test_etf_intelligence.py` 13 pass; `tests/test_macro_retention.py` 9 pass; every test file importing `build_board` passes (6 files, 164 tests).
- Acceptance on the real 19 Nov EVENING build:
  - XLF (inflow), XLK (outflow) and XLE (no read): 37 field checks against the board payload, 0 mismatches.
  - Packet lead/avoid for all 26 ETFs match the archived packet bytes the build read (`13ab6f2cb50e16ef_macro_intelligence_latest.json`): 0 mismatches.
  - Kill level equals the trade invalidation for all 26.
  - On 19 Nov: XLC measured LEAN_IN against packet AVOID gives DISAGREE; XLY LEAN_IN against packet MIXED gives PARTIAL; 15 industry ETFs are ONE_SOURCE because the packet does not name them.

**T2 status (20 Nov 2026): BUILT, verified, not committed.**
- `macro_board/triage_context.py`: `build_rows()`, `run()`, and the CLI `python -m macro_board.triage_context --handoff <folder> [--intelligence <file>]`. It writes `triage_macro_context_<session>.csv` (one row per hand-off row) and `.json` (board build, counts, per-sector summary for the merge, authority) atomically. A missing hand-off or board file stops with exit code 2 and writes nothing.
- Reused code:
  - `day_story.candidate_links` for side against relative performance;
  - `money_index.beta_corr` on the price store for the 60-session link (bars up to the board's session);
  - 0.4 from `session_plan.min_link_corr`.
- Additions to the design, each so that missing is not shown as neutral:
  - `side_fit_measured` adds NO_SIDE (direction UNRESOLVED), NO_BOARD_READ (the sector ETF is not in the board's 26) and LINK_MISSING (no price link);
  - `money_tag` adds NO_SIDE and NO_READ;
  - `board_session_note` says MATCH, OLDER_BUILD or NEWER_BUILD against the hand-off session;
  - `contract_symbol` is copied.
- `money_tag` table:
  - stock-specific → MIXED;
  - measured no edge → MIXED;
  - packet neutral or self-conflicted → MIXED;
  - agree → that word;
  - differ → MIXED;
  - one side missing → the other side's word, with a note.
  - `money_why` never says "agree" unless both lean the same way.
- Tests: `macro_board/tests/test_triage_context.py`, 19 pass.
- Acceptance on a copy of the real 19 Nov hand-off (2,593 rows) with the 19 Nov EVENING intelligence:
  - Row count and ledger-id order equal `handoff.csv`.
  - Ten names across batches 1–4: 119 field checks, 0 mismatches. Copied fields match `handoff.csv`, and agreement, packet fit and kill level match `etf_intelligence_latest.json`. `link_corr_60d` matches an independent SQL + numpy recomputation to 4 decimals.
  - money_tag: MIXED 1,566, NO_SIDE 435, WITH 325, AGAINST 213, NO_READ 54.
- Open (for T7): 51 names whose `sector_etf` is the ETF itself (SPY, TLT, GLD, MTUM, IBIT and others) get NO_BOARD_READ, because T1 covers only the 26 rotation ETFs. The board already measures several of them.

## 5. Tests (written first, business-rule names)

- **T1:** the projection carries every ETF in the rotation config. A missing flow is MISSING, never NEUTRAL. The packet stance is labelled LLM and the measured stance MEASURED. Disagreement is DISAGREE, not averaged. An LLM item that only repeats our measured read is marked as an echo. Each decision scenario has a trigger, an invalidation and a horizon. Historical `--as-of` builds never replace `etf_intelligence_latest.json`.
- **T2:**
  - one row per hand-off row, `ledger_id` unique and matching the hand-off;
  - the Lab rank, side and contract are copied unchanged;
  - `macro_view_order` never alters `lab_rank`;
  - `money_tag` follows the agreement table;
  - a stock-specific name is MIXED with a note;
  - a missing `sector_etf` is NO_SECTOR, and a missing board file stops with a clear message (no partial file);
  - the file states its build kind and time;
  - refresh overwrites atomically.
- **T3:** `today_context.json` carries `macro_context` and `macro_context_built`. The runner plan shows the refresh step after the board; it is skipped with a note when no hand-off exists for the next session.
- **T5:** matching columns pass; a hand-typed `money_tag` that differs is WARN; a triage built from an older build is WARN; a missing file is WARN, never FAIL.
- **T6:** the Day story lists triage names when the file exists, and falls back to the pipeline candidates file otherwise, labelled.

## 6. Acceptance against the source files (per step)

- **T1:** for 3 ETFs (one inflow, one outflow, one no flow), every field matches the board payload of the same build and the macro packet it read, field by field.
- **T2:** row count equals `handoff.csv` rows. For 10 names across the 4 batches, the copied fields match `handoff.csv`, the macro fields match `etf_intelligence_latest.json` for the name's ETF, and `link_corr_60d` matches a recomputation from the price store.
- **T3–T5:** one real session end to end: hand-off → join → triage (ACK's chats) → `checktriage`. On a matching triage the WARN list has no macro lines; on a hand-typed one it has them.
- **T6:** the Day story shows the same names and fits as the per-name file.

## 7. Decisions (ACK, 20 Nov 2026)

1. `money_tag` when measured and packet disagree: MIXED, with both readings in `money_why` (approved).
2. The join runs in the existing `packs` step of `avs_day.ps1` (approved).
3. The pre-open full build runs at 12:00 UK, 07:00 ET (approved: "We want to change 12pm UK").

**T3 status (20 Nov 2026): BUILT, verified, not committed.**
- `avs_day.ps1`:
  - `today_context.json` gains `macro_context` (the per-name CSV), `macro_context_built` (the board build it came from), `macro_context_note` (MATCH / OLDER_BUILD / NEWER_BUILD) and `macro_context_current` (False when the board was rebuilt after it).
  - The evening step (Lab hand-off) runs the join after the hand-off is built.
  - The packs step runs it unless the context is already current; later batches reuse it.
  - The board step runs it after `Run-MacroBoard.ps1` and reports "Macro context refreshed: N names changed money_tag". The re-tag-by-hand message remains only for when the refresh fails.
  - `status` says when the context is missing or behind the board.
  - The legacy hand-off is not joined (it has no `lb_ledger_id`); the step says so.
- `Run-MacroInputs.ps1`: a new step, "Triage macro context refresh" (`scripts/refresh_triage_macro_context.py`), runs after the board and before the clean-up. It is left out with `-SkipBoard`.
  - It joins the board's next session to `handoff\lab_<next_session>` when that exists. Otherwise it is skipped with a note (exit 0).
  - Exit 2 means not written, with the reason printed.
- `triage_context.py`: `refresh_next_session()`, the `--next-session` / `--handoff-root` CLI options, and `changed_money_tag` / `previous_board_built_at_utc` in the JSON.
- Tests:
  - `macro_board/tests/test_triage_context.py`: 22 pass;
  - `data/scratch/workaround/test_laneb_macro_context.py`: 4 pass (runs a copy of `avs_day.ps1 status` in a temporary repo tree);
  - `tests/test_macro_inputs_runner_steps.py`: 6 pass;
  - regression: Lane B tests 44 pass, and the 7 other files that plan the runner pass (77 tests).
- Smoke test on real paths:
  - with the 19 Nov intelligence, the wrapper skips (no `lab_2026-11-20` yet), exit 0;
  - without a board file since T1, it reports NOT WRITTEN, exit 2.
  - The first real file comes with the next board build.
- End-to-end acceptance (T3–T5) waits for one real session: hand-off → join → ACK's triage chats → checktriage.

**T5 status (20 Nov 2026): BUILT, verified, not committed.**
- `check_triage.py` v5 adds a `macro` check, WARN only, never FAIL. For each Lab triage row whose `ledger_id` is in `triage_macro_context_<session>.csv`, it checks that:
  - the first word of `money_tag` equals the file's;
  - `macro_sector_agreement` starts with the file's agreement word;
  - `macro_kill_switch` carries the file's kill level.
- Each mismatch is one WARN line per name, with the board's value beside it.
- Other WARN cases:
  - a missing or unreadable file gives one WARN: "the board macro context was not available";
  - a context older than `etf_intelligence_latest.json` gives a WARN to run `avs_day.ps1 board`;
  - a ledger id the context does not carry is named.
- Notes give "N of M rows match" per batch. `--macro-intelligence` overrides the latest-build path.
- Tests: `data/scratch/workaround/test_laneb_check_triage_macro.py` 6 pass; the existing `test_laneb_check_triage.py` 9 pass.
- Acceptance: the real 19 Nov triage (batches 1–4, 120 rows, read-only) was checked against the scratch 19 Nov EVENING context. 0 of 120 rows match: every macro column was hand-written.
  - BAC: triage MIXED/MIXED; board WITH/AGREE, kill 54.01.
  - HSBC: UNRESOLVED side, board NO_SIDE.
  - BKNG: triage WITH; board MIXED/PARTIAL, kill 114.17.
  - All three were verified against both files.
  - No macro line appears in the FAIL section. The one FAIL predates T5: batch 1's prompts were saved as `deep_dive_prompts_2026-11-19_b1.md`, and the check expects `deep_dive_prompts_2026-11-19.md`.
  - This run shows the check works. It compares a morning triage with that evening's build, so it is not the end-to-end case. That case (a triage made with the T4 prompt has no macro lines) waits for one real session.

**T6 status (20 Nov 2026): BUILT, verified, not committed.**
- Timing change from §2.6: the board does not read the per-name file. That file is written after the board build, so it would always be one build behind. Instead, the board build calls `triage_context.board_ticker_impact()` in-process, with this build's per-ETF projection: one owner of the join logic, and always the current build.
- `build_board.attach_triage_impact` runs after the Day story and sets `day_story.triage_impact`. Its status is one of:
  - TRIAGE: the names on the next session's `batch<N>_triage_<session>.csv`, by batch and `deep_mine_rank`;
  - HANDOFF_NOT_TRIAGED: hand-off batches 1–4 before the triage runs;
  - NO_HANDOFF / AS_OF_BUILD: the pipeline candidates are kept, with a note saying why;
  - FAILED: the reason is shown and the board still builds.
- Each name links to `<TICKER>_deep_dive_<session>.html` in the hand-off folder when one is saved (relative to the board HTML).
- Config: `day_story.triage_impact` (`max_batches` 4, `handoff_root`).
- Template:
  - Ticker impact shows the triage table (rank, ticker with card link, side, sector ETF with its relative-performance chip, link, `money_tag` with both readings on hover, measured / packet fit, kill switch, scenarios) grouped by batch, with a CSV export `day_story_triage`;
  - otherwise the existing pipeline table, with the note.
- Tests: `macro_board/tests/test_triage_context.py` 28 pass (6 new). Board regression: day_story 33, macro_board_rules 63, event_timestamp_sorting 20, etf_intelligence 13, lab_macro_desk 11.
- Browser check: the template was rendered with the real 19 Nov EVENING payload, plus a ticker-impact block from the real 18 Nov hand-off (`next_session` overridden for the check only). Results:
  - 90 triaged names in batch groups 1, 3 and 4;
  - card links on HSBC, BAC, BKNG and SMCI;
  - the first row matches the join (HSBC call, XLF, link 0.59, WITH, kill 54.01);
  - no console errors from the board.
  - With NO_HANDOFF, the pipeline table shows with the note.
  - The check pages were removed afterwards.

## 8. T7 design (approved by ACK 20 Nov 2026: "Approve, build T7"; built, see the status below)

T7 adds four items to the same per-ETF projection (`etf_intelligence.py`) and the per-name file (`triage_context.py`). Nothing new is measured beyond relative returns the board already holds, nothing is scored, and rule 6c still holds: no gate, rank, contract, side or size changes.

**Sources as read on 20 Nov (real files):**
- Event file (`dropbox/macro/economic_events_latest.json`, 19 Nov 23:35): 41 events, 209 distinct field names. `market_perception` is a dict on 35 events, each with `interpretation`, `alternative_explanation`, `invalidation`, `required_confirmation` and `evidence_status`. Consensus sits under `forecast` (13 events) or `pre_release_consensus` (7), with source and time under three or more spellings. `beneficiaries` is free text on 6 events. The top level carries `sector_impacts` (favoured / adverse / high-dispersion, each with named ETFs and a condition) and `counter_case` (summary plus reversal conditions).
- US Money Index (`dropbox/macro/avshunter_us_money_index.json`, rev 91): `forward_triggers` (relief confirmation, risk-off escalation, invalidation and its conditions); `leadership.counterevidence` (a list stored as a string); `leadership.leadership_invalidation`; `options_monetisation.sector_routing` keyed by sector name. `risk_off_transmission_score` has no score and no components since the 10 Nov rebaseline.
- Both are ChatGPT outputs written from our measured sheet plus outside news. New source label: `LLM_WITH_NEWS`, carrying the file name and its as-of time. Agreement with our measured read is still not independent confirmation (rule 6b).

**T7a. Event intelligence (tolerant field-name reader).**
- One reader in `build_board.build_intel` with aliases kept in config (`etf_intelligence.event_fields`), so the next spelling change is a config edit. The first alias present and non-empty wins, and the field it came from is recorded.
- Per ETF: `event_sector_view`, which is FAVOURED / ADVERSE / HIGH_DISPERSION / NOT_NAMED, with the condition text from `sector_impacts`, plus any `conditional_etf_cases` entry (bullish / bearish / wait).
- Market-wide block (JSON and merge only, not repeated on every row): the latest events by observation clock (count from config). Each carries interpretation, alternative explanation, invalidation, required confirmation, evidence status, consensus with its source and time (or MISSING), and beneficiaries as given. Beneficiaries are not mapped to ETFs because they are free text. It also carries the counter-case summary and its reversal conditions.

**T7b. US Money Index counter-evidence and triggers.**
- Market-wide block: the forward triggers (relief, escalation, invalidation), the counter-evidence (the stringified list parsed back into items) and the leadership invalidation.
- Per ETF: `usmi_routing`, the `sector_routing` text for the ETF's sector, via a config map from sector name to ETFs (for example semiconductors → SMH, SOXX; financials → XLF, KRE, KBE). Unmapped sectors are listed, never dropped.
- The empty score is shown as MISSING with the reason ("no score or components since the 10 Nov rebaseline"), never as 0.

**T7c. Peer and sector benchmarks.** SPY stays the market reference. Each ETF also gets one peer reference, set in a config map, and the read is computed with the existing `day_story.relative_returns` and `money_flow` (same windows and bands):
- the 11 sectors against RSP (the equal-weight S&P 500), so a sector is compared with the average stock and not the mega-cap weight;
- industries against their parent sector (SMH, SOXX, IGV → XLK; KRE, KBE → XLF; XBI, IBB → XLV; XOP → XLE; XHB, XRT → XLY; IYR → XLRE; IYT, JETS → XLI; GDX → XLB; ARKK → QQQ);
- other universe ETFs against their group reference (for example QQQ, IWM, DIA → SPY; factors → SPY; rates and credit → AGG; international → EFA or EEM; commodities → their spot proxy or none).
- Output: `benchmarks` = {SPY read, peer read, `benchmark_split`}. `benchmark_split` is SAME or SPLIT, meaning the two references give different labels. For example, XLY outperforming SPY but lagging RSP is SPLIT. It is display only.

**T7d. The self-ETF names.** On the 19 Nov hand-off, 80 rows have the name as its own `sector_etf`. Of these, 58 are outside the 26 rotation ETFs: 47 are in the board universe (for example SPY, QQQ, IWM, TLT, GLD, HYG, IBIT, MTUM) and 11 are not (IAI, IHE, IHI, IVE, IVW, IWR, IYW, SIZE, VGT, VOOG, VOOV). The earlier count of 51 was an estimate; this recount supersedes it.
- The projection covers every ETF in the board universe (115), not only the 26 rotation ETFs.
- The 26 keep their full Day story read.
- The other universe ETFs get a measured read against their T7c reference: relative performance, label, volume. Decision scenarios say "not offered: the board has no trade idea for this ETF" (STAND_ASIDE applies). The packet stance and agreement work as before.
- Leveraged and inverse ETFs take their underlying's read, with the sign flipped for inverse ones (config map). Volatility products (VXX, VIXY, UVXY, SVXY) stay NO_BOARD_READ with the reason "volatility product: no relative-performance read".
- Names outside the universe (for example IYW, VGT, IVE, IVW, VOOG, VOOV, IWR, SIZE, IAI, IHE, IHI) stay NO_BOARD_READ with the reason "not in the board universe". Adding them is a universe change for ACK.
- In `triage_context`, a name whose `sector_etf` is itself is read from its own ETF entry. The link is SELF, not a 60-session correlation of 1.0.

**Per-name file (`triage_context`), new columns:** `peer_reference`, `peer_relative_label`, `benchmark_split`, `event_sector_view`, `usmi_routing`. The JSON gains the market-wide `event_intelligence` and `usmi_intelligence` blocks for the merge. Existing columns and `money_tag` rules are unchanged.

**Out of T7:** board template display of the new items (a later step if wanted); options monetisation; the event-file and Money Index prompt fixes (ChatGPT side).

**Tests (written first):**
- the reader takes the first present alias and records which;
- a missing perception part is MISSING;
- `sector_impacts` membership maps to FAVOURED / ADVERSE / HIGH_DISPERSION / NOT_NAMED;
- the stringified USMI counter-evidence is parsed into items;
- the empty USMI score is MISSING with the reason;
- an unmapped routing sector is listed;
- sectors use RSP and industries their parent;
- a SPLIT is reported when the labels differ;
- every universe ETF is in the projection;
- an inverse ETF's stance is the flipped underlying;
- a volatility product is NO_BOARD_READ with its reason;
- a self-ETF name reads its own entry with link SELF;
- `lab_rank`, side and contract stay unchanged.

**Acceptance:** run against the real 19 Nov event file, the rev 91 Money Index and a 19 Nov EVENING payload rebuilt as of 19 Nov (no live file replaced):
- for 3 ETFs (sector, industry, self-ETF), every T7 field matches its source field by field;
- the 80 self-ETF rows are recounted by status;
- `peer_relative` is recomputed independently from the price store.

**T7 status (20 Nov 2026): BUILT, verified, not committed.**
- `etf_intelligence.py`: `event_intelligence()` (tolerant reader `pick()`, aliases in config `etf_intelligence.event_fields`, the field used recorded per item), `usmi_intelligence()`, peer reads (`_bench_read`, `_benchmarks`), universe coverage, derived and no-read entries. `project()` adds `coverage`, `benchmarks`, `event_sector_view`, `event_etf_case` and `usmi_routing` per ETF, and the market-wide `event_intelligence` / `usmi_intelligence` blocks with their as-of time.
- `build_board.build_intel(t7=...)` reads both files into the payload. A malformed file gives UNREADABLE with its reason and the board still builds.
- `triage_context.py`: link SELF for a name that is its own sector ETF; five new columns (`peer_reference`, `peer_relative_label`, `benchmark_split`, `event_sector_view`, `usmi_routing`); the JSON carries both market-wide blocks. A file built before T7 gives MISSING.
- Config: `etf_intelligence` gains `max_events`, `event_fields`, `sector_impact_views`, `usmi_trigger_keys`, `usmi_sector_map`, `benchmarks` and `t7_rationale`.
- Clarifications made while building (within the approved design):
  - The measured stance of every ETF is read against SPY, as for the 26; the peer is shown beside it. Broad indices and factors use RSP as their peer, because SPY as a peer would repeat the market read. International uses EFA, with EEM for the emerging-market ETFs (`ticker_peer`).
  - Universe ETFs outside the 26 have no volume ratio: the payload's price metrics carry none. It shows as MISSING.
  - The US Money Index stores its counter-evidence as a list written as text followed by more text (rev 91). The leading list is parsed and the trailing text kept as one more item.
  - **Fresh or flagged.** A read needs fresh price data on both legs. A stale leg gives MISSING and names its last session, never a comparison of returns ending on different dates.
- **Finding (data, not fixed here):** in the price store, 39 of the 115 universe ETFs are stale on 19 Nov. 37 last traded on 15 May (for example IJR, SCHD, XME, ITB, BND, EMB, IAU, GDXJ, KWEB, INDA, BITO and most leveraged ETFs) and 2 on 20 Aug (RSP, UUP). Because RSP is stale, the 11 sectors' peer read is MISSING until RSP is refreshed in the price store or ACK chooses another sector peer (for example an equal-weight average of the 11 sector ETFs, which are all fresh). Leveraged ETFs read their underlying, which is fresh, so they are unaffected.
- Tests: `macro_board/tests/test_etf_intelligence_t7.py` 24 pass; `macro_board/tests/test_triage_context_t7.py` 7 pass. Regression: 30 files, 435 tests, 0 failures (all macro_board tests, Lane B tests, `tests/test_lab_macro_desk.py`, `test_usmi_rebaseline_contract.py`, `test_macro_inputs_runner_steps.py` and `test_macro_retention.py`).
- Acceptance: the board was rebuilt as of 19 Nov into a scratch folder with the live event file (19 Nov 23:35) and US Money Index (rev 91). The live board, Lab publication and `macro_board/output` were not touched. 83 checks, 0 mismatches:
  - every field of the 5 events shown equals the source at the field used;
  - the sector-impact views of all 12 named ETFs match; all 8 routing sectors map to their ETFs (none unmapped);
  - the 10 counter-evidence items match; the triggers match; the score is MISSING;
  - XLK, SMH and TLT against SPY and their peer were recomputed from the price store to 4 decimals (XLK's RSP peer is MISSING, stale);
  - the per-name file on a copy of the 19 Nov hand-off has 2,593 rows in ledger order.
- Effect on the 19 Nov hand-off: all 80 self-ETF rows are link SELF. 14 remain NO_BOARD_READ: the 11 names outside the universe and 3 volatility products. Before T7, all 58 self-ETF names outside the 26 had no read. Across all rows, money_tag NO_READ falls from 54 to 17.
- Coverage on the 19 Nov build: 26 Day story, 4 absolute (SPY, VOO, IVV, VTI), 57 universe reads, 24 derived, 4 no read. Market/peer split: SAME 15, SPLIT 20, NO_PEER 9, MISSING 43 (stale legs), plus 24 DERIVED and 4 NO_READ.
- Not done in T7 (unchanged scope): the board template does not display the new items yet; the first real `etf_intelligence_latest.json` comes with the next current board build.

**T7 sector peer changed (ACK 20 Nov 2026: "Equal-weight 11 sectors").** It supersedes RSP as the sector peer in T7c, because RSP's last bar in the price store is 20 Aug.
- The 11 sector ETFs are now compared with `EW_SECTORS`, the plain mean of the 11 sector ETFs' returns over the same windows. It is set in config `etf_intelligence.benchmarks.baskets` (members = `rotation.sectors`).
- Every member must be fresh; otherwise the read is MISSING and names the stale members.
- Tests: `test_etf_intelligence_t7.py` 26 pass (2 new: the basket read, and a stale member). Regression: 30 files, 437 tests, 0 failures.
- Acceptance on a new as-of 19 Nov rebuild: 93 checks, 0 mismatches. XLK and XLE against `EW_SECTORS` were recomputed from the price store (the mean of the 11 sectors' returns) to 4 decimals.
  - XLE is the example: NONE against SPY (+0.10 over 5 sessions) but OUTFLOW against the average sector (−0.98), so SPLIT.
- Market/peer split on 19 Nov: SAME 20, SPLIT 26, MISSING 32, NO_PEER 9, plus 24 DERIVED and 4 NO_READ.
- Broad indices and factors switched too (ACK 20 Nov 2026: "Yes, switch them"). `group_peer` for Broad indices and Factors is now `EW_SECTORS`, so RSP is no longer a peer anywhere.
  - Tests: `test_etf_intelligence_t7.py` 27 pass; the live-config test pins all three to `EW_SECTORS`. Regression: 30 files, 438 tests, 0 failures.
  - Acceptance on a new as-of 19 Nov rebuild: 109 checks, 0 mismatches. QQQ and IWM against `EW_SECTORS` were recomputed from the price store.
  - IWM is the example: INFLOW against SPY but OUTFLOW against the average sector, so SPLIT.
  - Split on 19 Nov: SAME 28, SPLIT 33, MISSING 18 (the ETF itself is stale), NO_PEER 8, plus 24 DERIVED and 4 NO_READ.
- Still open: the 37 ETFs stale since 15 May (and RSP and UUP since 20 Aug) are a price-store gap, not fixed here; their own reads are MISSING with the last session named.

**Correction (20 Nov 2026, after `STALE_UNIVERSE_PRICES_root_cause_2026-11-20.md`).** The "39 stale ETFs" finding above was read from the as-of 19 Nov rebuilds, which skip the board's price fill (`build_board.py:208`). On the live 19 Nov EVENING build (23:42 UTC) all 39, RSP included, are FRESH to 19 Nov, filled from the board's grouped-daily cache (checked against the live board payload).
- What holds: the price store itself has no bars for the 37 after 15 May or for RSP and UUP after 20 Aug. As-of rebuilds therefore show them MISSING.
- What was wrong: the statement that the sector peer read is MISSING because RSP is stale. That is true only on as-of rebuilds; on live builds RSP was usable.
- ACK chose `EW_SECTORS` on that framing. `EW_SECTORS` works on both live and as-of builds; RSP would work on live builds only. **ACK confirmed the choice after the correction (20 Nov 2026: "Keep equal-weight").** `EW_SECTORS` stays the peer for sectors, broad indices and factors.
- New defect surfaced by the note: BITO's cached close is not split-adjusted (19 Nov close 1.98 times 18 Nov). The live board shows BITO +98.3% on the day, and T7 gives BITO a read from it. This is a board price-cache defect, not fixed here; the note proposes fixes A to C.

