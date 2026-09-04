"""AVS-TST-SD-001 Part A — static fix-verification against AVS-SD-001 v0.2.

For every workstream, check mechanically whether the change the design specifies
is present in the code on disk. READ-ONLY: reads source with utf-8-sig, opens
SQLite mode=ro, executes no pipeline stage and imports no production module.

Each check emits: test_id, workstream, expected (design citation), actual,
verdict PRESENT / ABSENT / BLOCKED.

Usage:  python t_static_fixverify.py
"""
from __future__ import annotations

import csv
import re
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent.parent
results: list[dict] = []


def src(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8-sig", errors="replace")


def emit(tid, ws, expected, actual, verdict, evidence=""):
    results.append({"test_id": tid, "workstream": ws, "level": "static",
                    "direction_variant": "n/a", "expected": expected,
                    "actual": actual, "verdict": verdict, "evidence": evidence})


def grep(rel: str, pattern: str, flags=0):
    """Return [(lineno, line)] for pattern in file."""
    out = []
    text = src(rel)
    if not text:
        return out
    rx = re.compile(pattern, flags)
    for i, ln in enumerate(text.splitlines(), 1):
        if rx.search(ln):
            out.append((i, ln.strip()[:160]))
    return out


def grep_repo(pattern: str, exts=(".py",), skip=("backups", "Archive",
              "_cleanup_holding", "venv", ".git", "audit")):
    hits = []
    rx = re.compile(pattern)
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT).as_posix()
        if any(rel.startswith(s + "/") or f"/{s}/" in rel for s in skip):
            continue
        try:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            continue
        for i, ln in enumerate(text.splitlines(), 1):
            if rx.search(ln):
                hits.append((rel, i, ln.strip()[:140]))
    return hits


# ---------------------------------------------------------------- WS0
def ws0():
    r = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                       capture_output=True, text=True, timeout=120)
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    untracked_py = [l for l in lines if l.startswith("??") and l.endswith(".py")]
    emit("WS0.git_clean", "WS0",
         "design §2 exit gate: `git status` clean",
         f"{len(lines)} entries; {len(untracked_py)} untracked .py",
         "ABSENT" if lines else "PRESENT", "git status --porcelain")

    h = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                       capture_output=True, text=True, timeout=60).stdout.strip()
    tags = subprocess.run(["git", "tag", "--list", "baseline-20260831"],
                          cwd=ROOT, capture_output=True, text=True,
                          timeout=60).stdout.strip()
    emit("WS0.baseline_tag", "WS0",
         "design §2: tag `baseline-20260831`",
         f"HEAD={h[:12]}; tag present={bool(tags)}",
         "PRESENT" if tags else "ABSENT", "git tag --list")

    # BOM normalisation
    bomlist = OUT.parent / "AVS-E2E-CODE-001" / "_tooling" / "bom_files.txt"
    n = 0
    if bomlist.exists():
        for rel in bomlist.read_text(encoding="utf-8").split():
            p = ROOT / rel
            try:
                if p.exists() and p.open("rb").read(3) == b"\xef\xbb\xbf":
                    n += 1
            except Exception:
                pass
    emit("WS0.bom_normalised", "WS0",
         "design §2: normalise the 42 UTF-8 BOMs", f"{n} still BOM-prefixed",
         "PRESENT" if n == 0 else "ABSENT", "byte scan of bom_files.txt")

    # scenario_builder determinism
    copies = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("scenario_builder.py")
              if not any(s in p.as_posix() for s in
                         ("backups", "Archive", "_cleanup_holding", "venv"))]
    emit("WS0.scenario_builder_determinism", "WS0",
         "design §2: delete shadowed module or rename; binding deterministic",
         f"{len(copies)} copies: {copies}",
         "PRESENT" if len(copies) <= 1 else "ABSENT", "rglob scenario_builder.py")

    # morning baseline run
    runs = ROOT / "data" / "output" / "runs"
    morning = []
    for d in runs.iterdir() if runs.exists() else []:
        if (d / "morning_validation").exists() and any(
                (d / "morning_validation").glob("morning_gate*")):
            morning.append(d.name)
    emit("WS0.morning_baseline", "WS0",
         "design §2: capture one governed morning evidence run",
         f"morning-gate outputs found in {len(morning)} runs",
         "PRESENT" if morning else "ABSENT",
         "scan runs/*/morning_validation for morning_gate artefacts")


