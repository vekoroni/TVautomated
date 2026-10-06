"""Score macro calls against what the market did next (measured against reality, R10).

Three call sources: the Colab daily regime model, the archived LLM macro packets, and the
board's own past leans. Each is scored from the first tradable open after the call.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from .evidence import effective_n


def packet_direction(label: str | None, switch: str | None, settings: Mapping) -> int:
    text = " ".join(str(v).upper() for v in (label, switch) if v)
    bull = any(token in text for token in settings["packet_bullish_tokens"])
    bear = any(token in text for token in settings["packet_bearish_tokens"])
    if bull and not bear:
        return 1
    if bear and not bull:
        return -1
    return 0


def packet_entry_index(as_of_utc: datetime, sessions: pd.DatetimeIndex, open_utc: str) -> int | None:
    """Index of the first session whose regular open is at or after the call time."""
    hour, minute = (int(x) for x in open_utc.split(":"))
    for index, session in enumerate(sessions):
        opening = datetime.combine(session.date(), time(hour, minute), tzinfo=timezone.utc)
        if opening >= as_of_utc:
            return index
    return None


def _score(calls: Iterable[tuple[int, int]], opens: pd.Series, closes: pd.Series, horizon: int) -> dict:
    """``calls``: (entry_index, direction). Hit = direction matches sign of open->close(h)."""
    rows = []
    o, c = opens.to_numpy(dtype=float), closes.to_numpy(dtype=float)
    for entry, direction in calls:
        exit_index = entry + horizon - 1
        if direction == 0 or exit_index >= len(c) or not np.isfinite(o[entry]) or not np.isfinite(c[exit_index]):
            continue
        ret = c[exit_index] / o[entry] - 1.0
        rows.append((entry, direction, ret))
    if not rows:
        return {"n": 0, "n_eff": 0, "hit_rate": None, "mean_signed_pct": None}
    entries = np.array([r[0] for r in rows])
    signed = np.array([r[1] * r[2] for r in rows]) * 100.0
    return {"n": len(rows), "n_eff": effective_n(entries, horizon),
            "hit_rate": round(float(np.mean(signed > 0)), 4), "mean_signed_pct": round(float(np.mean(signed)), 4)}


def score_regime_model(path: Path, opens: pd.DataFrame, closes: pd.DataFrame, tickers: Sequence[str],
                       horizons: Sequence[int]) -> dict:
    """Colab daily model: row dated D is computed from D's close -> entry at the next open."""
    if not path.exists():
        return {"status": "MISSING"}
    frame = pd.read_csv(path, parse_dates=["Date"])
    sessions = closes.index
    calls = []
    for _, row in frame.iterrows():
        regime = str(row.get("Regime", "")).upper()
        direction = 1 if "ON" in regime else -1 if "OFF" in regime else 0
        position = sessions.searchsorted(row["Date"], side="right")
        if position < len(sessions):
            calls.append((int(position), direction))
    accuracy = frame["Model_Accuracy"].dropna().iloc[-1] if "Model_Accuracy" in frame else None
    return {"status": "OK", "calls": len(calls), "first": str(frame["Date"].min().date()),
            "last": str(frame["Date"].max().date()),
            "self_reported_accuracy": None if accuracy is None else round(float(accuracy), 4),
            "results": {t: {str(h): _score(calls, opens[t], closes[t], h) for h in horizons}
                        for t in tickers if t in closes.columns}}


