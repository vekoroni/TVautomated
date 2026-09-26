"""Read-only old/new horizon diagnostic for a stored Lab book.

This compares only the target-versus-volatility review flag, not realised
returns, trade permission, or a reconstructed historical Evening decision.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.pretrade_focus import _cumulative_expected_move_pct, TARGET_EXPECTED_MOVE_REVIEW_MULTIPLE


LEGACY_FIELD = {
    "1_5D": "garch_expected_move_1_5d",
    "6_10D": "garch_expected_move_6_10d",
    "11_20D": "garch_expected_move_11_20d",
}


def _positive(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def audit_rows(rows: list[dict]) -> dict[str, object]:
    counts: Counter[str] = Counter()
    by_horizon: dict[str, Counter[str]] = {}
    for row in rows:
        horizon = str(row.get("time_horizon") or row.get("horizon_bucket") or "").upper()
        if horizon not in LEGACY_FIELD:
            counts["unsupported_horizon"] += 1
            continue
        group = by_horizon.setdefault(horizon, Counter())
        spot = _positive(row.get("signal_price"))
        target = _positive(row.get("target_price"))
        old = _positive(row.get(LEGACY_FIELD[horizon]))
        corrected = _cumulative_expected_move_pct(row, horizon)
        if spot is None or target is None or old is None or corrected is None:
            group["not_comparable"] += 1
            continue
        move = abs(target / spot - 1.0) * 100.0
        old_review = move > TARGET_EXPECTED_MOVE_REVIEW_MULTIPLE * old
        corrected_review = move > TARGET_EXPECTED_MOVE_REVIEW_MULTIPLE * corrected
        group["comparable"] += 1
        if old_review and not corrected_review:
            group["legacy_false_review"] += 1
        elif corrected_review and not old_review:
            group["new_review"] += 1
        elif corrected_review:
            group["both_review"] += 1
        else:
            group["neither_review"] += 1
    return {
        "total_rows": len(rows),
        "unsupported_horizon": counts["unsupported_horizon"],
        "by_horizon": {key: dict(value) for key, value in sorted(by_horizon.items())},
        "meaning": "review-flag arithmetic only; not a trading outcome or complete Evening replay",
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python tools/avs_int001_horizon_audit.py <stored_lab_book.json>", file=sys.stderr)
        return 2
    source = Path(sys.argv[1]).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("stored Lab book must contain a rows array")
    result = {"source": str(source), "run_id": payload.get("run_id"), **audit_rows(rows)}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
