# AVS-TRACE-001: traceability review of AVSHUNTER documents and fix logs, plus the ETF fix package for Codex

Prompt for Claude Code. Written 13 Nov 2026 for ACK.
Repo: `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`. Outputs: `audit\trace\AVS-TRACE-001\`.

## 0. Role and rules

- You are an **independent reviewer**. Read only. Do not change code, config, prompts, scheduled tasks or data.
  The only files you write are under `audit\trace\AVS-TRACE-001\`, plus the change-log entries in section 6.
- Do not run the pipeline, the Lab, or anything that calls MarketData, Polygon, Tastytrade or the Claude API.
- Two-level closure (ACK, 4 Sep 2026): a fix is **CLOSED** only with code evidence **and** a run artefact showing it working.
  Code plus tests only = **CLOSED OFFLINE**, reported in its own column, never counted as closed.
- Missing evidence is never a pass. If you cannot find it, say `NOT FOUND` and list where you looked.
- Every factual statement in your outputs cites a file path (and line or row where it applies), a commit hash or a run ID.
- Write in plain UK English. Commands for ACK in PowerShell with full paths.

### Comprehension gate (do first, write to `00_comprehension.md`, then continue)

In 10 lines or fewer state: what AVSHUNTER produces each day; the difference between Lane A (Evening/Morning pipeline,
Intelligence Lab) and Lane B (hand-off, packs, triage, deep dive); what the fix register, fix inbox and change log are for;
and the two-level closure rule. Then list the branches you found and which files each touches.

## 1. Why this review

Three agents work on this repo (Codex, Claude Code, Claude in chat) and ACK. On 13 Nov 2026:
- 7 branches were unmerged and no single record said what had changed (`laneb/lab-first-handoff`,
  `phantom-scoring-iv-hold-fixes-20261111`, `fix/production-eligibility-20261112`, `fix/ac-reliability-20261112`,
  `feat/a12-monetisation-clock-20261112`, `fix/station-quarantine-20261113`, `fix/phantom-path-completeness-safeguards-20261113`).
- `lessons\change_log.md` stopped being written around 19 Oct.
- `lessons\fix_register.csv` has 127 rows: 73 Proposed, 50 Built, 2 Decision, 1 Approved, **1 Closed**. "Built" without run evidence
  is the norm.
- Fixes are named in at least eight ID schemes across documents (F-, N-, X17-, D1–D18, W0–W4, WP0–WP8, REQ-/ALG-, A1–C6, B0–B10,
  the 13 Nov flaw list), so the same problem can be open under one ID and "built" under another.
- The 12 Nov Evening run (20261112_230902) stopped at the Discovery station on one bad row (RBOT entry_price not positive).
  There is no current Lab book.

ACK needs one traceable picture: what was asked, by which document, who owns it, what was built where, and what is proven on a run.

## 2. Sources to review

**Fix logs**
- `data\scratch\workaround\lessons\fix_register.csv`, `change_log.md`, `fix_review_2026-10-14.md`, `lessons_learnt_*.md`,
  `monitor_task_changes_20261017.md`, `archive\*.csv`
- `data\scratch\workaround\lessons\fix_inbox\*.md` and `fix_inbox\processed\*.md` (all of them, 14 Oct to 13 Nov)
- `audit\laneb_fixB\99_report.md`, `needs_codex.md`; `Claude outputs\2026-11-12_claude_code_brief_fix_B.md`
- `audit\verify\*\*\verify_report.md` (verifier results per run)

**Design, requirement and fix documents**
- `dropbox\macro\coaching\desk_gate\` (AVS-DESK-GATE-001, AVS-FIX-002, AVS-QA-SD-FIX-002 and v1.1, AVS-REQ-FIX-002 and Annex A,
  AVS-UAT-FIX-002, AVS-VAL-THESIS-001, AVS-TD-001, AVS-DISC-002)
- `docs\*.md` (AVS-SD-FIX-002, AVS-SD-DOI-001, AVS-SD-INT-001, AVS-SD-MON-003/004, AVS-FIX-REVIEW_APPROVED_FIXES_20260925 and others)
- `audit\*.md` and subfolders (AVS-INV-001, AVS-REV-002/003, rca, solution_design, avs_fix_002)
- `config\governed_constants_v1.json` (approval notes are requirements too: e.g. `long_option_contract_selection.approval`)
- `CLAUDE.md`, `AGENTS.md` if present

**Code history**
- All local branches and their commits (`git branch -a`, `git log --all --stat` since 2026-09-01), merged state against `master`
  and the checked-out branch. Files changed by more than one unmerged branch.

**Briefs and lists from 13 Nov (ACK will place them in `audit\trace\AVS-TRACE-001\inputs\`)**
- `AVS-LEDGER-001_card_outcome_ledger_brief.md`, `AVS-CHANGELOG-001_shared_change_log_rule.md`
- The 13 Nov flaw list (below), which exists only in chat.

### The 13 Nov flaw and fix list (trace each to existing IDs)

Root causes found 13 Nov from run 20261111_231951 and the code:
1. Thesis clock too slow for the 1–20 session mandate: arrival measured on the setup's bar timeframe (1mo = 21 sessions);
   1,499 of 2,132 hand-off rows outside the window.
2. Runway is a penalty, not a rule: `long_option_contract_selection_v2` ("the horizon informs contract choice, it never gates it",
   3 points per short day); `value_selection_mode` still SHADOW. 1,005 contracts expire before the median arrival, 481 before q80.
3. Illiquid contracts kept by design (DOI non-discard); 11 Nov liquidity gate only in Lane B; 1,045 rows fail OI, 616 spread > 20%.
4. Stale quotes: MarketData delayed feed (900 s delay vs 900 s freshness limit); Morning ran 10:42 ET; 4/4 tradeable rows 53–58 min old.
5. Specified fixes not shipped: GARCH D1 (`layer3_forward_variance.py` lines 691–692 still differences); monetisation not published;
   no outcome ledger.

Fixes proposed 13 Nov: (1) Lane B switched to the Lab hand-off; (2) Morning in 09:35–09:45 ET with a late guard; (3) Tastytrade live
re-quote at entry; (4) GARCH D1; (5) contract covers q80 + buffer, liquidity tiers, rank by return per premium dollar (SHADOW to ACTIVE);
(6) 2–3 contract alternatives; (7) publish monetisation; (8) window flag in the Lab; (9) outcome ledger for every card, traded or not;
(10) retire or adapt old-layout scripts and the X17 test.

## 3. Outputs

### 3.1 `01_traceability_matrix.csv` (and `.md` summary)

One row per requirement or fix, across all sources. Columns:

`trace_id, source_ids (every ID it carries in any document), title, source_documents (path:line), raised_date, raised_by, owner,
lane (A | B | macro | data | ops), branch, commits, files_changed, tests (path, pass/fail if recorded), run_evidence (run ID + artefact),
status (PROPOSED | APPROVED | DECISION_PENDING | BUILT_UNMERGED | MERGED | CLOSED_OFFLINE | CLOSED | SUPERSEDED | DUPLICATE | REJECTED | NOT_FOUND),
status_evidence, superseded_by, conflicts_with, monetisation_impact (HIGH | MEDIUM | LOW | NONE), notes`

Rules:
- Merge duplicates into one `trace_id`; keep every original ID in `source_ids`.
- `status` is what the evidence proves, not what a document claims. Where a document says closed but the evidence does not,
  record both and mark `CLAIM_NOT_SUPPORTED` in notes.
- `monetisation_impact`: HIGH if it touches contract choice, hold/window, liquidity, quote freshness, exit rules, outcome measurement
  or ranking; otherwise judge and say why.

### 3.2 `02_fix_log_review.md`

- How each log has been used against its own rules (inbox → register → change log → closure evidence). Where the flow broke and since when.
- Register rows marked Built with no closure evidence: list, and for each say whether a run since then shows it working.
- Duplicates, contradictions and superseded rules (e.g. the 25% spread rule vs the 11 Nov tiers; min-14-DTE rule vs 14–45 DTE vs
  "ignored in mining"; macro advisory-only vs the QQQ exception).
- Inbox candidates never triaged into the register (count and list).
- Decisions waiting on ACK, with the document that raised each.

### 3.3 `03_branch_review.md`

For each unmerged branch: purpose, commits, files, tests, receipt (if any), run evidence, what it closes in the matrix, and
**file overlaps with other branches** (same file changed on two branches = merge risk; give the hunks).
Recommend a merge order with reasons. Do not merge.

### 3.4 `04_open_fixes_by_impact.md`

The open items only, ordered by monetisation impact, grouped under the 13 Nov flaws 1–5 and "other". For each: trace_id, owner,
the smallest next step, and the acceptance check (code evidence + run evidence).

### 3.5 `05_change_log_backfill.md`

Entries for `lessons\change_log.md` covering 19 Oct to 13 Nov, built from git, run folders and receipts, in the log's existing format
plus the fields in AVS-CHANGELOG-001 (branch, commit, fix_id, run_evidence, receipt, merged). Include pipeline runs (with outcome,
e.g. 20261112_230902 STOPPED at Discovery) and data actions with credit counts (13 Nov PHANTOM backfills: 466,193 rows, 6,205 credits,
7,187 reserved; 12 Nov deferred). Write the entries here for ACK to approve; append them to `change_log.md` only after ACK says yes.

### 3.6 `06_ETF_fix_package_for_Codex.md`

Validate section 4 against the code and data (confirm or correct every evidence line with a path or count), add anything the logs
hold that section 4 misses, and write it as a hand-over for Codex as **owner**. Codex reviews it, accepts or challenges each item
in writing, and then owns delivery.

### 3.7 `99_report.md`

One page: counts by status, the five most important gaps, decisions needed from ACK, and the merge-order recommendation.

## 4. ETF fix package (AVS-ETF-001), draft for validation

**Why:** ETFs are the most liquid, macro-native instruments in the universe and ACK wants them prioritised. Today the pipeline treats
them as stocks and they almost never resolve. Evidence (14 Oct ledger, `decision_ledger_2026-10-14_outcomes.csv`): about 40 ETFs per
ledger (1.7% of rows); 24 of 36 ETFs with an arrival time over 60 sessions; 1 resolved outcome (a stop). Across all names, setups expected
in 1–3 sessions hit target first 83% of the time, 4–10 sessions 78%, over 60 sessions 5% (stock outcomes, 2 sessions tracked, one date).

| ID | Problem | Evidence (validate) | Change | Acceptance |
|---|---|---|---|---|
| E1 | No asset-type field: ETFs not identifiable universe-wide | Ledger has no ETF flag; classification done by a hand list | Add `asset_type` (ETF, ETN, index ETF, leveraged/inverse, stock) from instrument metadata to the universe and carry it to the Lab card | 100% of rows typed; leveraged/inverse flagged |
| E2 | ETF arrival times from stock-style structure (weekly/monthly bars) | 24 of 36 ETFs > 60 sessions on 14 Oct | ETF horizon model: targets sized to the ETF's own volatility over 1–10 sessions; weekly/monthly setups restated in sessions and flagged when outside 1–20 | ≥ 80% of ETF rows with q50 ≤ 20 sessions on a normal run |
| E3 | Long-running ETF theses frozen on old events | QQQ/SPY READY_OLD_EVENT from 24 Apr; 469–470 rows dropped the same way (`fix_inbox\2026-10-23_qqq_exclusion.md`) | Re-arm READY theses on a fresh event (new 20-day high/low close, reclaim after a test); index ETFs bypass `focus_v3` | No ETF thesis older than N sessions without a re-arm event; QQQ/SPY/IWM/DIA priced every run |
| E4 | Index ETFs have no macro mapping | money tag UNMAPPED for QQQ/SPY | Map index ETFs to themselves against SPY/RSP breadth; sector ETFs to their sector route | 0 ETF rows UNMAPPED |
| E5 | Macro authority for ETFs | ACK allowed QQQ as an exception to macro-advisory-only (12 Nov) | **Decision for ACK:** may the macro board set direction for ETFs (index and sector)? If yes, define the rule and its kill switch | Decision recorded; rule in governed constants |
| E6 | ETF events missing (holdings report dates) | XLE: holdings worth 65.2% report by 30 Oct, triage said "no events" (`fix_inbox\2026-10-19_XLE.md`) | Holdings-weighted event list with a materiality rule: a holding print counts when weight × its implied event move ≥ 0.25 ATR of the ETF | ETF cards list material holding events inside the hold |
| E7 | Dividends ignored in ETF option pricing | XLE yield 2.29%, ex-date inside the contract life; +22.0% vs +19.9% with dividend | Price discrete dividends from ex-date cadence (ignore Tastytrade `dividend-next-date`, stale) | Repricing matches the card basis within 1 point |
| E8 | Wrong correlation and beta source | Tastytrade corr-SPY 0.77 / beta 0.49 vs store 63-day −0.31 / −0.61 | Compute from the price store | Card values equal the store |
| E9 | Premium cap excludes index ETFs | QQQ near-the-money 14–45 DTE well above $5 | **Decision for ACK:** over-cap lane for index ETFs, or 5–8% OTM inside the cap (lower delta) | Rule recorded; selection follows it |
| E10 | ETF contracts should use weeklies for 1–10 session holds | QQQ has weeklies; monthly-only names differ | Contract selection for ETFs prefers the nearest weekly that covers q80 + buffer | 0 ETF contracts expiring before q80 |
| E11 | Spread gates on after-hours quotes | XLE short-dated spreads from 23:59 UTC quotes (34–47% of mid) | Capture gate quotes at 15:55 ET; flag post-close quotes | No gate decision on a post-close quote |
| E12 | ETFs not prioritised | Rank ignores asset type | In triage, in-window ETFs ranked ahead of stocks at equal Lab verdict | Batch 1 contains every in-window ETF |
| E13 | 52-week flag missing on ETFs | XLE 0.05 below its 52-week high, no flag | Add NEAR_52W_HIGH/LOW and the resistance-test value to every row (skill `avshunter-52w-resistance-check`) | Flag present on every ETF row |
| E14 | OCC symbol padding breaks quote lookups | "XLE  270115C00067500" returns nothing; needs a six-character root | Normalise OCC symbols in the tool wrapper and prompts | Lookups succeed for 2- and 3-letter roots |
| E15 | ETF outcomes not measured separately | No ETF split in any summary | ETF vs stock split in the card outcome ledger (AVS-LEDGER-001) | Summary shows ETF rows with n |

Dependencies: E2 and E10 depend on the 13 Nov fixes 5 (contract covers the hold) and 8 (window flag). E15 depends on AVS-LEDGER-001.

## 5. Acceptance for this review

| # | Check |
|---|---|
| T1 | Every row of `fix_register.csv` and every inbox candidate appears in the matrix (print the counts both sides) |
| T2 | Every unmerged branch is in `03_branch_review.md` with its file overlaps |
| T3 | Every status other than PROPOSED cites evidence; every CLOSED cites a run ID |
| T4 | Each of the 13 Nov flaws 1–5 and fixes 1–10 maps to one or more trace_ids, or is marked NEW |
| T5 | `06_ETF_fix_package_for_Codex.md` confirms or corrects every evidence line in section 4 |
| T6 | No file outside `audit\trace\AVS-TRACE-001\` changed (show `git status` before and after) |

## 6. Change-log entry for this session

When finished, add one entry for this review to `data\scratch\workaround\lessons\change_log.md` in its existing format
(WHAT, WHERE, REGISTER, STATE, COMMITTED) plus branch, fix_id `AVS-TRACE-001`, and the output folder. This is the only
change outside the output folder.
