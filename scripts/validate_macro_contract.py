# -*- coding: utf-8 -*-
"""
Validate macro snapshot contract (snake_case, aligned to manual macro_intelligence template).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple

REQUIRED = [
    "report_date",
    "as_of_utc",
    "risk_on_switch",
    "regime_state",
    "dir_bias",
    "volatility_mode",
    "trend_energy",
    "usd_state",
    "rates_impulse",
    "liquidity_pulse",
    "sector_bias",
    "regime_drift_status",
    "macro_conviction",
    "conviction_score",
]

def load_json(p: Path) -> Dict[str, Any]:
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def parse_iso(s: str) -> None:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    datetime.fromisoformat(s)

def validate(m: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errs = []
    missing = [k for k in REQUIRED if k not in m]
    if missing:
        errs.append("Missing keys: " + ", ".join(missing))
    if "as_of_utc" in m:
        try:
            parse_iso(str(m["as_of_utc"]))
        except Exception as e:
            errs.append(f"as_of_utc invalid: {m.get('as_of_utc')} ({e})")
    if "conviction_score" in m:
        try:
            float(m["conviction_score"])
        except Exception:
            errs.append("conviction_score must be numeric")
    return (len(errs) == 0), errs

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--macro-path", required=True, help="Path to macro JSON to validate")
    args = ap.parse_args()

    p = Path(args.macro_path)
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    if not p.exists():
        print(f"ERROR: file not found: {p}")
        return 2

    m = load_json(p)
    ok, errs = validate(m)
    if ok:
        print(f"OK: macro contract valid -> {p}")
        return 0
    print(f"FAIL: macro contract invalid -> {p}")
    for e in errs:
        print(" - " + e)
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