# ---------------------------------------------------------------- WS1
def ws1():
    f = "scripts/avshunter_options_intelligence.py"
    # change 1: lifecycle consumes published governed invalidation
    raw = grep(f, r'"invalidation_spot"\s*:\s*.*ctx\.get\(\s*"stop"')
    emit("WS1.c1_invalidation_source", "WS1",
         'design §3.1: :4549 consumes the published governed invalidation, '
         'not raw ctx["stop"]',
         f'raw ctx["stop"] still feeds invalidation_spot at {[l for l,_ in raw]}'
         if raw else "raw ctx[stop] pattern not found",
         "ABSENT" if raw else "PRESENT",
         f"{f}:{raw[0][0] if raw else '-'}")

    # change 2: routed planned hold
    hold = grep(f, r'"remaining_hold_sessions"\s*:\s*.*ctx\.get\(\s*"hold_days"')
    planned = grep(f, r"planned_hold_sessions")
    emit("WS1.c2_routed_hold", "WS1",
         'design §3.2: :4546 consumes routed planned_hold_sessions, '
         'not ctx["hold_days"]',
         f'ctx["hold_days"] still feeds remaining_hold_sessions at '
         f'{[l for l,_ in hold]}; planned_hold_sessions refs={len(planned)}'
         if hold else f"planned_hold_sessions refs={len(planned)}",
         "ABSENT" if hold else "PRESENT",
         f"{f}:{hold[0][0] if hold else '-'}")

    # change 6: fabricated stop entry x 0.97
    fab = grep_repo(r"0\.97")
    fab = [h for h in fab if "stop" in h[2].lower() or "entry" in h[2].lower()]
    emit("WS1.c6_no_fabricated_stop", "WS1",
         "design §3.6: kill the fabricated stop entry × 0.97",
         f"{len(fab)} candidate sites: " +
         "; ".join(f"{r}:{i}" for r, i, _ in fab[:4]),
         "ABSENT" if fab else "PRESENT", "repo grep 0.97 near stop/entry")

    # change 3+4: contract invariants
    c = "contracts/options_liquidity_lifecycle.py"
    inval_inv = grep(c, r"invalidation.*rais|rais.*invalidation", re.I)
    dom = grep(c, r"\{\s*5\s*,\s*10\s*,\s*20\s*\}|in\s*\(5,\s*10,\s*20\)|"
                  r"ALLOWED_HOLD|ROUTED_HOLD")
    emit("WS1.c3_invalidation_invariant", "WS1",
         "design §3.3: classify_remaining_runway raises on wrong-sided stop",
         f"{len(inval_inv)} invalidation-raise lines",
         "PRESENT" if inval_inv else "ABSENT",
         f"{c}:{inval_inv[0][0] if inval_inv else '-'}")
    emit("WS1.c4_dte_domain_assert", "WS1",
         "design §3.4: calculate_dte_requirement domain-asserts hold ∈ {5,10,20}",
         f"{len(dom)} domain-assert candidates",
         "PRESENT" if dom else "ABSENT",
         f"{c}:{dom[0][0] if dom else '-'}")

    # change 5: third arm named state
    third = grep(f, r"NOT_EVALUATED_NON_DIRECTIONAL|invalidation_state")
    emit("WS1.c5_third_arm_state", "WS1",
         "design §3.5: direction ∉ {CALL,PUT} → invalidation_state=NOT_APPLICABLE; "
         "lifecycle emits NOT_EVALUATED_NON_DIRECTIONAL",
         f"{len(third)} references",
         "PRESENT" if third else "ABSENT", f"{f}")


