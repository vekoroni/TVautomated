"""AVS-TRACE-001: build 01_traceability_matrix.csv from the register, the inbox extractions and the document-ID
extractions. Read-only on everything outside audit\\trace\\AVS-TRACE-001. Rerun: venv\\Scripts\\python.exe <this file>."""
import csv, json, re, collections, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1]
EV = OUT / "evidence"
REG = ROOT / "data/scratch/workaround/lessons/fix_register.csv"
REGP = r"data\scratch\workaround\lessons\fix_register.csv"
INB = r"data\scratch\workaround\lessons\fix_inbox" + "\\"
HIGH = {"contract_choice", "hold_window", "liquidity", "quote_freshness", "exit_rules", "outcome_measurement", "ranking"}
MED = {"pricing_model", "earnings_events", "data_quality", "etf"}
COLS = ["trace_id", "source_ids", "title", "source_documents", "raised_date", "raised_by", "owner", "lane", "branch",
        "commits", "files_changed", "tests", "run_evidence", "status", "status_evidence", "superseded_by",
        "conflicts_with", "monetisation_impact", "notes"]


def jl(name):
    return [json.loads(l) for l in open(EV / name, encoding="utf-8") if l.strip()]


reg = list(csv.DictReader(open(REG, encoding="utf-8-sig")))
for n, r in enumerate(reg, 2):
    r["_line"] = n
inbox = jl("inbox_candidates_A.jsonl") + jl("inbox_candidates_B.jsonl")
docs = jl("doc_ids_fix002.jsonl") + jl("doc_ids_other.jsonl")

# ---------------------------------------------------------------- curated rows (verified in this review)
C = {}


def cur(tid, title, lane, owner, status, ev, impact, *, src=(), reg_ids=(), doc_ids=(), kw=None, branch="", commits="",
        files="", tests="", run="", notes="", sup="", conf="", date="", by=""):
    C[tid] = dict(trace_id=tid, title=title, lane=lane, owner=owner, status=status, status_evidence="VERIFIED_IN_REVIEW: " + ev,
                  monetisation_impact=impact, branch=branch, commits=commits, files_changed=files, tests=tests,
                  run_evidence=run, notes=notes, superseded_by=sup, conflicts_with=conf, raised_date=date, raised_by=by,
                  _src=set(src), _docs=[], _reg=set(reg_ids), _doc=set(doc_ids), _kw=re.compile(kw, re.I) if kw else None)


H = r"data\scratch\workaround\handoff\lab_2026-11-12\handoff.csv"
CFG = r"config\governed_constants_v1.json"
CODEX = r"C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a" + "\\"
cur("TR-001", "Thesis clock too slow for the 1-20 session mandate; trading-window flag", "A", "Codex (pipeline flag); Claude Code (Lane B flag)",
    "APPROVED", f"ACK 13 Nov: window is a flag (Enhancements\\tradeability\\AVS-TRADE-001_status_and_decisions_2026-11-13.md:56). {H}: lb_window_flag OUTSIDE_WINDOW 1,499, IN_WINDOW 591, NOT_ASSESSED 42 of 2,132. No trade_window_state in pipeline code.",
    "HIGH", src=["13NOV-FLAW-1", "13NOV-FIX-8", "FIXLIST-D1", "TRADE-W3", "TRADE-DECISION-2", "E2"], reg_ids=["A16-04"],
    kw=r"outside.{0,12}window|1.?(–|-|to).?20 session|trading window", run="20261111_231951 (Lane B proxy flag only)",
    notes="Lane B flag built on PROXY_Q50 (60d0511); pipeline flag W3 not built. ETF baseline: 15 of 62 ETF rows within 20 sessions.", date="2026-11-13", by="ACK / Claude chat")
cur("TR-002", "Contract runway: contract chosen from the monetisation clock n, not penalised 3 points a day", "A", "Codex",
    "APPROVED", f"ACK 12 Nov (A12) and 13 Nov: contract from n, hold stays ({CFG}:120 'the horizon informs contract choice, it never gates it'; :135 COVERS_PLANNED_HOLD). {H}: 1,005 expire before the median arrival, 481 before q80. No contract_covers_n in code (grep).",
    "HIGH", src=["13NOV-FLAW-2", "13NOV-FIX-5a", "FIXLIST-A1", "TRADE-W2", "TRADE-DECISION-1", "E10", "config:long_option_contract_selection"],
    reg_ids=["N17-07", "N17-11"], doc_ids=["DESK-GATE:D4", "DESK-GATE hard stop:H9", "REQ-WP2-03", "UAT-D13", "RCA-03", "M_REGISTER:M4"],
    kw=r"expires? before|covers? (the )?(hold|q80)|14.?(day|dte).{0,30}(q50|q80)|runway",
    conf="13 Nov pasted plan and FIXLIST-A1 ('0 rows expiring before q80') vs ACK's A12; docs\\AVS-SD-DOI-001:306 hard-excludes short DTE; docs\\AVS-SD-MON-003:598 (M4)",
    notes="Uncommitted working-tree edits add expiry_session_check_state (domain\\option_contract_liquidity.py), on no branch.", date="2026-09-18", by="ACK")
cur("TR-003", "Switch value_selection_mode SHADOW to ACTIVE; rank contracts by return per premium dollar", "A", "ACK (decision)",
    "DECISION_PENDING", f"{CFG}:132 value_selection_mode SHADOW; :136 'ACK switches to ACTIVE'. Open decision 5 in the tradeability sheet (:64). CLAUDE.md rule 5 applies.",
    "HIGH", src=["13NOV-FIX-5c", "TRADE-DECISION-5"], reg_ids=["R14-08"], doc_ids=["INT_REGISTER_25SEP:B1", "INT_REGISTER_25SEP:B2", "INT_REGISTER_25SEP:B3", "INT_REGISTER_25SEP:B4"],
    date="2026-10-14", by="deep dives")
cur("TR-004", "One liquidity standard (11 Nov tiers) owned in the pipeline; spread units", "A", "Codex",
    "PROPOSED", f"{H}: lb_saved_gate C 1,697, B 248, A 99, no contract 88. Tiers exist in Lane B only (data\\scratch\\workaround\\build_lab_handoff.py:172). {CFG}:177-185 holds 0.18 / 0.25 / 0.08 / 0.15 and calls one policy 'a later decision'.",
    "HIGH", src=["13NOV-FLAW-3", "13NOV-FIX-5b", "TRADE-W2-tiers"], reg_ids=["A16-01", "W5", "W6", "W16-02"],
    doc_ids=["DESK-GATE:D15", "DESK-GATE:D9", "FIX-002 register:F1.5", "FIX-002 register:F1.6", "REQ-WP1-03", "UAT-D10", "RCA-01", "RCA-003 decision:DEC-3", "RCA3-D07"],
    kw=r"25 ?%|spread gate|spread.{0,20}(tier|of mid)|oi ?(<|under|≥|>=) ?100",
    conf="Six spread limits in force: 25% (W16-02), tiers 10/20% (11 Nov), 0.18/0.25 (config:177), 0.10 (AVS-INT-001_WEEKEND_POLICY_RECEIPT:15), 15% (desk H4), 20% card gate vs 25% monitor gate (fix_inbox\\2026-11-13_monitor_PRECLOSE.md)",
    notes="W16-02 is 'Built' in the register (25% rule) and superseded by the 11 Nov tiers; 19 later inbox reports. Argued both ways in the inbox: too strict (LTC, GO, ASO 29-30 Oct) and too loose (UHS 12 Nov).", date="2026-10-16", by="week review")
