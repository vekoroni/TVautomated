"""Report-only outlier and freshness summary for a staged actuarial v7 parquet.

Nothing is removed or changed: outlier handling is a C4 Evidence design decision.

  python Enhancements/phase0/actuarial_refresh/outlier_report.py <parquet> <report.json>
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pyarrow.compute as pc
import pyarrow.parquet as pq

HORIZONS = (5, 10, 20)
BOUNDS = (1.0, 10.0)   # |return| > 100% and > 1,000%


def main(path: Path, report_path: Path) -> dict:
    columns = ["ticker", "date"] + [f"outcome_{h}d_return" for h in HORIZONS]
    table = pq.read_table(path, columns=columns)
    dates = pc.cast(table["date"], "string")
    report: dict = {
        "path": str(path),
        "rows": table.num_rows,
        "tickers": len(pc.unique(table["ticker"])),
        "date_min": pc.min(dates).as_py(),
        "date_max": pc.max(dates).as_py(),
        "horizons": {},
    }
    for horizon in HORIZONS:
        values = table[f"outcome_{horizon}d_return"]
        valid = pc.is_valid(values)
        absolute = pc.abs(values)
        entry = {
            "labelled_rows": pc.sum(pc.cast(valid, "int64")).as_py(),
            "latest_labelled_date": pc.max(pc.filter(dates, valid)).as_py(),
            "max_abs_return": pc.max(absolute).as_py(),
        }
        for bound in BOUNDS:
            mask = pc.fill_null(pc.greater(absolute, bound), False)
            entry[f"rows_abs_gt_{bound:g}"] = pc.sum(pc.cast(mask, "int64")).as_py()
        worst = pc.fill_null(pc.greater(absolute, BOUNDS[1]), False)
        tickers = pc.filter(table["ticker"], worst)
        counts = pc.value_counts(tickers).to_pylist()
        entry["top_tickers_abs_gt_10"] = sorted(
            ({"ticker": c["values"], "rows": c["counts"]} for c in counts), key=lambda item: -item["rows"]
        )[:15]
        report["horizons"][f"{horizon}d"] = entry
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = main(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps({k: v for k, v in result.items() if k != "horizons"}, indent=2))
    for name, entry in result["horizons"].items():
        print(name, {k: v for k, v in entry.items() if k != "top_tickers_abs_gt_10"})
