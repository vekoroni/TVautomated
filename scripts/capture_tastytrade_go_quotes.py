"""Optional, read-only broker observation for one completed Morning GO cohort.

Example after broker OAuth environment has been approved for this process:

    python scripts/capture_tastytrade_go_quotes.py \
      --run-id 20260920_203115 \
      --output data/output/runs/20260920_203115/morning_validation/broker_advisory_20260921.json \
      --close-window-start-utc 2026-09-21T19:45:00Z \
      --close-window-end-utc 2026-09-21T20:00:00Z

The close window is explicit; it must not be inferred from fetch time. This
command neither calls order/account tools nor updates the Lab or ledger.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.tastytrade_go_quote_capture import build_go_quote_report  # noqa: E402
from bridge.tastytrade_readonly_mcp import ReadOnlyTastytradeMcp  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--close-window-start-utc")
    parser.add_argument("--close-window-end-utc")
    args = parser.parse_args(argv)
    if not args.run_id.replace("_", "").isdigit() or "/" in args.run_id or "\\" in args.run_id:
        parser.error("run-id must be the exact numeric run identity")
    source = (ROOT / "data" / "output" / "runs" / args.run_id
              / "morning_validation" / f"morning_validated_trades_{args.run_id}.csv")
    if not source.is_file():
        parser.error("the named Morning Gate source file is unavailable")
    output = args.output.resolve()
    if output.exists():
        parser.error("output already exists; broker observations are append-only")
    if not output.parent.is_dir():
        parser.error("output parent directory does not exist")
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with ReadOnlyTastytradeMcp() as broker:
        report = build_go_quote_report(
            rows, broker, run_id=args.run_id,
            close_window_start_utc=args.close_window_start_utc,
            close_window_end_utc=args.close_window_end_utc,
        )
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".tmp", dir=output.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.rename(output)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    print(json.dumps({
        "output": str(output),
        "run_id": args.run_id,
        "requested_contracts": report["requested_contract_count"],
        "close_window_paper_marks": report["close_window_paper_mark_count"],
        "authority": report["authority"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