cur("TR-005", "Quote freshness: delayed MarketData feed against a 900 s freshness limit", "A", "Codex; ACK (data plan)",
    "APPROVED", f"{CFG}:109-110 disclosed_delay_seconds 900, freshness_max_seconds 900. audit\\verify\\20261111_231951\\morning\\verify_report.md: R19_QUOTE_FRESH FAIL, 4 of 4 tradeable rows on quotes 53-58 min old.",
    "HIGH", src=["13NOV-FLAW-4"], doc_ids=["DESK-GATE:D18", "FIX-002 register:F0.2", "REQ-WP0-04", "ALG-12", "UAT-D02", "UAT-D06", "RCA-02"],
    kw=r"stale quote|quote (age|time)|day-old quote", run="20261111_231951 (shows the defect)", date="2026-09-10", by="desk gate")
cur("TR-006", "Morning pricing starts 09:35-09:45 ET; late-start guard", "A", "Codex; ACK (decision)",
    "BUILT_UNMERGED", "Uncommitted and on no branch: domain\\morning_pricing_window.py, config\\morning_pricing_policy_v1.json (outside_window_action STOP_BEFORE_PRICING), wired at intelligent_orchestrator.py:7971-7980 and morning_gate.py:3486, 3664. Codex: GARCH_D1_RELEASE_20261113.json 'follow_on_work'.",
    "HIGH", src=["13NOV-FIX-2", "TRADE-DECISION-6"], reg_ids=["D3"], doc_ids=["QA:R7"], tests="tests\\test_morning_pricing_window.py (untracked; result not recorded)",
    conf="Tradeability sheet 13 Nov lists Morning late-start as an open decision; ACK's rule 'flag quote age, never gate on it'. The guard refuses the run.",
    notes="A Morning run started outside the window returns without pricing. Run 20261111_231951 Morning ran 10:42 ET; 20261021_222556 at 13:42 ET.", date="2026-10-14", by="register D3")
cur("TR-007", "Tastytrade live re-quote at entry", "B", "ACK (decision)", "DECISION_PENDING",
    "Tradeability sheet decision 7 open. Conflicts with ACK's rule that option quotes come from MarketData only.", "HIGH",
    src=["13NOV-FIX-3", "TRADE-DECISION-7"], conf="Options data = MarketData only (ACK); triage already takes a live quote from Tastytrade for live_gate", date="2026-11-13", by="Claude chat")
cur("TR-008", "GARCH D1: cumulative trading-session expected moves, not differences between windows", "A", "Codex",
    "BUILT_UNMERGED", "Commit fff3a3e on fix/garch-d1-cumulative-windows-20261113 (4 files); same files uncommitted in the working tree (evidence\\branch_vs_worktree.txt). Last commit on the checked-out line still has the differences at layer3_forward_variance.py:690-692.",
    "HIGH", src=["13NOV-FLAW-5a", "13NOV-FIX-4", "GARCH-D1"], doc_ids=["DESK-GATE:D1", "FIX-002 register:F1.1", "WP1", "REQ-WP1-01", "REQ-WP1-02", "ALG-01", "UAT-D44", "DISC-F12", "APPROVED-0925:Item 4", "APPROVED-0925:Item 4.1", "INT_REGISTER_25SEP:C3"],
    branch="fix/garch-d1-cumulative-windows-20261113", commits="fff3a3e", files="layer3_forward_variance.py; domain\\volatility_budget.py",
    tests="tests\\test_garch_d1_cumulative_windows.py; 116 pass, 1 skipped (" + CODEX + "GARCH_D1_RELEASE_20261113.json)", run="AWAITING_RUN",
    notes="CLAIM_NOT_SUPPORTED: docs\\AVS-INT-001_HORIZON_UNIT_REPAIR_20260926.md:3 says 'implemented and offline-tested' and audit\\avs_fix_002\\stage2_5\\STAGES2_5_CLAIM_SHEET.md:5 says PASS, yet the defect was open on 13 Nov. Four consumers read the differenced fields (UAT-D44); domain\\pretrade_focus.py:248-253 not in the fix commit.",
    date="2026-09-10", by="desk gate D1")
cur("TR-009", "Monetisation clock n published (A12)", "A", "Codex", "BUILT_UNMERGED",
    "Commit b709669 on feat/a12-monetisation-clock-20261112. The monetisation files are absent from the working tree (evidence\\branch_vs_worktree.txt). " + H + ": monetisation_state NOT_PUBLISHED on all rows.",
    "HIGH", src=["13NOV-FLAW-5b", "13NOV-FIX-7", "FIXLIST-A12", "TRADE-W1"], reg_ids=["D1"],
    doc_ids=["RCA-003 decision:DEC-1", "FIX-002 register:F1.3", "REQ-WP2-04", "ALG-04", "ALG-05", "RCA-05", "APPROVED-0925:Item 2"],
    kw=r"monetis", branch="feat/a12-monetisation-clock-20261112 (stacked on fix/ac-reliability-20261112)", commits="b709669",
    files="avshunter\\c12_outcome\\monetisation.py; contracts\\monetisation_clock.py; config\\monetisation_clock_v1.json; scripts\\publish_monetisation_clock.py",
    tests="tests\\test_a12_monetisation_clock.py; 84 pass (" + CODEX + "A12_IMPLEMENTATION_RESULT_20261112.json)", run="AWAITING_RUN",
    notes="On saved run 20261111_231951 only 39 of 2,800 rows get an n at +20% and 21 at +30%: coverage is too thin to choose contracts from yet. Field name: branch publishes its own names; Lane B reads monetisation_threshold (build_lab_handoff.py:66). ID collision: register D1 (14 Oct, monetisability) vs fix-list D1 (window) vs GARCH D1.",
    date="2026-10-14", by="register D1; ACK 12 Nov")
