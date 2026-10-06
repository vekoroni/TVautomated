"""MarketData earnings calendar adapter (ACK 3 Oct 2026; design AVS_ANTICIPATED_MOVE_DESIGN_20261003 §9 step 1).

The earnings date is position-risk disclosure, never a gate or score (catalysts are bonuses). MarketData is the
options vendor; the Polygon snapshot carries no earnings field (verified 3 Oct 2026). Three explicit states:
SCHEDULED, NONE_IN_LOOKAHEAD, UNKNOWN (with a reason) - unknown is never "no catalyst" (R1).

One fetch per ticker per session: results are cached in ``cache_dir/<as_of>.json``. The transport is injectable
so tests never touch the network. The API key is read from the environment and never logged or returned.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Tuple
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
EARNINGS_SOURCE = "MARKETDATA_EARNINGS"
LOOKAHEAD_DAYS = 120
_REPORT_TIMES = {"before open": "BEFORE_OPEN", "after close": "AFTER_CLOSE", "during market": "DURING_MARKET"}

Transport = Callable[[str, date, date], Tuple[int, Mapping[str, Any]]]


def _first(payload: Mapping[str, Any], key: str, index: int) -> Any:
    values = payload.get(key) or []
    return values[index] if index < len(values) else None


def parse_marketdata_earnings(payload: Mapping[str, Any], *, as_of: date) -> Dict[str, Any]:
    """The next report on or after ``as_of`` from one MarketData earnings response."""
    status = str((payload or {}).get("s") or "").lower()
    if status == "no_data":
        return {"state": "NONE_IN_LOOKAHEAD", "source": EARNINGS_SOURCE, "lookahead_days": LOOKAHEAD_DAYS}
    if status != "ok":
        reason = str((payload or {}).get("errmsg") or f"PROVIDER_STATUS_{status or 'MISSING'}")
        return {"state": "UNKNOWN", "reason": reason, "source": EARNINGS_SOURCE}
    upcoming = []
    for i, stamp in enumerate(payload.get("reportDate") or []):
        try:
            report = datetime.fromtimestamp(float(stamp), tz=timezone.utc).astimezone(NEW_YORK).date()
        except (TypeError, ValueError, OverflowError, OSError):
            continue
        if report >= as_of:
            upcoming.append((report, i))
    if not upcoming:
        return {"state": "NONE_IN_LOOKAHEAD", "source": EARNINGS_SOURCE, "lookahead_days": LOOKAHEAD_DAYS}
    report, i = min(upcoming)
    year, quarter = _first(payload, "fiscalYear", i), _first(payload, "fiscalQuarter", i)
    raw_time = str(_first(payload, "reportTime", i) or "").strip().lower()
    return {
        "state": "SCHEDULED",
        "date": report.isoformat(),
        "report_time": _REPORT_TIMES.get(raw_time, "UNKNOWN"),
        "fiscal_quarter": f"{year}Q{quarter}" if year and quarter else "",
        "estimated_eps": _first(payload, "estimatedEPS", i),
        "source": EARNINGS_SOURCE,
        # Fix C (ACK 5 Oct 2026): MarketData carries no confirmation field; its future dates can be projections
        # (DELL 27 Nov vs a confirmed 24 Nov). The date is disclosed as the provider's, not confirmed.
        "date_confirmation": "PROVIDER_DATE_UNCONFIRMED",
    }


def _http_transport(api_token: str) -> Transport:
    def get(symbol: str, start: date, end: date) -> Tuple[int, Mapping[str, Any]]:
        url = (f"https://api.marketdata.app/v1/stocks/earnings/{symbol}/"
               f"?from={start.isoformat()}&to={end.isoformat()}")
        request = urllib.request.Request(url, headers={"Authorization": f"Token {api_token}"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            except Exception:  # noqa: BLE001 - provider body is not JSON
                return exc.code, {"s": "error", "errmsg": f"HTTP_{exc.code}"}
    return get


def fetch_marketdata_earnings(
    tickers: Iterable[str],
    *,
    as_of: date,
    cache_dir: Path | str | None = None,
    transport: Transport | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Next earnings report per ticker; UNKNOWN (stated) on any failure. Cached per ``as_of`` session."""
    symbols = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    cache_path = Path(cache_dir) / f"{as_of.isoformat()}.json" if cache_dir else None
    cached: Dict[str, Dict[str, Any]] = {}
    if cache_path and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = {}
    if transport is None:
        token = str(os.environ.get("MARKETDATA_API_KEY") or "").strip()
        transport = _http_transport(token) if token else None
    end = as_of + timedelta(days=LOOKAHEAD_DAYS)
    results: Dict[str, Dict[str, Any]] = {}
    for symbol in symbols:
        if symbol in cached:
            results[symbol] = cached[symbol]
            continue
        if transport is None:
            results[symbol] = {"state": "UNKNOWN", "reason": "MARKETDATA_API_KEY_NOT_CONFIGURED",
                               "source": EARNINGS_SOURCE}
            continue
        try:
            status, payload = transport(symbol, as_of, end)
            parsed = parse_marketdata_earnings(payload, as_of=as_of)
            if status >= 400 and parsed["state"] != "NONE_IN_LOOKAHEAD":
                parsed = {"state": "UNKNOWN", "reason": f"HTTP_{status}", "source": EARNINGS_SOURCE}
        except Exception as exc:  # noqa: BLE001 - every failure is stated per ticker, never a guess
            parsed = {"state": "UNKNOWN", "reason": type(exc).__name__, "source": EARNINGS_SOURCE}
        results[symbol] = parsed
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        # UNKNOWN is not cached, so a transient failure is retried on the next call.
        keep = {**cached, **{s: r for s, r in results.items() if r.get("state") != "UNKNOWN"}}
        cache_path.write_text(json.dumps(keep, sort_keys=True), encoding="utf-8")
    return results