def load_archive_packets(archive_dir: Path) -> list[dict]:
    """One entry per macro generation time, with every label its archived projections carry.

    Two archive schemas exist: the full macro contract (as_of_utc, regime_label) and the
    normalised quant packet (macro_generated_at_utc; macro_regime_sub_state carries the
    BULLISH/BEARISH qualifier). Several projections of one generation may be archived."""
    by_time: dict[pd.Timestamp, dict] = {}
    for path in sorted(archive_dir.glob("*.json")):
        try:
            packet = json.loads(path.read_text(encoding="utf-8")).get("packet") or {}
        except (OSError, ValueError):
            continue
        stamp = (packet.get("macro_generated_at_utc") or packet.get("as_of_utc")
                 or (packet.get("_builder_metadata") or {}).get("built_at"))
        if not stamp:
            continue
        when = pd.Timestamp(stamp)
        when = when.tz_localize("UTC") if when.tzinfo is None else when.tz_convert("UTC")
        label = packet.get("macro_regime_sub_state") or packet.get("regime_label") or packet.get("macro_regime_label")
        entry = by_time.setdefault(when, {"when": when, "labels": [], "switches": [], "projections": 0,
                                          "session_date": packet.get("macro_session_date") or packet.get("report_date")})
        entry["projections"] += 1
        entry["labels"].append(label)
        entry["switches"].append(packet.get("risk_on_off_switch"))
    return sorted(by_time.values(), key=lambda item: item["when"])


def resolve_direction(packet: Mapping, settings: Mapping) -> tuple[int, str]:
    """Direction of one macro generation across its projections: agreed direction, NEUTRAL,
    or CONFLICTING when projections point opposite ways (scored as no call)."""
    directions = {packet_direction(label, switch, settings) for label, switch in zip(packet["labels"], packet["switches"])}
    directional = directions - {0}
    if len(directional) > 1:
        return 0, "CONFLICTING"
    if directional:
        return directional.pop(), "AGREED" if directions == directional else "PARTIAL"
    return 0, "NEUTRAL"


def score_packets(packets: Sequence[dict], opens: pd.DataFrame, closes: pd.DataFrame, tickers: Sequence[str],
                  horizons: Sequence[int], settings: Mapping) -> dict:
    """Latest macro wins: for each entry session, the newest generation before its open."""
    sessions = closes.index
    by_entry: dict[int, dict] = {}
    listing = []
    for packet in packets:
        direction, agreement = resolve_direction(packet, settings)
        entry = packet_entry_index(packet["when"].to_pydatetime(), sessions, settings["us_regular_open_utc"])
        row = {"generated_utc": packet["when"].isoformat(), "labels": sorted({str(l) for l in packet["labels"]}),
               "projections": packet["projections"], "direction": direction, "agreement": agreement,
               "entry_session": None if entry is None else str(sessions[entry].date())}
        listing.append(row)
        if entry is not None:
            by_entry[entry] = {**row, "entry": entry}       # packets are time-ordered: newest wins
    calls = [(entry, row["direction"]) for entry, row in sorted(by_entry.items())]
    superseded = {row["generated_utc"] for row in listing} - {row["generated_utc"] for row in by_entry.values()}
    for row in listing:
        row["used"] = row["generated_utc"] not in superseded and row["entry_session"] is not None
    return {"status": "OK" if packets else "MISSING", "generations": len(packets),
            "entry_sessions": len(calls), "directional": sum(1 for _, d in calls if d != 0),
            "conflicting": sum(1 for row in listing if row["agreement"] == "CONFLICTING"),
            "partial": sum(1 for row in listing if row["agreement"] == "PARTIAL"),
            "listing": listing[::-1][:25],
            "results": {t: {str(h): _score(calls, opens[t], closes[t], h) for h in horizons}
                        for t in tickers if t in closes.columns}}