cur("TR-010", "Outcome ledger for every card, traded or not (option outcomes)", "B", "Claude Code", "APPROVED",
    "Brief issued 13 Nov (audit\\trace\\AVS-TRACE-001\\inputs\\AVS-LEDGER-001_card_outcome_ledger_brief.md). Not built: no card_outcomes.py. data\\scratch\\workaround\\decision_ledger_*_outcomes.csv exist for 12, 13, 14 Oct only; six later ledgers unscored.",
    "HIGH", src=["13NOV-FLAW-5c", "13NOV-FIX-9", "AVS-LEDGER-001", "E15"], reg_ids=["W4", "A16-03", "W16-12", "G8", "N8", "T1", "N6", "N7"],
    doc_ids=["FIX-002 register:F3.5", "QA:R2", "WP7", "WP7A", "WP7B", "REQ-WP7-01", "REQ-WP7-02", "UAT-D33", "UAT-D56", "RCA-13", "APPROVED-0925:Item 7", "APPROVED-0925:Item 6", "DOI-7", "LESSONS_REGISTER_12OCT_R:R3", "LESSONS_REGISTER_12OCT_L:L7"],
    notes="Research package holds a partial equivalent (dropbox\\macro\\coaching\\model\\outcomes\\decision_events.sqlite: 20,782 decisions, 1,060 option rows scored) that is not a card ledger. Same need raised under at least 20 IDs since 10 Sep.", date="2026-09-10", by="desk gate")
cur("TR-011", "Two or three contract alternatives on the card", "A", "Codex", "PROPOSED",
    "Uncommitted contracts\\lab_review_projection.py adds contract_value_alternatives and doi_alternatives_json; no contract_alternative* column in " + H + ".",
    "HIGH", src=["13NOV-FIX-6", "FIXLIST-A8"], date="2026-11-12", by="fix list")
cur("TR-012", "Lane B switched to the Lab hand-off (Fix B, B0-B10)", "B", "Claude Code", "CLOSED_OFFLINE",
    "8 commits 1e43e6b..016b301 on laneb/lab-first-handoff; 48 tests pass (audit\\laneb_fixB\\triage_prompt_update_2026-11-13.md section 4); built on stored run 20261111_231951 only; data\\scratch\\workaround\\day_settings.json handoff_source LEGACY.",
    "HIGH", src=["13NOV-FIX-1", "FIX-B", "B0", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "B10"], branch="laneb/lab-first-handoff",
    commits="1e43e6b; 7f604d1; 572a904; 60d0511; 99ee568; 26c6f3e; 163e933; 016b301", files="data\\scratch\\workaround\\lab_reader.py; build_lab_handoff.py; check_triage.py; collect_decisions.py; avs_day.ps1",
    tests="48 pass on 13 Nov", run="AWAITING_RUN (first Lab-first cycle)", notes="B5, B8, B9 not built. Report's commit table omits 163e933 and 016b301. Report counts 3 GO_LIMIT; brief said 4.", date="2026-11-12", by="ACK / Claude chat")
cur("TR-013", "Retire or adapt old-layout scripts and the X17 spread-gate test", "B", "ACK (decision)", "DECISION_PENDING",
    "tests\\test_x17_check_triage_spread_gate.py pins the removed 25% rule and now fails by design (triage_prompt_update_2026-11-13.md section 3); quickkill.py and capture_score.py still use 25% (audit\\laneb_fixB\\needs_codex.md).",
    "MEDIUM", src=["13NOV-FIX-10"], reg_ids=["X17-02"], notes="Register X17-02 is 'Built' with this test as closure evidence: CLAIM_NOT_SUPPORTED since 12 Nov.", date="2026-10-17", by="Claude Code")
cur("TR-014", "Premium cap ($5) as a flag with an over-cap lane", "both", "Codex (pipeline flag); ACK (account-based cap)", "APPROVED",
    "ACK 13 Nov: cap is a flag. " + H + ": lb_over_cap OVER_CAP 848, WITHIN_CAP 1,196. Cap defined in Lane B only (avs_day.ps1:48; build_lab_handoff.py:75-76). Register W16-08: account-based cap still open.",
    "HIGH", src=["FIXLIST-D2", "TRADE-W4", "TRADE-DECISION-3", "E9"], reg_ids=["W16-08", "D2"], kw=r"premium cap|\$5 cap|over.?cap",
    notes="No contract passes cap and spread for 11 to 25 of 30 names per batch (fix_inbox 11-12 Nov). QQQ: 0 near-the-money contracts within $5.", date="2026-10-16", by="ACK")
cur("TR-015", "Station quarantine: one bad row no longer stops the run", "A", "Codex", "BUILT_UNMERGED",
    "Commit 58a4904 on fix/station-quarantine-20261113; 6 of 9 files identical in the working tree, 3 differ. Saved replay of 20261112_230902 PASS (" + CODEX + "STATION_QUARANTINE_SAVED_VERIFICATION_20261113_v2.json).",
    "MEDIUM", src=["STATION-QUARANTINE"], branch="fix/station-quarantine-20261113", commits="58a4904", tests="tests\\test_station_quarantine.py (count not recorded)",
    run="AWAITING_RUN; defect shown by 20261112_230902 (STOPPED at Discovery, RBOT)", notes="Config approval 'ACK, 13 November 2026' is stated in the receipt on the branch.", date="2026-11-13", by="run failure")
cur("TR-016", "Production eligibility: refuse a standard production run on uncommitted code", "A", "Codex", "BUILT_UNMERGED",
    "Commit eb50549 on fix/production-eligibility-20261112; none of its new files are in the working tree. Runs 20261110_231648 and 20261111_231951 carry run_condition TEST, baseline_eligible false (run_meta.json).",
    "LOW", src=["PRODUCTION-ELIGIBILITY"], branch="fix/production-eligibility-20261112", commits="eb50549", run="AWAITING_RUN",
    notes="Merge last: with 64 modified files it would refuse the run.", date="2026-11-12", by="Codex")
cur("TR-017", "A/C reliability: exact XNYS session clocks, hand-off reliability contract", "A", "Codex", "BUILT_UNMERGED",
    "Commit da9a922 on fix/ac-reliability-20261112; 9 of 14 files in the working tree. " + CODEX + "AC_RELIABILITY_VERIFICATION_20261112.json: SAVED_DATA_VERIFIED_NOT_LIVE_PUBLISHED.",
    "HIGH", src=["AC-RELIABILITY", "FIXLIST-A (Codex part)", "FIXLIST-C (Codex part)"], branch="fix/ac-reliability-20261112", commits="da9a922", tests="465 pass (Codex record)", run="AWAITING_RUN",
    notes="The commit message does not say which fix-list A and C items it closes; they are kept as separate PROPOSED rows (TR-FL-*).", date="2026-11-12", by="fix list")
cur("TR-018", "PHANTOM scoring speed, IV acknowledgement, hold-period lineage", "data", "Codex", "BUILT_UNMERGED",
    "Commit 1332983 on phantom-scoring-iv-hold-fixes-20261111; 5 of 6 files in the working tree.", "MEDIUM", src=["PHANTOM-SCORING"], reg_ids=["UAT-04", "UAT-05"],
    branch="phantom-scoring-iv-hold-fixes-20261111", commits="1332983", tests="69 pass (commit message)", run="20261111_231951 ran with an uncommitted copy; no artefact found showing the fix itself", date="2026-10-17", by="UAT")
