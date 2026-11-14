# AVS-CHANGELOG-001: one shared change log for every agent

Standing rule for Codex, Claude Code and any other agent working in `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`.
Paste this section into `AGENTS.md` (Codex) and `CLAUDE.md` (Claude Code) so it applies to every session, not one brief.

## Why

Three agents (Codex, Claude Code, Claude in chat) work on the same repo on different branches. On 13 Nov 2026 seven
branches were unmerged and no single place said what had changed, so the state of the pipeline had to be rebuilt from git logs.

## The file

**Correction (13 Nov, after reading the repo):** a change log already exists at `data\scratch\workaround\lessons\change_log.md`
(ACK's rule of 17 Oct, last entry about 19 Oct), with `lessons\fix_register.csv` and `lessons\fix_inbox\`. Do **not** create a
second log. Extend the existing one: keep its entry format and add the fields below (branch, commit, fix_id, run_evidence, receipt,
merged) to every new entry. AVS-TRACE-001 backfills the gap since 19 Oct. The table header below shows the fields; the existing
entry format may be kept as long as every field is present.

```
| when_utc | agent | branch | commit | fix_id | change (one line) | files | tests | run_evidence | receipt | merged |
|---|---|---|---|---|---|---|---|---|---|---|
```

## The rule

1. **Every commit gets one line**, written in the same commit. No line, the commit is not done.
2. **Every non-code action that changes data or spends credits gets one line** (backfills, re-scores, provider pulls), with the
   credit count in `change`. Example: PHANTOM backfills 13 Nov, 466,193 rows, 6,205 credits.
3. **Every pipeline run gets one line**: run ID, mode (Evening/Morning), outcome (COMPLETE / STOPPED at <station> / FAILED) and why.
4. `run_evidence` = the run ID that shows the change working, or `AWAITING_RUN`. A fix is CLOSED only when this is filled
   (two-level closure: code evidence plus run evidence).
5. `receipt` = path under `audit\fix_receipts\`. Required for every fix line.
6. `merged` = `no` when written. When a branch is merged, append a new line (`agent = ACK` or the merging agent,
   `change = merged <branch> into <target>`); do not edit the old line.
7. **Before starting work, read the last 30 lines** of `audit\CHANGE_LOG.md` and state in your first message which open branches
   or awaiting-run items touch the files you will change. If two branches change the same file, say so before writing code.
8. Times in UTC, ISO format. One line per item, no line breaks inside a cell.

## Backfill (once)

The first agent to pick this up adds lines for everything since 11 Nov 2026, from the git branch logs:

| when_utc | agent | branch | change |
|---|---|---|---|
| 2026-11-11T11:15Z | Codex | phantom-scoring-iv-hold-fixes-20261111 | PHANTOM scoring, IV and hold lineage |
| 2026-11-12T12:18Z | Codex | fix/production-eligibility-20261112 | production eligibility checked before acquisition |
| 2026-11-12T21:12Z to 23:05Z | Claude Code | laneb/lab-first-handoff | Lane B Fix B (B0 to B10); live flow left on LEGACY |
| 2026-11-12T22:14Z | Codex | fix/ac-reliability-20261112 | A/C evidence clocks and hand-offs |
| 2026-11-12T23:07Z | Codex | feat/a12-monetisation-clock-20261112 | saved-data A12 monetisation clock |
| 2026-11-13T01:09Z | Pipeline | (run 20261112_230902) | Evening STOPPED at Discovery station: RBOT entry_price not positive, enforce on; no Lab book |
| 2026-11-13T07:29Z | Codex | fix/station-quarantine-20261113 | isolated station defects quarantined instead of stopping the run |
| 2026-11-13 (day) | Codex | (data) | PHANTOM backfills 466,193 rows, 6,205 credits; 12 Nov deferred (40 entry, 20 path quotes) |
| 2026-11-13T21:19Z | Codex | fix/phantom-path-completeness-safeguards-20261113 | path completeness check, backfill guards |

Fill the missing columns (commit hash, files, tests, receipt) from git for each.
