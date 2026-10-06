"""ETF holdings from the issuers' daily files (State Street xlsx, Invesco JSON), and what
those holdings did: weight x return contribution and weight-share participation.

Fetching is the only network step and is explicit (``refresh``); every raw download is
archived content-addressed under ``output/holdings/raw`` so a board can be reproduced.
Holdings without a price in the store are reported as unpriced weight, never as zero return.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pandas as pd

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
_TICKER = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


# --- parsing -------------------------------------------------------------------------------

def xlsx_rows(data: bytes) -> list[list[Any]]:
    """First worksheet as rows of cell values (no third-party dependency)."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    shared: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")) for si in root.findall("m:si", _NS)]
    sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in sheet.iter(f"{{{_NS['m']}}}row"):
        values = []
        for cell in row.findall("m:c", _NS):
            value, kind = cell.find("m:v", _NS), cell.get("t")
            if kind == "s" and value is not None:
                values.append(shared[int(value.text)])
            elif kind == "inlineStr":
                values.append("".join(x.text or "" for x in cell.iter(f"{{{_NS['m']}}}t")))
            else:
                values.append(None if value is None else value.text)
        rows.append(values)
    return rows


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


def parse_ssga_rows(rows: Sequence[Sequence[Any]]) -> list[dict]:
    """State Street daily holdings: header row starts with Name/Ticker; cash and blank
    tickers are dropped."""
    header_at = next((i for i, r in enumerate(rows) if r and r[0] == "Name" and len(r) > 1 and r[1] == "Ticker"), None)
    if header_at is None:
        return []
    header = list(rows[header_at])
    col = {name: header.index(name) for name in ("Name", "Ticker", "Weight", "Shares Held", "Sector") if name in header}
    out = []
    for row in rows[header_at + 1:]:
        if not row or row[0] is None:
            continue
        ticker = str(row[col["Ticker"]] or "").strip().upper()
        weight = _number(row[col["Weight"]]) if "Weight" in col else None
        if not _TICKER.match(ticker) or weight is None:
            continue
        out.append({"ticker": ticker, "name": row[col["Name"]], "weight_pct": weight,
                    "shares": _number(row[col["Shares Held"]]) if "Shares Held" in col else None})
    return out


def ssga_as_of(rows: Sequence[Sequence[Any]]) -> str | None:
    for row in rows[:6]:
        if row and str(row[0]).startswith("Holdings") and len(row) > 1 and row[1]:
            match = re.search(r"(\d{2}-[A-Za-z]{3}-\d{4})", str(row[1]))
            if match:
                return datetime.strptime(match.group(1), "%d-%b-%Y").date().isoformat()
    return None


def parse_invesco_json(payload: Mapping) -> list[dict]:
    out = []
    for item in payload.get("holdings") or []:
        ticker = str(item.get("ticker") or "").strip().upper()
        weight = _number(item.get("percentageOfTotalNetAssets"))
        if not _TICKER.match(ticker) or weight is None:
            continue
        out.append({"ticker": ticker, "name": item.get("issuerName"), "weight_pct": weight,
                    "shares": _number(item.get("units"))})
    return out


# --- fetching (explicit network step) ------------------------------------------------------

def _download(requests, source: Mapping, timeout: float, attempts: int = 3, pause_seconds: float = 5.0) -> bytes:
    """GET with a short, polite retry: issuer endpoints intermittently refuse (Invesco 406)."""
    import time
    for attempt in range(1, attempts + 1):
        response = requests.get(source["url"], headers={"User-Agent": _USER_AGENT, "Accept": source.get("accept", "*/*")},
                                timeout=timeout)
        if response.ok:
            return response.content
        if attempt == attempts or response.status_code not in (406, 429, 500, 502, 503, 504):
            response.raise_for_status()
        time.sleep(pause_seconds * attempt)
    raise RuntimeError("unreachable")


