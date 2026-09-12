# AVS-OPS-002 — Identify and commit all uncommitted work in AVSHUNTER-Intelligence

**Issued:** 2026-09-11 by ACK
**Operator:** Claude Code, working in `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`
**Objective:** every fix and feature currently sitting in the working tree is committed in clearly described, logically grouped commits, with nothing dangerous or disposable included, so that future runs can identify the code they ran on (closes defect QT-D02).
**Output:** `audit\ops\AVS-OPS-002\` — inventory, commit plan, commit log, exclusions register.

---

## 0. Hard rules

1. **Commit only. Do not change code.** No edits, no formatting, no "quick fixes" to make a test pass, no deletions of source. If something looks broken, note it in the report and commit it as-is; a broken file that is committed is recoverable, an uncommitted one is not.
2. **Never run the pipeline.** No `intelligent_orchestrator.py`, no `morning_gate.py`, no Lab server, no provider calls. You may run `pytest --collect-only` to check that a test tree imports, and you may run individual offline test files if it helps you describe a commit, but a failing test never blocks a commit under this prompt.
3. **No destructive git.** No `reset --hard`, no `checkout -- <file>`, no `clean`, no `stash drop`, no `rebase`, no `push --force`, no branch deletion, no history rewriting, no merging of branches. If you believe one of these is needed, stop and ask ACK.
4. **Secrets are a hard stop.** Before every commit, scan the staged diff for anything that looks like a credential: `ANTHROPIC_API_KEY`, `MARKETDATA_API_KEY`, `POLYGON_API_KEY`, `sk-`, `.env`, `.env.txt`, `.env.*`, `secrets`, `token`, base64 blobs, and any 20+ character alphanumeric string assigned to a variable whose name suggests a key. If a match is a real value, unstage it, add the path to `.gitignore` if it is a file, and record it in the exclusions register with the path and variable name only — **never echo the value** into the terminal, a commit message, or the report. If a key value is already in an existing commit, do not attempt to rewrite history; report it and stop that commit group.
5. **Do not commit run artefacts, databases, caches or backups.** Exclude by default: `data\`, `dropbox\`, `*.db`, `*.sqlite*`, `*.parquet`, `*.pkl`, `*.bak`, `*_backup*`, `*.orig`, `__pycache__`, `.pytest_cache`, `.venv`, `venv`, `*.log`, `*.xlsx` under output paths, `node_modules`. If any of these are currently tracked and modified, leave them unstaged and list them in the register for ACK to decide. If a JSON under `contracts\` or a checked-in runtime profile is modified, that **is** code and should be committed.
6. **One workstream per commit.** Never one giant commit. Never a commit whose message is "misc" or "wip".
7. **Attribution.** End every commit message with the two lines below, exactly:

   ```
   Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
   Claude-Session: https://claude.ai/code/session_01DyN6iHjTxkW7cvHyBmGwnU
   ```

8. **Report honestly.** If you could not classify a file, say so. If a commit group is a guess, say it is a guess.

---

## 1. Establish where you are

Record all of this in `01_state.md` before touching anything:

- `git rev-parse --abbrev-ref HEAD`, `git rev-parse HEAD`, `git status --porcelain=v1 | Measure-Object -Line`
- `git branch -a --format="%(refname:short) %(objectname:short) %(upstream:short)"`
- `git tag --list "avs-*" --sort=-creatordate` with the commit each points to
- `git log --oneline -20`
- `git stash list`
- Whether a remote exists (`git remote -v`). If none, this prompt ends at local commits and a tag; say so.
- Whether `.gitignore` exists and what it currently excludes.

Known history you should expect to see, and must reconcile against (from earlier audits — treat as hints, not facts): a tag `avs-baseline-20260906` on the pre-fix tree; a branch `avs-fix-001` at `00baa2b` that was never merged; a large volume of uncommitted work from 4–6 Sep (63 modified / 33 untracked at the time of QT-D02) and further uncommitted work from the DOI build on 8–10 Sep (DOI-1 through DOI-11: new domain packages, option-lifecycle schema extensions, DOI regression tests, Lab projection, orchestrator wiring); around 95 `.bak` copies and 127 untracked `.py` files historically lying around the tree; an unauthorised `domain\` package (QT-D11) which is now presumably the home of the DOI work.

**Stop and ask ACK before proceeding if any of these is true:** HEAD is detached; a merge or rebase is in progress; the current branch is neither `main`/`master` nor an `avs-*` branch; `git status` shows conflict markers.

Otherwise, decide the target branch as follows and record the reason: if you are on `avs-fix-001` or another `avs-*` working branch that contains the recent commits, commit there. If you are on the default branch and the uncommitted work clearly continues `avs-fix-001`, do **not** merge — create a new branch `avs-ops-002-commit-20260911` from HEAD and commit there, so ACK can merge deliberately.

---

## 2. Inventory every change

Produce `02_inventory.csv` with one row per path from `git status --porcelain=v1 -uall`, columns:

`path | status (M/A/D/??/R) | size_bytes | last_modified | extension | is_test | is_data_or_artifact | is_backup | is_secret_risk | workstream_guess | commit_group | include (Y/N) | reason`

To fill `workstream_guess`, use the evidence in the file itself and its neighbours, not the file name alone. Read the top of every modified `.py` and every untracked `.py` (docstring, imports, class names). Expected workstreams, in rough chronological order:

- `FIX-001` — AVS-IMP-FIX-001 items W0/W1 (flag-test fix, tests\msi in matrix, venv pin, CLI hygiene, structural_target null guard, EIL telemetry suppression, monetisability_authority stamp, profile guard semantics, contract_dte, per-horizon spread authority; `check_run_gates.py`, `check_warm_rerun.py`)
- `DDD` — dynamic-session dispatcher / runtime profile / build receipt work (`contracts\dynamic_session_runtime_v1.json` and successors, plan-hash receipt, single pipeline_run_id, MarketData `to`-boundary fix)
- `DOI-1..DOI-11` — Dynamic Options Intelligence phases; split by phase where the file evidence supports it, otherwise group as `DOI-domain`, `DOI-tests`, `DOI-lab`, `DOI-wiring`
- `MI` — US Money Index sidecar (`us_money_index_latest.json` contract, `regime_alignment`, `ars_z`) if present
- `GEX` — GEX proxy consumers (`build_macro_json.py` Data_Mode lookup) if present
- `AUDIT` — anything under `audit\` (reports, prompts, findings)
- `UNKNOWN` — cannot tell; list separately in the report

For untracked `.py` files, additionally check whether anything imports them (`grep` for the module name across the tree). An untracked module that nothing imports and that has no test is a candidate for `UNKNOWN`; do not include it in a code commit without saying so.

---

## 3. Commit plan — get sign-off before executing

Write `03_commit_plan.md`: an ordered list of commit groups, each with the files, the proposed message (subject ≤ 72 chars, body explaining what and why, referencing the AVS-* document it implements), and any file you were unsure about. Order: `AUDIT` docs can go first or last (they carry no code risk); code groups in chronological workstream order; `.gitignore` changes in their own first commit if needed.

Suggested subject shapes:

- `fix(w0): honour runtime profile in feature-flag default test (AVS-IMP-FIX-001 W0.2)`
- `feat(doi-2): contract-entry state vocabulary and append-only ContractFamily schema (AVS-SD-DOI-001)`
- `feat(doi-10): read-only DOI projection over governed Lab book, ALL OPPORTUNITIES default`
- `feat(doi-11): wire DOI into evening orchestrator after horizon propagation`
- `test(doi): 120-test DOI regression pack`
- `chore(git): ignore run artefacts, databases, backups and env files`
- `docs(audit): AVS-TST-DOI-001 tester prompt and DOI claim register`

**Then stop and present the plan to ACK in the chat**, with: number of files to commit, number excluded and why (by category), anything in `UNKNOWN`, and any secret-risk finding. Wait for ACK to reply `go` (or amend the plan) before Section 4. If ACK is not available and you are running unattended, do not commit; leave the plan and end.

---

## 4. Execute the commits

For each group in order:

1. `git add` exactly the listed paths (never `git add -A` or `git add .`).
2. `git diff --cached --stat` and the secrets scan from rule 4 on `git diff --cached`. Abort the group on any hit.
3. Commit with the approved message plus the attribution lines.
4. Append to `04_commit_log.md`: commit hash, subject, file count, insertions/deletions.

After all groups: `git status --porcelain` — anything remaining must appear in `05_exclusions.md` with a reason (`data/artefact`, `backup`, `secret`, `unknown — needs ACK`, `deliberately left for ACK`). Then create an annotated tag `avs-committed-20260911` on the final commit with a message listing the workstreams it contains. Do not push unless ACK has said so.

---

## 5. Final report

`06_report.md`, one page: branch and HEAD before and after; commits made (hash, subject); files committed / excluded / unknown, split by workstream; secret-risk findings (paths only); whether `.gitignore` was changed; whether any test tree failed to collect; what ACK still needs to decide (unknown files, tracked artefacts, the unmerged `avs-fix-001` branch, push). Confidence rating per workstream classification.

Last chat message to ACK: the tag name, the commit count, the count of files left uncommitted, and the path to `06_report.md`. Nothing else.