cur("TR-019", "PHANTOM path completeness; guarded historical backfills (13 Nov)", "data", "Codex", "BUILT_UNMERGED",
    "Commit f845857 on fix/phantom-path-completeness-safeguards-20261113. Data action: 466,193 rows, 6,205 credits consumed, 7,187 reserved (" + CODEX + "OPTION_PATH_GAP_AUDIT_AFTER_20261113.json).",
    "MEDIUM", src=["PHANTOM-PATH", "PHANTOM-BACKFILL-20261113"], branch="fix/phantom-path-completeness-safeguards-20261113", commits="f845857", tests="33 pass before the resume (Codex record)", run="n/a (data action)",
    notes="The commit also carries Lane B files and three AVS-MODEL-001 research scripts. 12 Nov deferred: 40 entry chains, 20 path quotes.", date="2026-11-13", by="Codex")
cur("TR-020", "PUT base rates wrong in EV v2", "A", "Codex", "PROPOSED", "ev_engine_v2.py:92-94 (confirmed open in the tradeability sheet :35-37); no approved root cause and design.", "HIGH",
    src=["PUT-BASE-RATES"], doc_ids=["DESK-GATE:D17", "FIX-002 register:F1.7"], date="2026-09-10", by="desk gate")
cur("TR-021", "Actuarial match drops dimensions", "A", "Codex", "PROPOSED", "actuarial_query.py:653, 667, 1002-1016 (tradeability sheet); no approved design.", "HIGH", src=["DROPPED-DIMENSIONS"], date="2026-11-13", by="Claude Code")
cur("TR-022", "One shared change log, written by every agent", "ops", "all agents", "APPROVED",
    "data\\scratch\\workaround\\lessons\\change_log.md: last entry 20 Oct (file saved 20 Oct 10:44); 12 unlogged commits on branches and 8 on the line since. Rule restated in inputs\\AVS-CHANGELOG-001_shared_change_log_rule.md.",
    "LOW", src=["AVS-CHANGELOG-001"], reg_ids=["X17-05", "D8"], notes="Register X17-05 and D8 are 'Built': CLAIM_NOT_SUPPORTED, the log lapsed after three days. audit\\fix_receipts\\ (required by the rule) does not exist.", date="2026-10-17", by="ACK")
cur("TR-023", "Fix register kept current; inbox triaged into it", "ops", "monitoring chat / ACK", "PROPOSED",
    "fix_register.csv last saved 17 Oct 17:59; 96 inbox files (855 candidates) dated 18 Oct to 13 Nov never moved to fix_inbox\\processed\\.", "LOW", src=["REGISTER-LAPSE"], date="2026-11-14", by="this review")
cur("TR-024", "Macro delivery and FULL publication guards", "macro", "Codex", "BUILT_UNMERGED", "Commit 4601ce5 on macro-delivery-publication-guards-20261110; 21 of 32 files in the working tree.", "LOW",
    src=["MACRO-DELIVERY"], branch="macro-delivery-publication-guards-20261110", commits="4601ce5", run="board rebuild 10 Nov (Codex: MACRO_FULL_REBUILD_VERIFICATION_20261110.json); no pipeline run", date="2026-11-10", by="Codex")
cur("TR-025", "Macro board events sorted by source timestamp", "macro", "Codex", "BUILT_UNMERGED", "Commit 66d0501 on macro-board-event-timestamp-sort-20261110.", "NONE", src=["MACRO-EVENT-SORT"],
    branch="macro-board-event-timestamp-sort-20261110", commits="66d0501", run="board rebuild (Codex: ETF_BOARD_EVENT_SORT_VERIFIED_20261110.json)", date="2026-11-10", by="Codex")
cur("TR-026", "Absent gamma flips; explicit US Money Index text flag", "macro", "Codex", "BUILT_UNMERGED", "Commit 4d47a85 on macro-null-usmi-fixes (17 Oct); overlaps macro delivery in contracts\\us_money_index_contract.py lines 204-230.", "NONE",
    src=["MACRO-NULL-USMI"], branch="macro-null-usmi-fixes", commits="4d47a85", run="NOT FOUND (looked in audit\\verify, Enhancements\\maintenance_repairs)", date="2026-10-17", by="Codex")
cur("TR-027", "Lab macro desk, Market Mentality, Worker 3 retired", "macro", "Codex", "MERGED",
    "bb65704 on the checked-out line (19 Oct). Older branches macroboard-lab-worker3-decommission (0724adf) and market-mentality-redesign (a4f0ecc) differ from it in 12 and 6 files and are unmerged.", "NONE",
    src=["LAB-MACRO-DESK"], doc_ids=["LAB_MACRO_DESK:LAB_MACRO_DESK"], branch="avs-fix-001 line; two stale branches", commits="bb65704; 0724adf; a4f0ecc", run="NOT FOUND",
    conf="Worker 3 state stated three ways: docs\\AVS-W3-SD-003.md:3 'active', docs\\AVS-REL-20260923-1_WORKER3_PAUSE.md:5 INSTALLED_DISABLED, docs\\LAB_MACRO_DESK_AND_WORKER3_RETIREMENT.md:22 DECOMMISSIONED_RETAINED", date="2026-10-18", by="Codex")
cur("TR-028", "today_context rolls every session; no stale session", "B", "Claude Code", "PROPOSED",
    "61 inbox reports 19 Oct to 13 Nov (register_match N17-01); on 13 Nov today_context showed session 12 Nov, run_state running (fix_inbox\\2026-11-13_triage.md).", "MEDIUM",
    reg_ids=["N17-01", "F14-07"], kw=r"today_context", notes="F14-07 is 'Built' (14 Oct): CLAIM_NOT_SUPPORTED, 14 later reports. B7 does not cover the failed roll of 13 Nov.", date="2026-10-15", by="monitors")
cur("TR-029", "Scheduled tasks attached to this computer; alert on a missing report", "ops", "ACK (task settings)", "PROPOSED",
    "17 inbox reports; macro thesis task had no folder attached (fix_inbox\\2026-11-03_macro.md); monitors late on 2, 4, 5, 9, 11 Nov.", "MEDIUM", reg_ids=["N17-13"], date="2026-10-15", by="monitors")
cur("TR-030", "Resting exit order within 5 minutes of a fill", "B", "ACK (execution)", "NOT_FOUND",
    "Register W16-05 'Built' as an execution rule and monitor alert (no code). 45 later inbox reports: OI Dec18 5P held since 13 Oct, stop 22 Oct, time stop 27 Oct, target 29 Oct, no resting exit (every monitor file to 13 Nov).",
    "HIGH", reg_ids=["W16-05"], notes="CLAIM_NOT_SUPPORTED. fix_inbox\\2026-11-05_monitor_PRECLOSE.md asks ACK whether exit tickets are read at all.", date="2026-10-16", by="week review")
cur("TR-031", "Criteria met, no order; order outcome recorded", "B", "ACK (execution); Claude Code (records)", "NOT_FOUND",
    "Register W16-04 'Built' (tickets). 18 later reports: ADTN 27 Oct, AAL 5 Nov, ATEN 11-12 Nov, UHS 11 Nov, CPNG 12-13 Nov; five 22 Oct cards decided and never recorded (fix_inbox\\2026-11-11_triage.md).",
    "HIGH", reg_ids=["W16-04", "R14-14", "N17-16"], notes="CLAIM_NOT_SUPPORTED. B10 (decision record per card) built offline, see TR-012.", date="2026-10-16", by="week review")
