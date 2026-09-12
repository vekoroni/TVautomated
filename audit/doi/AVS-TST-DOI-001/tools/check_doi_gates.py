"""AVS-TST-DOI-001 — read-only DOI gate report for one run.

    venv\\Scripts\\python.exe audit\\doi\\AVS-TST-DOI-001\\tools\\check_doi_gates.py <run_id>
        [--control-plane <path>] [--json <path>]

This is the checklist ACK ticks against the NEXT evening artefact and the next
valid Morning Gate, to convert this audit's VERIFIED OFFLINE items into
VERIFIED. Each gate names the audit finding it closes.

It follows the conventions of `audit/ops/check_run_gates.py`: reads
`data/output/runs/<run_id>/` and a control-plane database and nothing else,
opens no network connection, executes no stage, and writes only the file named
on the command line. Every population line carries its CALL/PUT/OTHER split.

The existing `audit/ops/check_run_gates.py` is NOT modified.

Exit code is 1 if any P0 gate fails, 0 otherwise. A gate whose evidence is not
yet present reports AWAITING and does not fail the run.

DEFAULT SAFETY: the control plane is opened read-only (`mode=ro`). Point
--control-plane at a copy if you prefer.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

RUNS = REPO / "data" / "output" / "runs"
DEFAULT_DB = REPO / "data" / "canonical" / "control_plane.sqlite"

DOI_TABLES = (
    "doi_contract_families", "doi_contract_assessments",
    "doi_preferred_contract_decisions", "doi_family_rankings",
    "doi_lifecycle_events", "doi_outcome_labels",
    "doi_probability_inferences", "doi_probability_models",
    "doi_ranking_policies",
)

#: Gates whose failure means DOI must not stay wired. Everything else is
#: reported and does not change the exit code.
P0_GATES = {
    "DOI-G01-POPULATION",
    "DOI-G02-DIRECTION-IMMUTABLE",
    "DOI-G03-NO-PROVIDER-FETCH",
    "DOI-G04-AUTHORITY-COLUMNS",
    "DOI-G09-NO-PROBABILITY-MISLABEL",
}


@dataclass
class Gate:
    gate: str
    verdict: str          # PASS / FAIL / AWAITING / NOT_DEFINED
    detail: str
    closes: str           # which audit defect or claim this closes
    three_direction: str = ""


@dataclass
class Report:
    run_id: str
    rows: list[Gate] = field(default_factory=list)

    def add(self, *args: Any, **kwargs: Any) -> None:
        self.rows.append(Gate(*args, **kwargs))


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _split(rows: list[dict], *keys: str) -> tuple[int, int, int]:
    call = put = other = 0
    for row in rows:
        value = ""
        for key in keys:
            value = str(row.get(key) or "").strip().upper()
            if value:
                break
        if value == "CALL":
            call += 1
        elif value == "PUT":
            put += 1
        else:
            other += 1
    return call, put, other


def _fmt(split: tuple[int, int, int]) -> str:
    return f"CALL={split[0]} PUT={split[1]} OTHER={split[2]}"


def build(run_id: str, db_path: Path) -> Report:
    report = Report(run_id)
    run_dir = RUNS / run_id
    doi_report = _read_json(run_dir / "options" / f"dynamic_options_intelligence_{run_id}.json")
    book = _read_json(run_dir / "intelligence_lab" / f"final_opportunity_book_{run_id}.json")
    book_rows = book.get("rows", []) if isinstance(book, dict) else []

    # ---- G01 population preserved -----------------------------------------
    if doi_report is None:
        report.add("DOI-G01-POPULATION", "AWAITING",
                   "no DOI run report for this run", "T11.3 / DOI-D24")
    else:
        unique = int(doi_report.get("unique_tickers") or 0)
        retained = int(doi_report.get("retained_opportunities") or 0)
        deleted = int(doi_report.get("deleted_opportunities") or 0)
        ok = unique == retained and deleted == 0 and unique > 0
        report.add("DOI-G01-POPULATION", "PASS" if ok else "FAIL",
                   f"unique={unique} retained={retained} deleted={deleted}",
                   "invariant 4/6, §1.1")

    # ---- G02 direction immutable across the Lab merge ----------------------
    # Closes the one P0 in this audit. Requires the pre-merge book to be kept.
    pre = _read_json(run_dir / "intelligence_lab" / f"final_opportunity_book_pre_doi_{run_id}.json")
    if pre is None:
        report.add("DOI-G02-DIRECTION-IMMUTABLE", "AWAITING",
                   "pre-merge book not retained; write "
                   f"final_opportunity_book_pre_doi_{run_id}.json to enable this gate",
                   "DOI-D27 (P0)")
    else:
        before = {str(r.get("ticker", "")).upper(): r for r in pre.get("rows", [])}
        changed = [
            t for t, r in before.items()
            for a in [next((x for x in book_rows
                            if str(x.get("ticker", "")).upper() == t), None)]
            if a is not None and str(r.get("governed_direction") or "").upper()
            != str(a.get("governed_direction") or "").upper()
        ]
        report.add("DOI-G02-DIRECTION-IMMUTABLE",
                   "PASS" if not changed else "FAIL",
                   f"rows whose governed_direction changed: {len(changed)} {changed[:8]}",
                   "DOI-D27 (P0)")

    # ---- G03 zero provider fetches ----------------------------------------
    if doi_report is None:
        report.add("DOI-G03-NO-PROVIDER-FETCH", "AWAITING", "no DOI run report",
                   "DOI-D23 / invariant 13")
    else:
        fetches = int(doi_report.get("physical_fetch_count") or 0)
        exceptions = list(doi_report.get("exceptions") or [])
        reuse = int(doi_report.get("canonical_reuse") or 0)
        # physical_fetch_count is a literal 0 in the production summary, so a
        # real provider fetch surfaces as a ticker exception instead. Only
        # PROVIDER-shaped exceptions are evidence of a fetch; an ordinary data
        # exception such as MISSING_GOVERNED_THESIS_ID is not, and must not
        # fail this gate. (Fixed after the first real run reported one
        # MISSING_GOVERNED_THESIS_ID and the gate cried wolf.)
        provider_tokens = ("PROVIDER", "FETCH", "MARKETDATA", "POLYGON",
                           "TASTYTRADE", "FRED", "HTTP", "TIMEOUT", "CONNECTION")
        provider_exceptions = [
            e for e in exceptions
            if any(tok in f"{e.get('error_type','')}{e.get('reason','')}".upper()
                   for tok in provider_tokens)
        ]
        other_exceptions = len(exceptions) - len(provider_exceptions)
        ok = fetches == 0 and not provider_exceptions
        detail = (f"physical_fetch_count={fetches} canonical_reuse={reuse} "
                  f"provider_exceptions={len(provider_exceptions)} "
                  f"other_ticker_exceptions={other_exceptions}")
        if provider_exceptions:
            detail += f" -> {provider_exceptions[:3]}"
        report.add("DOI-G03-NO-PROVIDER-FETCH", "PASS" if ok else "FAIL",
                   detail, "DOI-D23, DOI-D24")

    # ---- G04..G08 control-plane gates -------------------------------------
    try:
        uri = f"file:{db_path.as_posix()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as con:
            present = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            missing = sorted(set(DOI_TABLES) - present)
            if missing:
                for gate, closes in (
                    ("DOI-G04-AUTHORITY-COLUMNS", "sec.6 / DOI-D06"),
                    ("DOI-G05-APPEND-ONLY-TRIGGERS", "invariant 12"),
                    ("DOI-G06-FAMILY-COVERAGE", "DOI-D24"),
                    ("DOI-G07-DATASET-LINEAGE", "invariant 11 / DOI-D24"),
                    ("DOI-G08-NO-ACCEPTED-MODEL-OR-POLICY", "DOI-8/9 accept."),
                ):
                    report.add(gate, "AWAITING",
                               f"DOI tables not created yet: {','.join(missing)}", closes)
            else:
                violations = 0
                for table in ("doi_contract_families", "doi_contract_assessments"):
                    violations += int(con.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE run_id=? AND "
                        "(decision_authority<>'NONE' OR can_change_direction<>0 OR "
                        "can_invalidate_thesis<>0 OR can_grant_capital<>0)",
                        (run_id,)).fetchone()[0])
                report.add("DOI-G04-AUTHORITY-COLUMNS",
                           "PASS" if violations == 0 else "FAIL",
                           f"authority violations={violations}", "sec.6 / DOI-D06")

                triggers = {r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'")}
                expected = 2 * len(DOI_TABLES[:6])
                got = len([t for t in triggers if t.startswith("trg_doi_")])
                report.add("DOI-G05-APPEND-ONLY-TRIGGERS",
                           "PASS" if got >= expected else "FAIL",
                           f"trg_doi_* triggers present={got} expected>={expected}",
                           "invariant 12")

                fam = [dict(zip(("d",), r)) for r in con.execute(
                    "SELECT governed_direction FROM doi_contract_families WHERE run_id=?",
                    (run_id,))]
                split = _split([{"governed_direction": r["d"]} for r in fam],
                               "governed_direction")
                report.add("DOI-G06-FAMILY-COVERAGE",
                           "PASS" if fam else "FAIL",
                           f"families persisted={len(fam)}", "DOI-D24", _fmt(split))

                null_lineage = int(con.execute(
                    "SELECT COUNT(*) FROM doi_contract_families WHERE run_id=? AND "
                    "(source_dataset_ids_json='[]' OR source_dataset_ids_json IS NULL "
                    " OR evidence_cutoff_utc IS NULL)", (run_id,)).fetchone()[0])
                report.add("DOI-G07-DATASET-LINEAGE",
                           "PASS" if null_lineage == 0 else "FAIL",
                           f"families with empty dataset lineage or cutoff={null_lineage}",
                           "invariant 11 (the '[]' default is why this gate exists)")

                accepted = int(con.execute(
                    "SELECT COUNT(*) FROM doi_probability_models WHERE status='ACCEPTED'"
                ).fetchone()[0])
                policies = int(con.execute(
                    "SELECT COUNT(*) FROM doi_ranking_policies").fetchone()[0])
                labels = int(con.execute(
                    "SELECT COUNT(*) FROM doi_outcome_labels").fetchone()[0])
                report.add("DOI-G08-NO-ACCEPTED-MODEL-OR-POLICY", "PASS",
                           f"accepted_models={accepted} policies={policies} labels={labels} "
                           "(informational: a non-zero accepted model requires a DOI-8 "
                           "model-card review before any probability is displayed)",
                           "DOI-8/9 accept. / DOI-D19")
    except sqlite3.Error as error:
        report.add("DOI-G04-AUTHORITY-COLUMNS", "FAIL",
                   f"control plane unreadable: {error}", "sec.6")

    # ---- G09 no deterministic value wearing a probability name -------------
    if not book_rows:
        report.add("DOI-G09-NO-PROBABILITY-MISLABEL", "AWAITING",
                   "no final opportunity book", "sec.11.6 / non-goal 5")
    else:
        # A reserved column name is not a mislabel. The defect is a VALUE that
        # is published under a probability name with no accepted model behind
        # it, so a field must be POPULATED to count. Identifier and state
        # fields are excluded by name. (Fixed after the first real run, where
        # all four probability slots were None on 1424/1424 rows and this gate
        # wrongly reported FAIL.)
        model_ids = {
            str(r.get("doi_probability_model_id") or "").strip()
            for r in book_rows
        } - {""}
        suspects: list[str] = []
        for key in book_rows[0].keys():
            low = key.lower()
            if not low.startswith("doi_"):
                continue
            if low.endswith(("_id", "_state", "_version", "_applicability")):
                continue
            if "uncalibrated" in low or "applicab" in low:
                continue
            if not any(tok in low for tok in ("prob", "likelihood", "p_", "confidence")):
                continue
            populated = sum(
                1 for r in book_rows
                if r.get(key) not in (None, "", [], {})
            )
            if populated and not model_ids:
                suspects.append(f"{key}({populated} rows, no model id)")
        report.add("DOI-G09-NO-PROBABILITY-MISLABEL",
                   "PASS" if not suspects else "FAIL",
                   f"populated DOI probability-named values with no accepted "
                   f"model: {suspects or 'none'}"
                   + (f"; accepted model ids seen: {sorted(model_ids)}" if model_ids else ""),
                   "sec.11.6, non-goal 5")

    # ---- G10 Lab population and EIL wording -------------------------------
    if not book_rows:
        report.add("DOI-G10-LAB-POPULATION", "AWAITING", "no final opportunity book",
                   "sec.14 / DOI-D29")
    else:
        split = _split(book_rows, "governed_direction", "final_direction", "direction")
        report.add("DOI-G10-LAB-POPULATION", "PASS",
                   f"rows in the unfiltered governed book={len(book_rows)}",
                   "sec.14", _fmt(split))

    index = REPO / "intelligence-lab" / "static" / "index.html"
    if index.exists():
        text = index.read_text(encoding="utf-8", errors="ignore")
        bad = []
        if "?'YES':'NO'" in text.replace(" ", "") and "Advisory Only" in text:
            bad.append("Advisory Only renders NO on a missing flag (index.html:2737)")
        if "'STOP'" in text:
            bad.append("STOP pill still mapped for non-EXECUTE verdicts (index.html:2116)")
        report.add("DOI-G11-EIL-WORDING", "PASS" if not bad else "FAIL",
                   "; ".join(bad) or "no authority-implying EIL wording found",
                   "DOI-D29 / DOI-10 step 3")

    # ---- G12 Morning Gate needs no new option quote ------------------------
    morning = run_dir / "morning_validation" / f"morning_validated_trades_{run_id}.csv"
    report.add("DOI-G12-MORNING-NO-REQUOTE",
               "PASS" if morning.exists() else "AWAITING",
               f"morning artefact {'present' if morning.exists() else 'absent'}: {morning.name}",
               "invariant 5")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run_id")
    parser.add_argument("--control-plane", type=Path, default=DEFAULT_DB)
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args(argv)

    run_dir = RUNS / args.run_id
    if not run_dir.is_dir():
        print(f"run directory not found: {run_dir}", file=sys.stderr)
        return 1

    report = build(args.run_id, args.control_plane)

    print("=" * 100)
    print(f"AVS-TST-DOI-001 DOI gate report - run {args.run_id}")
    print(f"source: {run_dir}   (read only)")
    print(f"control plane: {args.control_plane}   (opened mode=ro)")
    print("=" * 100)
    width = max(len(row.gate) for row in report.rows)
    for row in report.rows:
        marker = "*" if row.gate in P0_GATES else " "
        print(f"  {row.verdict:9s} {marker} {row.gate:{width}s}  {row.detail}")
        if row.three_direction:
            print(f"            {'':{width}s}   -> {row.three_direction}")
        print(f"            {'':{width}s}   closes: {row.closes}")
    print("-" * 100)
    failures = [r for r in report.rows if r.verdict == "FAIL" and r.gate in P0_GATES]
    awaiting = [r for r in report.rows if r.verdict == "AWAITING"]
    print(f"gates={len(report.rows)}  "
          f"pass={sum(1 for r in report.rows if r.verdict == 'PASS')}  "
          f"fail={sum(1 for r in report.rows if r.verdict == 'FAIL')}  "
          f"awaiting={len(awaiting)}")
    print(f"P0 failures: {len(failures)}"
          + (" -> " + ", ".join(r.gate for r in failures) if failures else ""))
    print("* = P0 gate")

    if args.json_path:
        Path(args.json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_path).write_text(json.dumps(
            {"run_id": args.run_id,
             "rows": [vars(r) for r in report.rows]}, indent=2), encoding="utf-8")
        print(f"json: {args.json_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
