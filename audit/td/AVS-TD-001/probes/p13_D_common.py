"""Shared helpers for Track D probes (read-only)."""
from __future__ import annotations
import json, sqlite3, sys
from pathlib import Path
import pandas as pd

ROOT = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence")
RUNS = ROOT / "data" / "output" / "runs"
AUD = ROOT / "audit" / "td" / "AVS-TD-001"
DB = AUD / "db_copies"
PRIMARY = "20260911_115904"
COMPARISON = "20260910_150045"


def run_dir(run: str) -> Path:
    return RUNS / run


def art(run: str, rel: str) -> Path:
    return run_dir(run) / rel.replace("<run>", run)


def read_csv(path: Path, usecols=None, **kw) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False, usecols=usecols, **kw)


def header(path: Path) -> list[str]:
    import csv
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        return next(csv.reader(fh))


def ro_conn(name: str) -> sqlite3.Connection:
    p = (DB / name).resolve()
    return sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)


def direction_bucket(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().str.upper()
    return s.where(s.isin(["CALL", "PUT"]), "OTHER")


def dump(obj, path: Path):
    path.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    print(f"[written] {path}")


def vc(s: pd.Series, dropna=False) -> dict:
    return {str(k): int(v) for k, v in s.value_counts(dropna=dropna).items()}