cur("TR-032", "Earnings date present in the hand-off; null is MISSING, never 'no event'", "B", "Claude Code", "MERGED",
    "Register W1/F14-01 'Built' 14 Oct (build_mining_handoff v2). 16 later reports: 57 of 60 names null on 19 Oct (fix_inbox\\2026-10-19_triage.md).", "MEDIUM",
    reg_ids=["W1", "F14-01", "N17-04"], doc_ids=["LESSONS_REGISTER_12OCT_R:R5"], notes="CLAIM_NOT_SUPPORTED: regression of a Built fix. Legacy hand-off; to be re-checked on the Lab hand-off.", date="2026-10-14", by="parallel-run review")
cur("TR-033", "Correlation and beta from the price store; Tastytrade metric traps", "B", "Claude Code", "PROPOSED",
    "31 inbox reports (N17-03). XLE: Tastytrade 0.77 / 0.49 vs store -0.311 / -0.612 (recomputed, evidence\\etf_evidence_check.md E8).", "MEDIUM", src=["E8"], reg_ids=["N17-03"], date="2026-10-14", by="deep dives")
cur("TR-034", "Sector / money-tag map: real industry map, ETFs mapped to themselves", "both", "Codex (map); Claude Code (rank)", "PROPOSED",
    "W2, R14-04, A16-02 all Proposed since 14-16 Oct; 16 inbox reports; all 51 UNMAPPED rows on the 12 Nov ledger are ETFs (build_thesis_ledger.py:275-278).", "MEDIUM",
    src=["E4"], reg_ids=["W2", "R14-04", "A16-02", "W16-03"], doc_ids=["LESSONS_REGISTER_12OCT_R:R4"], notes="W16-03 (rank by money tag) is 'Built' on top of a map known to be wrong.", date="2026-10-14", by="parallel-run review")
cur("TR-035", "NO_DIRECTION label; failed-breakout setup", "A", "Codex", "PROPOSED", "R14-01, R14-02, A16-08 Proposed since 14 Oct; 9 later reports (BKSY, CAVA, CBRL, DQ, GO, ADTN handed over as CONFIRMED).", "MEDIUM",
    reg_ids=["R14-01", "R14-02", "A16-08"], date="2026-10-14", by="deep dives")
cur("TR-036", "Hand-off inside the trigger session", "both", "Codex / Claude Code", "PROPOSED", "D5, R14-12, A16-05 Proposed; phase8 R1.", "HIGH",
    reg_ids=["D5", "R14-12", "A16-05"], doc_ids=["LESSONS_REGISTER_12OCT_R:R1"], date="2026-10-12", by="lessons register")
cur("TR-037", "One American pricing engine with dividends in both lanes", "both", "Claude Code / Codex", "CLOSED_OFFLINE",
    "G5-MIN, G9-GUARD: commits c175576, 5b4fc6a on the checked-out line with tests (tests\\test_g9_no_new_option_pricer.py). G5-REST approved for 24 Oct: no commit or log entry shows it was done. 11 later reports that triage still prices European with no dividend.",
    "MEDIUM", src=["E7"], reg_ids=["G5-MIN", "G9-GUARD", "G5-REST", "G6"], commits="c175576; 5b4fc6a", tests="tests\\test_g5_*; tests\\test_g9_no_new_option_pricer.py", run="NOT FOUND",
    notes="G5-REST: NOT FOUND (looked in git log 24 Oct to 13 Nov, change_log.md, fix_inbox).", date="2026-10-17", by="options valuation review")
cur("TR-038", "Kill-switch acceptance rule (two closes or a band)", "macro", "ACK (rule)", "DECISION_PENDING",
    "Requested in at least eight inbox files 3-12 Nov and as fix-list C6; undefined. SPY closed 749.92 against a 750 switch.", "LOW", src=["FIXLIST-C6"], kw=r"kill.?switch|two.?close", date="2026-11-03", by="monitors")
cur("TR-039", "Macro thesis and board defects reported build after build", "macro", "macro chat / ACK", "PROPOSED",
    "Unmatched macro inbox candidates 18 Oct to 13 Nov (count in notes); no closure record for any. No thesis 27 Oct to 10 Nov; board not built 5, 6, 9, 10 Nov.", "LOW", src=["MACRO-THESIS-DEFECTS"],
    notes="Macro is display-only (CLAUDE.md rule 6), so impact on the book is indirect.", date="2026-10-19", by="macro checks")
cur("TR-040", "52-week high/low flag and resistance test on every row", "both", "Codex / Claude Code", "PROPOSED",
    "Reported missing in 8 ticker files 19 and 22 Oct; XLE 0.05 below its 252-session high with no flag (recomputed).", "MEDIUM", src=["E13"], kw=r"52.?week", date="2026-10-18", by="skill / deep dives")
cur("TR-041", "Daily option close for every carded contract (one writer)", "B", "monitor task / Claude Code", "MERGED",
    "75eb443 (local capture retired). Monitor writes data\\scratch\\workaround\\monitor\\option_closes.csv. X17-01 (monitor prompt needs the UAT rules) Proposed, needs ACK. 5 later reports that 16:20 ET closing quotes widen.",
    "HIGH", reg_ids=["W16-10", "C16-01", "X17-01"], commits="75eb443", run="NOT FOUND as a pipeline run (Lane B artefact)", date="2026-10-16", by="week review")
ETF = {"E1": ("Carry and repair instrument_type; retire ETF hand lists", "A", "PROPOSED", "MEDIUM"),
       "E3": ("Stale-event flag and re-arm for long-running ETF theses", "A", "PROPOSED", "MEDIUM"),
       "E5": ("May the macro board set ETF direction? (QQQ exception)", "macro", "DECISION_PENDING", "HIGH"),
       "E6": ("Holdings-weighted event list for ETFs", "both", "PROPOSED", "MEDIUM"),
       "E11": ("Liquidity tier on an in-session quote; post-close quotes labelled", "both", "PROPOSED", "HIGH"),
       "E12": ("ETFs prioritised: labelled lane or asset type in the rank", "both", "DECISION_PENDING", "HIGH"),
       "E14": ("OCC symbol padding in quote lookups", "B", "PROPOSED", "LOW"),
       "E16": ("Leveraged, inverse and volatility products treated as stocks", "A", "DECISION_PENDING", "MEDIUM"),
       "E17": ("Board ETF list (115) and pipeline ETF list (85) not reconciled; 39 with no chain", "data", "PROPOSED", "MEDIUM"),
       "E18": ("No holdings file for industry ETFs", "data", "PROPOSED", "LOW"),
       "E19": ("Metrics call fails a whole batch on one non-standard chain", "B", "PROPOSED", "LOW"),
       "E20": ("Volatility-product inputs (VIX term, VX strip, settlement dates)", "A", "PROPOSED", "LOW"),
       "E21": ("Macro and political dated events in ETF holds", "both", "PROPOSED", "LOW"),
       "E22": ("Barrier odds overstate target-first for an ETF", "A", "PROPOSED", "MEDIUM"),
       "E23": ("ETF with a single-name sleeve of 10% or more", "A", "PROPOSED", "LOW")}
