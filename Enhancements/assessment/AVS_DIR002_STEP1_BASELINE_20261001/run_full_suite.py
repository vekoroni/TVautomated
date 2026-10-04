"""Run every offline test file in its own process and record explicit counts.

DIR-002 Step 1 / R-9 offline part. One file per process with a short
--basetemp (CLAUDE.md). Failures and errors are counted per file from the
pytest summary line, never inferred from a "passed" filter.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(os.environ.get("AVS_SUITE_ROOT") or Path(__file__).resolve().parents[3])
PY = ROOT / "venv" / "Scripts" / "python.exe"
SUMMARY = re.compile(r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed|deselected)")


def discover(selection: str) -> list[Path]:
    files: list[Path] = []
    if selection in {"all", "tests"}:
        files += sorted((ROOT / "tests").glob("test_*.py"))
    if selection in {"all", "vanguard"}:
        files += sorted((ROOT / "vanguard" / "tests").glob("test_*.py"))
    if selection in {"all", "enh"}:
        files += sorted((ROOT / "Enhancements" / "backtest").glob("test_*.py"))
    return files


def run_one(path: Path, timeout: int) -> dict:
    base = Path(tempfile.gettempdir()) / f"avs_fs_{abs(hash(path.name)) % 10**8}"
    cmd = [str(PY), "-m", "pytest", str(path), "-q", "-p", "no:cacheprovider",
           f"--basetemp={base}", "-rfE"]
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              timeout=timeout, encoding="utf-8", errors="replace")
        out = proc.stdout + proc.stderr
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        code = "TIMEOUT"
    counts: dict[str, int] = {}
    tail = "\n".join(out.strip().splitlines()[-3:])
    for number, label in SUMMARY.findall(tail):
        label = "error" if label.startswith("error") else label
        counts[label] = counts.get(label, 0) + int(number)
    failed_ids = re.findall(r"^(?:FAILED|ERROR) (\S+)", out, flags=re.M)
    return {
        "file": str(path.relative_to(ROOT)).replace("\\", "/"),
        "returncode": code,
        "seconds": round(time.time() - started, 1),
        "counts": counts,
        "failed_ids": failed_ids[:50],
        "tail": tail[-600:],
    }


def main() -> None:
    selection = sys.argv[1] if len(sys.argv) > 1 else "all"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).with_name("full_suite_results.jsonl")
    timeout = int(os.environ.get("AVS_FILE_TIMEOUT", "900"))
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            done.add(json.loads(line)["file"])
    shard = sys.argv[3] if len(sys.argv) > 3 else "0/1"
    index, total = (int(x) for x in shard.split("/"))
    for position, path in enumerate(discover(selection)):
        if position % total != index:
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel in done:
            continue
        result = run_one(path, timeout)
        with out_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result) + "\n")
        print(rel, result["returncode"], result["counts"], flush=True)


if __name__ == "__main__":
    main()