# ---------------------------------------------------------------- WS2
def ws2():
    o = "intelligent_orchestrator.py"
    eil = grep(o, r"run_execution_intelligence_layer\(")
    tp2 = grep(o, r"_tl_enrich_csv\(")
    eil_l = eil[0][0] if eil else None
    tp2_l = tp2[0][0] if tp2 else None
    if eil_l and tp2_l:
        ordered = tp2_l < eil_l
        emit("WS2.d1a_trigger_before_execution", "WS2",
             "design §4 D1-A: trigger pass 2 moved BEFORE the Execution write",
             f"EIL write at :{eil_l}; trigger pass 2 at :{tp2_l} "
             f"({'reordered' if ordered else 'still AFTER'})",
             "PRESENT" if ordered else "ABSENT", f"{o}")
    else:
        emit("WS2.d1a_trigger_before_execution", "WS2",
             "design §4 D1-A ordering", "call sites not located", "BLOCKED", o)

    sch = grep("execution_schema.py", r"trigger_(codes|quality|primary|score|"
                                      r"count|go_eligible)")
    emit("WS2.d1a_schema_trigger_block", "WS2",
         "design §4 D1-A: trigger block added to execution_schema.py (GAP-311)",
         f"{len(sch)} trigger field references",
         "PRESENT" if sch else "ABSENT", "execution_schema.py")

    join = grep("eod_candidate_engine.py", r"eil_enriched")
    emit("WS2.d1b_allowlisted_join", "WS2",
         "design §4 D1-B (fallback): allow-listed join from eil_enriched in the "
         "EOD engine",
         f"{len(join)} eil_enriched references",
         "PRESENT" if join else "ABSENT", "eod_candidate_engine.py")

    lab = grep("intelligence-lab/intelligence_lab.py",
               r"trigger_quality.*trigger_score|trigger_score.*trigger_quality")
    emit("WS2.lab_fallback_deleted", "WS2",
         "design §4: delete the Lab fallback trigger_quality ← trigger_score",
         f"{len(lab)} fallback lines: " +
         "; ".join(f":{l}" for l, _ in lab[:3]),
         "ABSENT" if lab else "PRESENT", "intelligence-lab/intelligence_lab.py")


# ---------------------------------------------------------------- WS3
def ws3():
    o = "intelligent_orchestrator.py"
    wg = grep(o, r"filter_rows_to_worklist|reconcile_stage_outcomes")
    hr = grep(o, r"run_horizon_router\(")
    emit("WS3.worklist_gate_at_horizon", "WS3",
         "design §5.1: worklist_gate wired at the Options→Horizon boundary",
         f"worklist-gate calls at {[l for l,_ in wg]}; "
         f"run_horizon_router at {[l for l,_ in hr]}",
         "ABSENT", "manual read required to confirm adjacency")

    cm = grep(o, r"runs BEFORE Vanguard")
    emit("WS3.orchestrator_comments_fixed", "WS3",
         "design §5.3: fix contradictory position comments (:4136-4139 vs :4151)",
         f"stale 'runs BEFORE Vanguard' comment present at "
         f"{[l for l,_ in cm]}" if cm else "stale comment not found",
         "ABSENT" if cm else "PRESENT", f"{o}")

    sc = grep_repo(r"_DTE_SCAFFOLD")
    emit("WS3.dte_scaffold_retired", "WS3",
         "design §5.6: retire Discovery's _DTE_SCAFFOLD (or zero readers)",
         f"{len(sc)} references: " + "; ".join(f"{r}:{i}" for r, i, _ in sc[:4]),
         "ABSENT" if sc else "PRESENT", "repo grep _DTE_SCAFFOLD")

    ph = grep_repo(r"preliminary_horizon_hint")
    emit("WS3.single_horizon_writer", "WS3",
         "design §5.5: Discovery's horizon output renamed preliminary_horizon_hint",
         f"{len(ph)} references",
         "PRESENT" if ph else "ABSENT", "repo grep preliminary_horizon_hint")


# ---------------------------------------------------------------- WS4
def ws4():
    sites = [
        ("trigger_confirmation_engine.py", r"direction\s*=\s*TradeBias\.PUT|"
                                           r"direction not in \(.*\).*PUT"),
        ("scripts/exit_rules_engine.py", r'if\s+direction\s*==\s*"CALL"'),
        ("zero_dte/zero_dte_contract.py", r'options_direction["\']?\s*,\s*["\']CALL'),
        ("short_swing/short_swing_contract.py",
         r'options_direction["\']?\s*,\s*["\']CALL'),
        ("short_swing/short_swing_monitor.py", r'direction["\']?\s*,\s*["\']CALL'),
        ("avshunter_trap_engine.py", r"max\(\s*bull_score\s*,\s*bear_score\s*\)"),
    ]
    for rel, pat in sites:
        h = grep(rel, pat)
        emit(f"WS4.coercion_removed::{rel}", "WS4",
             "design §6.2: peripheral direction coercion removed (three-arm rewrite)",
             f"{len(h)} coercion lines: " + "; ".join(f":{l}" for l, _ in h[:2]),
             "ABSENT" if h else "PRESENT", rel)

    rule3 = grep("avshunter_discovery_ULTIMATE.py", r"_reconcile_intent")
    emit("WS4.reconcile_intent_flags", "WS4",
         "design §6.3: _reconcile_intent Rule 3 flags instead of overwriting",
         f"{len(rule3)} references — behaviour requires fixture",
         "BLOCKED", "avshunter_discovery_ULTIMATE.py (fixture needed)")

    mr = grep("tools/msi_reconcile.py", r"domain|VALID_DIRECTION|"
                                        r"STRANGLE|UNRESOLVED")
    emit("WS4.msi_reconcile_validity", "WS4",
         "design §6.4: msi_reconcile upgraded from agreement to domain validity",
         f"{len(mr)} domain-validation candidates",
         "PRESENT" if mr else "ABSENT", "tools/msi_reconcile.py")

    mg = grep("morning_gate.py", r"NOT_EVALUATED_NON_DIRECTIONAL")
    emit("WS4.morning_third_arm", "WS4",
         "design §6.5: morning _check_invalidation third arm → "
         "NOT_EVALUATED_NON_DIRECTIONAL",
         f"{len(mg)} references",
         "PRESENT" if mg else "ABSENT", "morning_gate.py")