def refresh(sources: Mapping[str, Mapping], out_dir: Path, timeout: float = 40.0) -> dict:
    """Download each issuer file, archive the raw bytes, write normalised ``<ETF>_latest.json``."""
    import requests

    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for etf, source in sources.items():
        try:
            data = _download(requests, source, timeout)
            if source["format"] == "ssga_xlsx":
                rows = xlsx_rows(data)
                holdings, as_of = parse_ssga_rows(rows), ssga_as_of(rows)
            elif source["format"] == "invesco_json":
                payload = json.loads(data)
                holdings, as_of = parse_invesco_json(payload), payload.get("effectiveBusinessDate")
            else:
                raise ValueError(f"unknown holdings format {source['format']}")
            if not holdings:
                raise ValueError("no holdings parsed")
            digest = hashlib.sha256(data).hexdigest()
            suffix = ".xlsx" if source["format"] == "ssga_xlsx" else ".json"
            raw_name = f"{digest[:16]}_{etf}_{as_of}{suffix}"
            (raw_dir / raw_name).write_bytes(data)
            record = {"etf": etf, "issuer": source["issuer"], "as_of": as_of, "url": source["url"],
                      "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "raw_sha256": digest, "raw_file": raw_name,
                      "total_weight_pct": round(sum(h["weight_pct"] for h in holdings), 4), "holdings": holdings}
            (out_dir / f"{etf}_latest.json").write_text(json.dumps(record), encoding="utf-8")
            report[etf] = {"status": "OK", "as_of": as_of, "count": len(holdings)}
        except Exception as exc:                                   # one issuer failing never stops the board
            report[etf] = {"status": "FAILED", "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return report


def load_latest(out_dir: Path, etfs: Sequence[str]) -> dict:
    out = {}
    for etf in etfs:
        path = out_dir / f"{etf}_latest.json"
        if path.exists():
            try:
                out[etf] = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
    return out


# --- what the holdings did -----------------------------------------------------------------

def contribution(holdings: Sequence[Mapping], closes: pd.DataFrame, *, window: int, trend_sessions: int,
                 holdings_as_of: pd.Timestamp | None = None) -> dict:
    """Weight x return over the last ``window`` sessions, plus participation.

    Issuer weights describe the fund on ``holdings_as_of``. They are drifted back to the window
    start (w0 = w / (P_asof / P_start)) and renormalised to the priced share of the fund, so
    holdings that rallied are not over-weighted (end-weights overstated SPY's 20d move by ~0.9 pp
    on 6 Oct 2026). A holding needs a bar on the last session, the window start and the holdings
    date; otherwise its weight is reported as unpriced, never treated as a zero return."""
    session, start = closes.index[-1], closes.index[-1 - window] if len(closes.index) > window else None
    as_of = holdings_as_of if holdings_as_of is not None and holdings_as_of in closes.index else session
    priced_items, unpriced, above = [], 0.0, 0.0
    for item in holdings:
        ticker, weight = item["ticker"], float(item["weight_pct"])
        series = closes[ticker] if ticker in closes.columns else None
        values = None if series is None or start is None else (series.get(session), series.get(start), series.get(as_of))
        if values is None or any(v is None or not np.isfinite(v) or v <= 0 for v in values):
            unpriced += weight
            continue
        p_end, p_start, p_asof = values
        priced_items.append((item, weight, p_end / p_start - 1.0, weight / (p_asof / p_start)))
        history = series.loc[:session].dropna()
        if len(history) >= trend_sessions and history.iloc[-1] > history.iloc[-trend_sessions:].mean():
            above += weight
    priced = sum(w for _, w, _, _ in priced_items)
    start_total = sum(w0 for _, _, _, w0 in priced_items)
    rows = []
    for item, weight, ret, w0 in priced_items:
        start_weight = w0 / start_total * priced if start_total else 0.0
        rows.append({"ticker": item["ticker"], "name": item.get("name"), "weight_pct": round(weight, 4),
                     "start_weight_pct": round(start_weight, 4), "return_pct": round(ret * 100.0, 4),
                     "contribution_pp": round(start_weight * ret, 4)})
    rows.sort(key=lambda r: r["weight_pct"], reverse=True)
    return {
        "rows": rows,
        "priced_weight_pct": round(priced, 4), "unpriced_weight_pct": round(unpriced, 4),
        "sum_contribution_pp": round(sum(r["contribution_pp"] for r in rows), 4),
        "top10_weight_pct": round(sum(r["weight_pct"] for r in rows[:10]), 4),
        "top10_contribution_pp": round(sum(r["contribution_pp"] for r in rows[:10]), 4),
        "participation_weight_pct": round(above / priced * 100.0, 4) if priced else None,
    }