EREG = {"E20": ["R14-09", "A16-06", "W16-09"], "E21": ["N17-09"], "E22": ["R14-06"]}
for k, (t, lane, st, imp) in ETF.items():
    cur("TR-" + k.replace("E", "E").rjust(3, "0") if False else "TR-" + k, t, lane, "Codex (owner, AVS-ETF-001)" if st != "DECISION_PENDING" else "ACK (decision)", st,
        "audit\\trace\\AVS-TRACE-001\\06_ETF_fix_package_for_Codex.md and evidence\\etf_evidence_check.md, item " + k, imp, src=[k, "AVS-ETF-001"],
        reg_ids=EREG.get(k, ()), date="2026-11-13", by="ACK / Claude chat", notes="E5: ACK's QQQ exception of 12 Nov is NOT FOUND in the repo." if k == "E5" else "")

# ---------------------------------------------------------------- register rows
GROUPS = [["F-001", "T2", "N3", "F-001/T2/N3"], ["N5", "T4", "F14-06"], ["E-001", "W16-01"], ["W16-11", "X17-03", "A16-07"]]
rows = {}
src_rows = []          # (trace_id, source_type, id, scheme, where)
reg2trace = {}
for tid, c in C.items():
    for rid in c["_reg"]:
        reg2trace[rid] = tid
later = collections.Counter(r["register_match"] for r in inbox if r.get("register_match"))
later_files = collections.defaultdict(list)
for r in inbox:
    if r.get("register_match"):
        later_files[r["register_match"]].append(r["file"])


def reg_status(r):
    s, ce = r["status"], r["closure_evidence"]
    where = f"{REGP}:{r['_line']}"
    if s == "Proposed":
        return "PROPOSED", f"Register status Proposed ({where})"
    if s == "Approved":
        return "APPROVED", f"Register: {ce} ({where})"
    if s == "Decision":
        return ("APPROVED" if "disabled" in ce else "DECISION_PENDING"), f"Register: {ce} ({where})"
    hashes = [h for h in re.findall(r"\b[0-9a-f]{7}\b", ce) if re.search(r"\d", h) and re.search(r"[a-f]", h)]
    if s == "Closed":
        return "CLOSED_OFFLINE", f"Register 'Closed' on a monitor note, no run ID: {ce} ({where})"
    if hashes and re.search(r"test", ce):
        return "CLOSED_OFFLINE", f"Commit(s) {', '.join(hashes)} on the checked-out line with tests; no run artefact cited: {ce} ({where})"
    if hashes:
        return "MERGED", f"Commit(s) {', '.join(hashes)} on the checked-out line, not in master; no run artefact cited: {ce} ({where})"
    text = ce + " " + r["proposed_fix"]
    if re.search(r"\.py|\.ps1", text):
        return "MERGED", f"Register 'Built'; script named, Lane B code tracked since 245e87c; no test or run artefact cited: {ce or r['proposed_fix']} ({where})"
    return "NOT_FOUND", f"Register 'Built' ({ce or 'no closure evidence'}); the change is a prompt, task or skill not stored in the repo. Looked in: git log, data\\scratch\\workaround, lessons\\ ({where})"


def impact_of(tags):
    t = set(tags or [])
    return "HIGH" if t & HIGH else "MEDIUM" if t & MED else "LOW" if t - {"other"} else "NONE"


REGTAG = [(r"contract|strike|expiry|dte", "contract_choice"), (r"spread|oi ?<|liquid", "liquidity"), (r"quote|stale", "quote_freshness"),
          (r"exit|stop|gtc|target", "exit_rules"), (r"outcome|score|capture|p&l", "outcome_measurement"), (r"rank", "ranking"),
          (r"hold|window|session", "hold_window"), (r"earnings|event", "earnings_events"), (r"iv|pricing|american|greeks|dividend", "pricing_model"),
          (r"etf", "etf"), (r"macro|board|thesis", "macro"), (r"store|data|backfill", "data_quality")]


def reg_tags(r):
    t = (r["proposed_fix"] + " " + r["evidence"]).lower()
    return [tag for pat, tag in REGTAG if re.search(pat, t)] or ["process"]


n_r = 0
for r in reg:
    rid = r["fix_id"]
    where = f"{REGP}:{r['_line']}"
    if rid in reg2trace:
        tid = reg2trace[rid]
        C[tid]["_src"].add(rid)
        C[tid]["_docs"].append(where)
        src_rows.append((tid, "register", rid, "fix_register", where))
        continue
    grp = next((g for g in GROUPS if rid in g), None)
    if grp and grp[0] in reg2trace and rid != grp[0]:
        tid = reg2trace[grp[0]]
        rows[tid]["_src"].add(rid)
        rows[tid]["_docs"].append(where)
        if r["status"] == "Built" and rows[tid]["status"] == "PROPOSED":
            rows[tid]["status"], rows[tid]["status_evidence"] = reg_status(r)
        rows[tid]["notes"] += f" Duplicate register row {rid} merged here."
        reg2trace[rid] = tid
        src_rows.append((tid, "register", rid, "fix_register", where))
        continue
    n_r += 1
    tid = f"TR-R{n_r:03d}"
    st, ev = reg_status(r)
    note = ""
    if later[rid] and r["status"] in ("Built", "Closed"):
        fs = sorted(set(later_files[rid]))
        note = f"CLAIM_NOT_SUPPORTED: register says {r['status']}, but {later[rid]} later inbox report(s) of the same problem ({fs[0]} to {fs[-1]})."
    elif later[rid]:
        note = f"{later[rid]} later inbox report(s) of the same problem."
    rows[tid] = dict(trace_id=tid, title=r["proposed_fix"][:140], lane={"both": "both", "Both": "both"}.get(r["lane"], r["lane"]), owner=r["owner"] or "not named",
                     status=st, status_evidence=ev, monetisation_impact=impact_of(reg_tags(r)), branch="", commits="", files_changed="", tests="", run_evidence="",
                     notes=note, superseded_by="", conflicts_with="", raised_date=r["raised_date"], raised_by=r["source"][:60], _src={rid}, _docs=[where])
    reg2trace[rid] = tid
    if grp and rid == grp[0]:
        pass
    src_rows.append((tid, "register", rid, "fix_register", where))
for tid, c in C.items():
    rows[tid] = c
    extra = sum(later[x] for x in c["_reg"])
    if extra:
        c["notes"] = (c["notes"] + f" {extra} inbox report(s) since 18 Oct matched to its register rows.").strip()