# ---------------------------------------------------------------- WS5
def ws5():
    d = "avshunter_discovery_ULTIMATE.py"
    macro = grep(d, r"macro_intelligence_latest|macro_path|MACRO_FILE|"
                    r"regime_align|sector_lift")
    emit("WS5.discovery_macro_removed", "WS5",
         "design §7: Discovery's five macro modulation channels removed",
         f"{len(macro)} macro references still present",
         "ABSENT" if macro else "PRESENT", d)

    mds = grep_repo(r"MACRO_DIRECTION_SIZING")
    emit("WS5.d3_no_size_by_direction", "WS5",
         "design §7 D3-A: no code path multiplies size by direction",
         f"{len(mds)} MACRO_DIRECTION_SIZING references: " +
         "; ".join(f"{r}:{i}" for r, i, _ in mds[:4]),
         "ABSENT" if mds else "PRESENT", "repo grep MACRO_DIRECTION_SIZING")

    hs = grep("intelligent_orchestrator.py", r"as_of_utc")
    emit("WS5.horizon_summary_run_identity", "WS5",
         "design §7: horizon_summary.as_of_utc stamps run identity (GAP-010)",
         f"{len(hs)} as_of_utc writes in orchestrator — requires read",
         "BLOCKED", "manual read of the horizon_summary writer")


# ---------------------------------------------------------------- WS6
def ws6():
    c = "contracts/selected_contract_economics.py"
    qs = grep(c, r"quote_source|completed_session|eod_quote")
    emit("WS6.hydrate_quote_source_param", "WS6",
         "design §8.1: hydrate_selected_structure gains a quote-source parameter",
         f"{len(qs)} quote-source candidates",
         "PRESENT" if qs else "ABSENT", c)

    call = grep_repo(r"evaluate_long_option_monetisability")
    eod = [h for h in call if "options_intelligence" in h[0]
           or "eod_candidate" in h[0]]
    emit("WS6.eod_monetisability_call", "WS6",
         "design §8.2: evaluate_long_option_monetisability runs at EOD",
         f"{len(call)} call sites; {len(eod)} on the EOD path: " +
         "; ".join(f"{r}:{i}" for r, i, _ in call[:5]),
         "PRESENT" if eod else "ABSENT", "repo grep")

    ts = grep_repo(r"selected_quote_timestamp_utc")
    writers = [h for h in ts if "lab_control" in h[0] or "eod_candidate" in h[0]]
    emit("WS6.book_quote_timestamp", "WS6",
         "design §8.1: book carries selected_quote_timestamp_utc",
         f"{len(ts)} references; {len(writers)} in book writers",
         "PRESENT" if writers else "ABSENT", "repo grep")