def score_board_snapshots(snapshot_dir: Path, opens: pd.DataFrame, closes: pd.DataFrame,
                          horizons: Sequence[int]) -> dict:
    """The board's own UP/DOWN leans, scored once their horizon has completed, beside the
    price-only baseline leans recorded on the same day (what macro adds beyond drift)."""
    sessions = closes.index
    snapshots = sorted(snapshot_dir.glob("board_*.json")) if snapshot_dir.exists() else []
    calls = {kind: {str(h): [] for h in horizons} for kind in ("leans", "baseline_leans")}
    for path in snapshots:
        try:
            snap = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        position = int(sessions.searchsorted(pd.Timestamp(snap["as_of_session"]), side="right"))
        for kind in calls:
            for ticker, leans in (snap.get(kind) or {}).items():
                if ticker not in closes.columns:
                    continue
                for h, lean in leans.items():
                    if lean in ("UP", "DOWN") and h in calls[kind]:
                        calls[kind][h].append((ticker, position, 1 if lean == "UP" else -1))

    def score(rows_in, horizon):
        rows = []
        for ticker, entry, direction in rows_in:
            exit_index = entry + horizon - 1
            if exit_index >= len(sessions):
                continue
            o, c = opens[ticker].iloc[entry], closes[ticker].iloc[exit_index]
            if np.isfinite(o) and np.isfinite(c):
                rows.append(direction * (c / o - 1.0) * 100.0)
        return {"scored": len(rows), "pending": len(rows_in) - len(rows),
                "hit_rate": round(float(np.mean(np.array(rows) > 0)), 4) if rows else None,
                "mean_signed_pct": round(float(np.mean(rows)), 4) if rows else None}

    return {"snapshots": len(snapshots),
            "results": {h: score(calls["leans"][h], int(h)) for h in calls["leans"]},
            "baseline": {h: score(calls["baseline_leans"][h], int(h)) for h in calls["baseline_leans"]}}


# --- US Money Index: grouped by its own ladder, not turned into an invented call ----------

def ladder_band(score: float | None, ladder: Mapping[str, str]) -> str | None:
    """Band name for ``score`` from the packet's own ladder ({"0-40": NAME, ...})."""
    if score is None:
        return None
    for span, name in ladder.items():
        low, high = (float(x) for x in span.split("-"))
        if low <= float(score) <= high:
            return name
    return None


def score_money_index(packet: Mapping | None, opens: pd.DataFrame, closes: pd.DataFrame, tickers: Sequence[str],
                      horizons: Sequence[int], settings: Mapping) -> dict:
    """Forward returns after each revision, grouped by the Money Index's own ladder band.
    Latest revision before each session's open wins. Descriptive: no direction is assigned."""
    if not packet:
        return {"status": "MISSING"}
    score_block = packet.get("risk_off_transmission_score") or {}
    ladder = score_block.get("ladder") or {}
    history = packet.get("revision_history") or []
    sessions = closes.index
    by_entry: dict[int, dict] = {}
    for item in history:
        stamp, score = item.get("generated_utc"), item.get("risk_off_transmission_score")
        if not stamp or score is None:
            continue
        when = pd.Timestamp(stamp)
        when = when.tz_localize("UTC") if when.tzinfo is None else when.tz_convert("UTC")
        entry = packet_entry_index(when.to_pydatetime(), sessions, settings["us_regular_open_utc"])
        if entry is not None and (entry not in by_entry or when > by_entry[entry]["when"]):
            by_entry[entry] = {"when": when, "score": float(score), "band": ladder_band(score, ladder)}
    results: dict = {}
    for ticker in tickers:
        if ticker not in closes.columns:
            continue
        o, c = opens[ticker].to_numpy(dtype=float), closes[ticker].to_numpy(dtype=float)
        per_h = {}
        for horizon in horizons:
            groups: dict[str, list] = {}
            for entry, row in sorted(by_entry.items()):
                exit_index = entry + horizon - 1
                if exit_index >= len(c) or not np.isfinite(o[entry]) or not np.isfinite(c[exit_index]):
                    continue
                groups.setdefault(row["band"] or "UNBANDED", []).append((entry, (c[exit_index] / o[entry] - 1.0) * 100.0))
            per_h[str(horizon)] = {band: {"n": len(rows), "n_eff": effective_n([r[0] for r in rows], horizon),
                                          "mean_pct": round(float(np.mean([r[1] for r in rows])), 4),
                                          "up_rate": round(float(np.mean([r[1] > 0 for r in rows])), 4)}
                                   for band, rows in groups.items()}
        results[ticker] = per_h
    return {"status": "OK", "revisions": len(history), "entry_sessions": len(by_entry), "ladder": ladder,
            "calls": [{"entry_session": str(sessions[e].date()), "score": r["score"], "band": r["band"]}
                      for e, r in sorted(by_entry.items())][::-1],
            "results": results}
