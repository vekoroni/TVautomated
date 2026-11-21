"""Display-only fund capital flows. Price performance never establishes a flow."""
from datetime import date
import hashlib
import json
import math
from pathlib import Path


def load_reported_flows(path, tickers, *, as_of):
    """Read publisher-reported net creations/redemptions with exact raw provenance.

    No network, estimates, AUM changes, volume or benchmark returns are accepted.
    Missing and invalid observations remain unavailable rather than zero.
    """
    result = {t: {"status": "UNAVAILABLE", "net_flow_usd": None,
                  "reason": "No verified ETF creations/redemptions source connected."} for t in tickers}
    path = Path(path)
    if not path.exists():
        return result
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        if doc.get("contract_version") != "etf_reported_net_flows_v1":
            raise ValueError("Unsupported fund-flow contract")
        seen = set()
        for row in doc["observations"]:
            t = row["ticker"]
            if t not in result:
                continue
            if t in seen:
                raise ValueError("Conflicting or duplicate ETF flow observations")
            seen.add(t)
            value = row["net_flow_usd"]
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError("Invalid net flow")
            first, last = date.fromisoformat(row["period_start"]), date.fromisoformat(row["period_end"])
            if not first <= last <= date.fromisoformat(as_of):
                raise ValueError("Invalid flow observation dates")
            if row["measure"] != "PUBLISHER_REPORTED_NET_CREATIONS_REDEMPTIONS" or row["currency"] != "USD":
                raise ValueError("Flow must be publisher-reported USD net creations/redemptions")
            if not row["source_url"].startswith("https://") or not row["publisher"]:
                raise ValueError("Publisher provenance required")
            raw = (path.parent / row["raw_file"]).resolve()
            if path.parent.resolve() not in raw.parents:
                raise ValueError("Raw source must stay inside the flow source directory")
            if hashlib.sha256(raw.read_bytes()).hexdigest() != row["raw_sha256"]:
                raise ValueError("Raw fund-flow checksum mismatch")
            result[t] = {**row, "status": "REPORTED", "basis": "NET_FUND_CAPITAL_FLOW",
                         "intraday": False, "source_observation_date": last.isoformat()}
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return {t: {"status": "INVALID_SOURCE", "net_flow_usd": None, "reason": str(exc)} for t in tickers}
    return result


def activity_rows(payload, reported=None):
    """Own-price direction plus share-volume activity; never infer net capital flow."""
    reported = reported or {}
    stories = {r["ticker"]: r for r in (payload.get("day_story") or {}).get("stories", [])}
    tickers = list(dict.fromkeys(list(payload.get("focus", [])) +
                               [r["ticker"] for r in (payload.get("rotation") or {}).get("rows", [])]))
    rows = []
    for t in tickers:
        m = (payload.get("etfs", {}).get(t) or {}).get("metrics") or {}
        value = m.get("ret_1d")
        valid = type(value) in (int, float) and math.isfinite(value) and m.get("status") != "MISSING"
        rows.append({"ticker": t, "price_session": m.get("last_session"),
                     "absolute_1d_pct": value if valid else None,
                     "absolute_5d_pct": m.get("ret_5d"), "absolute_20d_pct": m.get("ret_20d"),
                     "price_direction": "UNAVAILABLE" if not valid else "RISING" if value > 0 else "FALLING" if value < 0 else "UNCHANGED",
                     "relative_volume": (stories.get(t, {}).get("volume") or {}).get("ratio"),
                     "activity_basis": "PRICE_AND_SHARE_VOLUME_ONLY_NOT_CAPITAL_FLOW",
                     "fund_flow": reported.get(t, {"status": "UNAVAILABLE", "net_flow_usd": None,
                                                   "reason": "No verified ETF fund-flow observation."})})
    return {"rows": rows, "basis": "ABSOLUTE_ETF_ACTIVITY_AND_SEPARATE_REPORTED_FUND_FLOWS",
            "note": "Rising/falling prices and trading volume do not establish money entering or leaving a fund. Reported fund flows retain their own reporting period; they are not live order flow."}