# ---------------------------------------------------------------- WS7
def ws7():
    db = ROOT / "data" / "canonical" / "control_plane.sqlite"
    cols_found = {}
    if db.exists():
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            for t in ("option_thesis_events", "option_contract_observations",
                      "option_contract_selection_events"):
                try:
                    cs = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
                    cols_found[t] = cs
                except Exception:
                    cols_found[t] = []
            con.close()
        except Exception as e:
            cols_found = {"error": str(e)}
    need = {"calculation_version", "supersedes_event_id", "correction_reason",
            "corrected_by_run_id"}
    have = set()
    for cs in cols_found.values():
        if isinstance(cs, list):
            have |= (set(cs) & need)
    emit("WS7.supersession_columns", "WS7",
         "design §9.2: append-only correction protocol columns exist",
         f"present: {sorted(have) or 'NONE'} of {sorted(need)}",
         "PRESENT" if have == need else "ABSENT", "PRAGMA table_info (mode=ro)")

    tid = grep("scripts/avshunter_options_intelligence.py",
               r"thesis_id\s*=|f\"\{ticker\}:\{")
    emit("WS7.thesis_id_completed_session", "WS7",
         "design §9.1: thesis identity keys on COMPLETED_SESSION not run date",
         f"{len(tid)} thesis_id construction candidates — requires read",
         "BLOCKED", "manual read of key construction")

    wfm = grep_repo(r"write_final_run_manifest\(")
    emit("WS7.manifest_single_producer", "WS7",
         "design §9.4: four write_final_run_manifest call sites reduced to one",
         f"{len(wfm)} call sites: " + "; ".join(f"{r}:{i}" for r, i, _ in wfm[:6]),
         "PRESENT" if len(wfm) <= 2 else "ABSENT", "repo grep")

    dt = grep_repo(r"date\.today\(\)")
    emit("WS7.no_local_clock", "WS7",
         "design §9.4: local-clock stamps replaced with session-clock sources",
         f"{len(dt)} date.today() sites: " +
         "; ".join(f"{r}:{i}" for r, i, _ in dt[:5]),
         "ABSENT" if not dt else "ABSENT" if dt else "PRESENT", "repo grep")

    sc = grep_repo(r"from canonical_data\.session_clock|import session_clock")
    emit("WS7.session_clock_adoption", "WS7",
         "design §9.5: session clock is the sole time authority "
         "(baseline: only morning_gate.py imported it)",
         f"{len(sc)} importers: " + "; ".join(h[0] for h in sc[:6]),
         "PRESENT" if len(sc) > 3 else "ABSENT", "repo grep")


# ---------------------------------------------------------------- WS8/9
def ws89():
    dcv = "scripts/data_contract_validator.py"
    fin = grep(dcv, r"isfinite|math\.isnan|>\s*0\b")
    emit("WS8.validator_finiteness", "WS8",
         "design §10: validator checks finiteness and positivity, not just is None",
         f"{len(fin)} finiteness/positivity candidates",
         "PRESENT" if fin else "ABSENT", dcv)

    stale = grep(dcv, r"DATA_DEFECT")
    emit("WS8.unparseable_date_data_defect", "WS8",
         "design §10: unparseable date → DATA_DEFECT, fail-closed",
         f"{len(stale)} DATA_DEFECT references",
         "PRESENT" if stale else "ABSENT", dcv)

    enum = grep_repo(r"PENDING_MORNING_REFRESH")
    mods = sorted({h[0] for h in enum})
    emit("WS8.eight_states_one_enum", "WS8",
         "design §10: the eight governed states become an enum from one module",
         f"PENDING_MORNING_REFRESH appears in {len(mods)} modules: {mods[:5]}",
         "PRESENT" if len(mods) == 1 else "ABSENT", "repo grep")

    eg = grep("execution_gate.py", r"action_is_within_guard")
    emit("WS9.guard_at_emission", "WS9",
         "design §11.2: execution_gate.py calls action_is_within_guard at emission",
         f"{len(eg)} call sites in execution_gate.py",
         "PRESENT" if eg else "ABSENT", "execution_gate.py")

    forks = [p for p in (ROOT / "zero_dte_screener.py",
                         ROOT / "short_swing_screener.py") if p.exists()]
    emit("WS9.fork_twins_removed", "WS9",
         "design §11.1: root-level fork twins deleted or output paths isolated",
         f"{len(forks)} fork twins still present: "
         f"{[p.name for p in forks]}",
         "ABSENT" if forks else "PRESENT", "filesystem check")


def main() -> None:
    for fn in (ws0, ws1, ws2, ws3, ws4, ws5, ws6, ws7, ws89):
        try:
            fn()
        except Exception as e:
            emit(f"{fn.__name__}.ERROR", fn.__name__.upper(),
                 "check completes", f"{type(e).__name__}: {e}", "BLOCKED")

    w = max(len(r["test_id"]) for r in results) + 1
    print("\n=== AVS-TST-SD-001 Part A :: static fix-verification "
          "vs AVS-SD-001 v0.2 ===\n")
    cur = None
    for r in results:
        if r["workstream"] != cur:
            cur = r["workstream"]
            print(f"\n--- {cur} ---")
        print(f"  {r['verdict']:<8} {r['test_id']:<{w}} {r['actual'][:96]}")
    tally: dict[str, int] = {}
    for r in results:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    print(f"\n  TALLY: {tally}")

    p = OUT / "TST_static_fixverify.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        wr.writeheader()
        wr.writerows(results)
    print(f"  wrote {p.name}")


if __name__ == "__main__":
    main()