# ---------------------------------------------------------------- inbox candidates
FIXLIST_FILES = {"2026-11-12_lab_first_fix_list.md", "2026-11-12_fix_A12_monetisation_clock.md", "2026-11-12_claude_code_brief_fix_B.md"}
FL = {"A1": "TR-002", "A8": "TR-011", "A12": "TR-009", "D1": "TR-001", "D2": "TR-014", "C6": "TR-038", "A": "TR-017", "C": "TR-017"}
clusters = {}
n_in = 0
for r in inbox:
    where = INB + f"{r['file']}:{r.get('line', '')}"
    text = " ".join(str(r.get(k, "")) for k in ("title", "problem", "proposed_fix"))
    tid = None
    ids = r.get("ids") or []
    if r["file"] in FIXLIST_FILES and ids:
        i = ids[0]
        if re.fullmatch(r"B\d+", i):
            tid = "TR-012"
        elif i in FL:
            tid = FL[i]
        elif re.fullmatch(r"[AC]\d+", i):
            tid = f"TR-FL-{i}"
            if tid not in rows:
                rows[tid] = dict(trace_id=tid, title=r["title"], lane=r["lane"], owner=r.get("owner_named") or "Codex", status="PROPOSED",
                                 status_evidence=f"Fix list item, proposed ({where})", monetisation_impact=impact_of(r.get("topic_tags")), branch="", commits="",
                                 files_changed="", tests="", run_evidence="", notes="May be covered by da9a922 (A/C reliability, TR-017); the commit does not list the items it closes.",
                                 superseded_by="", conflicts_with="", raised_date="2026-11-12", raised_by="Claude chat / ACK", _src={"FIXLIST-" + i}, _docs=[])
    if not tid and r.get("register_match"):
        tid = reg2trace.get(r["register_match"])
    if not tid:
        for ctid, c in C.items():
            if c["_kw"] and c["_kw"].search(text):
                tid = ctid
                break
    if not tid and r["lane"] == "macro":
        tid = "TR-039"
    if not tid and (r.get("topic_tags") or ["other"])[0] == "outcome_measurement":
        tid = "TR-010"
    if not tid:
        tag = (r.get("topic_tags") or ["other"])[0]
        key = (r["lane"], tag)
        if key not in clusters:
            clusters[key] = f"TR-I-{r['lane']}-{tag}"
            rows[clusters[key]] = dict(trace_id=clusters[key], title=f"Inbox candidates never triaged: lane {r['lane']}, topic {tag.replace('_', ' ')}", lane=r["lane"],
                                       owner="not assigned (never registered)", status="PROPOSED", status_evidence="Inbox only; no register row, no owner, no build found",
                                       monetisation_impact=impact_of([tag]), branch="", commits="", files_changed="", tests="", run_evidence="",
                                       notes="Grouped by lane and topic for this review; each candidate is listed in evidence\\trace_sources.csv and needs its own triage.",
                                       superseded_by="", conflicts_with="", raised_date="2026-10-18 to 2026-11-13", raised_by="monitors, triage, deep dives", _src=set(), _docs=[])
        tid = clusters[key]
    rows[tid]["_docs"].append(where)
    rows[tid].setdefault("_n_inbox", 0)
    rows[tid]["_n_inbox"] += 1
    n_in += 1
    src_rows.append((tid, "inbox", ";".join(ids) or f"candidate {r.get('candidate_no')}", r.get("kind", ""), where))

# ---------------------------------------------------------------- document IDs
GLOBAL = re.compile(r"^(REQ-|NFR-|BR-|OPS-|TST-|ALG-|UAT-D|DISC-F|DEV-|PN-|RCA-|RCA3-|WP\d|CDS-|DOI-\d|MSI-|AVS-|POST-CDS)")
FOLD = re.compile(r"track|^UAT$|^TD$|DISC rule|premise|deviation|verdict|INVARIANT|PRINCIPLE|ENVIRONMENT|ACCEPTANCE|_TEST|_TC$|_RULE$|traceability|disposition|wave|"
                  r"build stage|slice|claim row|receipt|hypothesis|study|closure gate|integration gate|ARCHIVE|INT_BASELINE|_STEP|_PHASE|_GATE|_EVIDENCE|_RECORD|"
                  r"_ORDER|OUT_OF_SCOPE|MODEL_AUDIT|^AVS-TRADE$|LAB_FIRST_FIX_LIST|^F14$|^R14$|^X17$|^N17$|FIX_REGISTER|LESSONS_REGISTER_12OCT$|historical finding|"
                  r"condition|adjustment|closer|terminal-thesis|recoverable|work item|baseline defect|SD-MON-003 check|LESSON_WEEK_GAP|ACK_PATTERN|_FINDING|_RISK|INVENTORY", re.I)
APPROVED_SCHEMES = re.compile(r"^(REQ|NFR|BR|OPS|TST|ALG|WP|APPROVED-0925|CLAUDE_|CONFIG_APPROVAL|FIX-002 policy)")
TRADE = {"AVS-TRADE_WORK": {"W1": "TR-009", "W2": "TR-002", "W3": "TR-001", "W4": "TR-014"},
         "AVS-TRADE_DECISION": {"1": "TR-002", "2": "TR-001", "3": "TR-014", "5": "TR-003", "6": "TR-006", "7": "TR-007"}}
doc2trace = {}
for tid, c in C.items():
    for d in c["_doc"]:
        doc2trace[d] = tid


def key_of(d):
    i = d["id"].strip()
    return i if GLOBAL.match(i) else f"{d['scheme']}:{i}"


def doc_status(d):
    c = (d.get("status_claimed") or "").lower()
    cite = d.get("evidence_cited") or "none cited"
    base = f"DOCUMENT_CLAIM (not re-verified): '{(d.get('status_claimed') or 'no status word')[:90]}' at {d['source']}; evidence cited: {str(cite)[:120]}"
    if re.search(r"reject|retired|ruled out|do not build", c):
        return "REJECTED", base
    if "supersed" in c:
        return "SUPERSEDED", base
    if re.search(r"decision for ack|ack to |waiting|pending|still open", c):
        return "DECISION_PENDING", base
    if re.search(r"not implemented|not tested|^open|active|severity p|filed|blocking|required|residual|research|premise", c):
        return ("APPROVED" if APPROVED_SCHEMES.match(d["scheme"]) else "PROPOSED"), base
    if re.search(r"closed offline|offline|implemented|built|complete|delivered|pass|verified|live", c):
        return "CLOSED_OFFLINE", base
    if re.search(r"approved|accepted|confirmed|mandatory|decided|answered", c):
        return "APPROVED", base
    return ("APPROVED" if APPROVED_SCHEMES.match(d["scheme"]) else "PROPOSED"), base


RANK = {"REJECTED": 0, "SUPERSEDED": 0, "PROPOSED": 1, "DECISION_PENDING": 2, "APPROVED": 3, "CLOSED_OFFLINE": 4}
n_doc = n_d = 0
groups = {}
td_open = re.compile(r"not implemented|not tested|^open", re.I)
for d in docs:
    n_doc += 1
    k = key_of(d)
    where = d["source"].replace("/", "\\")
    i = d["id"].strip()
    tid = doc2trace.get(k) or doc2trace.get(i if GLOBAL.match(i) else "")
    if not tid and d["scheme"] in TRADE:
        tid = TRADE[d["scheme"]].get(i) or TRADE[d["scheme"]].get(re.sub(r"\D", "", i))
    if not tid and d["scheme"] == "LAB_FIRST_FIX_LIST":
        m = re.match(r"^([ABCD]\d+)", i)
        if m:
            tid = "TR-012" if m.group(1).startswith("B") else FL.get(m.group(1)) or (f"TR-FL-{m.group(1)}" if f"TR-FL-{m.group(1)}" in rows else None)
    if not tid and i in reg2trace and re.search(r"ARCHIVE|^F14$|^R14$|^X17$|^N17$|FIX_REGISTER", d["scheme"]):
        tid = reg2trace[i]
    if not tid and k in rows.get("_dockeys", {}):
        tid = rows["_dockeys"][k]
    if not tid and FOLD.search(d["scheme"]) and not (GLOBAL.match(i) and re.match(r"^(REQ-|NFR-|ALG-|UAT-D)", i)):
        doc = where.rsplit(":", 1)[0]
        gk = (doc, d["scheme"])
        if gk not in groups:
            n_d += 1
            groups[gk] = f"TR-G{n_d:03d}"
            rows[groups[gk]] = dict(trace_id=groups[gk], title=f"{d['scheme']} entries in {doc.rsplit(chr(92), 1)[-1]}", lane=d.get("lane") or "A", owner=d.get("owner_named") or "not named",
                                    status="NOT_FOUND", status_evidence=f"Supporting records (test steps, track results, rules, receipts), not individual fixes; no per-item closure evidence looked for. Source {doc}",
                                    monetisation_impact="NONE", branch="", commits="", files_changed="", tests="", run_evidence="", notes="Grouped by document; each entry is listed in evidence\\trace_sources.csv.",
                                    superseded_by="", conflicts_with="", raised_date=d.get("doc_date", ""), raised_by=d.get("raised_by", ""), _src=set(), _docs=[doc])
        tid = groups[gk]
        rows[tid]["_src"].add(i)
        src_rows.append((tid, "document", i, d["scheme"], where))
        continue
    if not tid:
        rows.setdefault("_dockeys", {})
        n_d += 1
        tid = f"TR-D{n_d:04d}"
        st, ev = doc_status(d)
        rows[tid] = dict(trace_id=tid, title=(d.get("title") or d.get("one_line") or i)[:140], lane=d.get("lane") or "A", owner=d.get("owner_named") or "not named", status=st,
                         status_evidence=ev, monetisation_impact=impact_of(d.get("topic_tags")), branch="", commits="", files_changed="; ".join(map(str, d.get("files_named") or []))[:200],
                         tests="", run_evidence=";".join(sorted(set(re.findall(r"\b20\d{6}_\d{6}\b", str(d.get("evidence_cited")))))), notes="", superseded_by="", conflicts_with="",
                         raised_date=d.get("doc_date", ""), raised_by=d.get("raised_by", ""), _src={i}, _docs=[where], _claims=[st])
        rows["_dockeys"][k] = tid
        src_rows.append((tid, "document", i, d["scheme"], where))
        continue
    row = rows[tid]
    row["_src"].add(i)
    row["_docs"].append(where)
    src_rows.append((tid, "document", i, d["scheme"], where))
    if tid.startswith("TR-D"):
        st, ev = doc_status(d)
        claim = d.get("status_claimed") or ""
        row["_claims"].append(st)
        if re.search(r"UAT (track result|verdict)", d["scheme"]) and td_open.search(claim):
            if "CLOSED_OFFLINE" in row["_claims"]:
                row["notes"] += f" CLAIM_NOT_SUPPORTED: independent test (AVS-TD-001) says '{claim[:60]}' at {where}."
            row["status"] = "APPROVED"
            row["status_evidence"] = f"AVS-TD-001 independent test: '{claim[:80]}' at {where} (not re-verified)"
        elif len(set(row["_claims"])) > 1 and "differ" not in row["notes"]:
            row["notes"] += " Status differs between documents; see evidence\\trace_sources.csv."
rows.pop("_dockeys", None)

# ---------------------------------------------------------------- write
out = []
for tid, r in rows.items():
    if tid == "TR-039":
        r["notes"] = f"{r.get('_n_inbox', 0)} inbox candidates. " + r["notes"]
    elif r.get("_n_inbox") and tid.startswith("TR-I-"):
        r["title"] += f" ({r['_n_inbox']} candidates)"
    docs_ = list(dict.fromkeys(r["_docs"]))
    r["source_documents"] = "; ".join(docs_[:5]) + (f"; +{len(docs_) - 5} more in evidence\\trace_sources.csv" if len(docs_) > 5 else "")
    r["source_ids"] = "; ".join(sorted(r["_src"]))[:600]
    out.append({c: str(r.get(c, "")).strip() for c in COLS})


def order(t):
    p = t["trace_id"]
    return (0 if re.match(r"TR-\d", p) else 1 if p.startswith("TR-E") else 2 if p.startswith("TR-FL") else 3 if p.startswith("TR-R") else 4 if p.startswith("TR-I") else 5 if p.startswith("TR-D") else 6, p)


out.sort(key=order)
with open(OUT / "01_traceability_matrix.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=COLS)
    w.writeheader()
    w.writerows(out)
with open(EV / "trace_sources.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["trace_id", "source_type", "source_id", "scheme_or_kind", "where"])
    w.writerows(src_rows)

by = collections.Counter(s[1] for s in src_rows)
stat = collections.Counter(r["status"] for r in out)
summary = dict(trace_rows=len(out), register_rows=len(reg), register_mapped=by["register"], inbox_candidates=len(inbox), inbox_mapped=by["inbox"],
               inbox_files=len({r["file"] for r in inbox}), doc_records=len(docs), doc_mapped=by["document"], status=dict(stat),
               status_by_family={fam: dict(collections.Counter(r["status"] for r in out if order(r)[0] == n)) for n, fam in enumerate(["curated", "etf", "fixlist", "register", "inbox_cluster", "document", "document_group"])},
               impact=dict(collections.Counter(r["monetisation_impact"] for r in out)),
               open_high=sum(1 for r in out if r["monetisation_impact"] == "HIGH" and r["status"] in ("PROPOSED", "APPROVED", "DECISION_PENDING", "BUILT_UNMERGED", "NOT_FOUND")),
               claim_not_supported=sum(1 for r in out if "CLAIM_NOT_SUPPORTED" in r["notes"]),
               non_proposed_without_evidence=sum(1 for r in out if r["status"] != "PROPOSED" and not r["status_evidence"]),
               closed=sum(1 for r in out if r["status"] == "CLOSED"),
               inbox_unregistered=sum(1 for r in inbox if not r.get("register_match")),
               doc_rows_citing_a_run=sum(1 for r in out if r["trace_id"].startswith("TR-D") and r["run_evidence"]))
json.dump(summary, open(EV / "matrix_summary.json", "w", encoding="utf-8"), indent=1)
sys.stdout.reconfigure(encoding="utf-8")
print(json.dumps(summary, indent=1))
