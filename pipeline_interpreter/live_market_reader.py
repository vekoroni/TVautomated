"""
live_market_reader.py
=====================
Fetches the four live data gaps identified in the WFC Interpreter output:

  1. Intraday options volume  — Polygon.io options chain with volume (not OI-only)
  2. Institutional flow       — Unusual options activity via Polygon/MarketData
  3. Live bid/ask spread      — Polygon snapshot for specific contract
  4. Sector peer confirmation — Live quotes for peer tickers (JPM/BAC/C for WFC etc.)

Called by:
  - /intraday TICKER command in pipeline_interpreter_commands.py
  - /ticker TICKER command (auto-fetches if morning session)
  - morning_thesis_validator.py --live (writes to run folder for Interpreter pickup)

Output paths (written per-ticker):
  MA_Inputs/options_data/TICKER_live_options_{date}.json
  MA_Inputs/options_data/TICKER_peer_quotes_{date}.json

These are auto-detected by scan_ma_inputs_for_ticker() and injected into prompts.
"""

import os
import json
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, date
from pathlib import Path
from typing import Optional

# ── API keys ──────────────────────────────────────────────────────────────────
POLYGON_API_KEY    = os.environ.get(
    "POLYGON_API_KEY",
    "rM5gfljE3Dls1RSYpTFZjhLcG8ekTGL0"
)
MARKETDATA_API_KEY = os.environ.get(
    "MARKETDATA_API_KEY",
    "eVRtV3kxVWQyY1VmTDhFekMwMVBJbTBhTjhEWndoUExXNTFtRURjMHRBND0="
)

# ── Output paths ──────────────────────────────────────────────────────────────
_INTERP_DIR   = Path(__file__).resolve().parent
_MA_OPTIONS   = _INTERP_DIR / "MA_Inputs" / "options_data"
_TODAY        = date.today().strftime("%Y%m%d")

# ── Sector peer map ───────────────────────────────────────────────────────────
# Maps ticker → sector peers for confirmation analysis
SECTOR_PEERS = {
    # Financials / Banks
    "WFC":  ["JPM", "BAC", "C", "GS"],
    "JPM":  ["WFC", "BAC", "C", "GS"],
    "BAC":  ["JPM", "WFC", "C", "MS"],
    "C":    ["JPM", "BAC", "WFC", "GS"],
    "GS":   ["MS", "JPM", "C", "BAC"],
    "MS":   ["GS", "JPM", "C", "BAC"],
    "SCHW": ["IBKR", "RJF", "ETFC", "AMTD"],
    # Insurance
    "MET":  ["PRU", "AFL", "AIG", "ALL"],
    "UNM":  ["MET", "PRU", "AFL", "LNC"],
    # Healthcare
    "PFE":  ["MRK", "ABBV", "JNJ", "BMY"],
    "HCA":  ["THC", "UHS", "CYH", "LPNT"],
    # Real Estate
    "PLD":  ["AMT", "CCI", "EQIX", "DLR"],
    # Energy
    "XLE":  ["XOM", "CVX", "COP", "SLB"],
    "TRGP": ["WMB", "OKE", "KMI", "ET"],
    # Tech
    "GOOGL":["META", "MSFT", "AMZN", "AAPL"],
    "AAPL": ["MSFT", "GOOGL", "META", "AMZN"],
    # Industrials
    "VMC":  ["MLM", "NUE", "X", "CLF"],
    # Consumer
    "TJX":  ["ROST", "BURL", "M", "KSS"],
    "DAL":  ["UAL", "AAL", "LUV", "JBLU"],
    # China
    "BILI": ["SE", "BABA", "JD", "PDD"],
    "SE":   ["BILI", "BABA", "JD", "GRAB"],
    # Default fallback — SPY/QQQ for macro confirmation
    "_DEFAULT": ["SPY", "QQQ", "IWM", "XLF"],
}


def _http_get(url: str, timeout: int = 10) -> Optional[dict]:
    """Simple HTTP GET with JSON response. Returns None on any error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AVSHUNTER/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  ⚠  HTTP error: {e}")
        return None


# ── 1. Intraday options volume (replaces OI_ONLY) ────────────────────────────


def _marketdata_get(path: str, params: Optional[dict] = None, timeout: int = 12) -> Optional[dict]:
    """MarketData.app GET helper. Returns None on transport or API error."""
    params = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
    qs = urllib.parse.urlencode(params)
    url = f"https://api.marketdata.app/v1/{path.lstrip('/')}"
    if qs:
        url = f"{url}?{qs}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AVSHUNTER/1.0",
                "Authorization": f"Bearer {MARKETDATA_API_KEY}",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            payload["_http_status"] = getattr(resp, "status", None)
            if payload.get("s") not in ("ok", "no_data"):
                print(f"  [MARKETDATA] status={payload.get('s')} msg={payload.get('errmsg', '')}")
                return None
            return payload
    except Exception as e:
        print(f"  [MARKETDATA] HTTP error: {e}")
        return None


def _take_array(payload: dict, key: str) -> list:
    val = payload.get(key, [])
    return val if isinstance(val, list) else [val]


def _marketdata_chain_rows(ticker: str, expiry: str = None, direction: str = None) -> list[dict]:
    params = {}
    if expiry:
        params["expiration"] = expiry
    if direction:
        params["side"] = direction.lower()
    payload = _marketdata_get(f"options/chain/{ticker.upper()}/", params=params)
    if not payload or payload.get("s") != "ok":
        return []
    symbols = _take_array(payload, "optionSymbol")
    rows: list[dict] = []
    for i, symbol in enumerate(symbols):
        def at(key, default=None):
            arr = _take_array(payload, key)
            return arr[i] if i < len(arr) else default
        rows.append({
            "contract": symbol,
            "type": str(at("side", "") or "").lower(),
            "strike": at("strike"),
            "expiry": at("expiration"),
            "dte": at("dte"),
            "bid": at("bid"),
            "ask": at("ask"),
            "mid": at("mid"),
            "volume": at("volume") or 0,
            "open_interest": at("openInterest") or 0,
            "delta": at("delta"),
            "gamma": at("gamma"),
            "theta": at("theta"),
            "vega": at("vega"),
            "iv": at("iv"),
            "updated": at("updated"),
            "source": "MARKETDATA_OPTIONS_CHAIN",
            "freshness": "DELAYED_OR_REALTIME_BY_ENTITLEMENT",
        })
    return rows


def _marketdata_option_quote(contract_ticker: str) -> Optional[dict]:
    contract = str(contract_ticker or "").upper().replace("O:", "")
    if not contract:
        return None
    payload = _marketdata_get(f"options/quotes/{contract}/")
    if not payload or payload.get("s") != "ok":
        return None
    def one(key, default=None):
        arr = _take_array(payload, key)
        return arr[0] if arr else default
    return {
        "contract": contract,
        "bid": one("bid"),
        "ask": one("ask"),
        "mid": one("mid"),
        "volume": one("volume"),
        "open_interest": one("openInterest"),
        "delta": one("delta"),
        "gamma": one("gamma"),
        "theta": one("theta"),
        "vega": one("vega"),
        "iv": one("iv"),
        "updated": one("updated"),
        "source": "MARKETDATA_OPTIONS_QUOTE",
        "freshness": "DELAYED_OR_REALTIME_BY_ENTITLEMENT",
    }

def fetch_intraday_options_volume(
    ticker: str,
    expiry: str = None,
    direction: str = None,
    min_volume: int = 50,
    limit: int = 25,
) -> dict:
    """Fetch option volume from MarketData.app. Polygon options are retired."""
    print(f"  [LIVE] Fetching MarketData options volume: {ticker}...")
    rows = _marketdata_chain_rows(ticker, expiry=expiry, direction=direction)
    if not rows:
        print(f"  [LIVE] No MarketData options volume data for {ticker}")
        return {"status": "NO_DATA", "ticker": ticker, "source": "MARKETDATA_OPTIONS_CHAIN"}

    processed = []
    total_call_vol = 0
    total_put_vol = 0
    for r in rows:
        vol = int(r.get("volume") or 0)
        oi = int(r.get("open_interest") or 0)
        if vol < min_volume:
            continue
        ctype = str(r.get("type") or "").lower()
        if ctype == "call":
            total_call_vol += vol
        elif ctype == "put":
            total_put_vol += vol
        processed.append({
            "contract": r.get("contract", ""),
            "type": ctype,
            "strike": r.get("strike"),
            "expiry": r.get("expiry"),
            "dte": r.get("dte"),
            "volume": vol,
            "open_interest": oi,
            "vol_oi_ratio": round(vol / oi, 3) if oi > 0 else None,
            "delta": r.get("delta"),
            "iv": r.get("iv"),
            "mid": r.get("mid"),
        })

    processed.sort(key=lambda x: int(x.get("volume") or 0), reverse=True)
    pcr = round(total_put_vol / total_call_vol, 3) if total_call_vol > 0 else None
    put_flag = None
    if total_put_vol > 0 and total_call_vol > 0:
        if total_put_vol >= total_call_vol * 3:
            put_flag = f"PUT_VOLUME_{round(total_put_vol/total_call_vol, 1)}X_CALLS -- institutional put positioning confirmed"
        elif total_call_vol >= total_put_vol * 3:
            put_flag = f"CALL_VOLUME_{round(total_call_vol/total_put_vol, 1)}X_PUTS -- institutional call positioning confirmed"
    result = {
        "status": "OK",
        "ticker": ticker,
        "fetched_at": datetime.now().strftime("%H:%M ET"),
        "source": "MARKETDATA_OPTIONS_CHAIN",
        "data_freshness": "DELAYED_OR_REALTIME_BY_ENTITLEMENT",
        "total_call_volume": total_call_vol,
        "total_put_volume": total_put_vol,
        "put_call_ratio": pcr,
        "put_volume_flag": put_flag,
        "contracts": processed[:20],
        "data_note": "MARKETDATA_OPTIONS_VOLUME -- no Polygon options calls",
    }
    print(f"  [LIVE] MarketData options volume: {ticker} | calls={total_call_vol:,} puts={total_put_vol:,} PCR={pcr}")
    return result

def fetch_unusual_options_activity(
    ticker: str,
    min_premium: float = 50000,
    lookback_hours: int = 4,
) -> dict:
    """Infer unusual activity from MarketData chain volume/OI and premium."""
    print(f"  [LIVE] Fetching MarketData unusual options activity: {ticker}...")
    rows = _marketdata_chain_rows(ticker)
    if not rows:
        return {"status": "NO_DATA", "ticker": ticker, "source": "MARKETDATA_OPTIONS_CHAIN"}
    unusual = []
    for r in rows:
        oi = int(r.get("open_interest") or 0)
        vol = int(r.get("volume") or 0)
        mid = float(r.get("mid") or 0)
        vol_oi = vol / oi if oi > 0 else (float(vol) if vol > 0 else 0.0)
        premium = vol * mid * 100
        if vol_oi < 2 or premium < min_premium:
            continue
        ctype = str(r.get("type") or "").lower()
        flag = "EXTREME_UNUSUAL_VOLUME" if vol_oi >= 10 else "HIGH_UNUSUAL_VOLUME" if vol_oi >= 5 else "UNUSUAL_VOLUME"
        unusual.append({
            "contract": r.get("contract", ""),
            "type": ctype,
            "strike": r.get("strike"),
            "expiry": r.get("expiry"),
            "volume": vol,
            "open_interest": oi,
            "vol_oi_ratio": round(vol_oi, 2),
            "premium_usd": round(premium, 0),
            "flag": flag,
            "direction_signal": (
                f"INSTITUTIONAL_{ctype.upper()}_POSITIONING"
                if flag in ("HIGH_UNUSUAL_VOLUME", "EXTREME_UNUSUAL_VOLUME")
                else "ELEVATED_ACTIVITY"
            ),
        })
    unusual.sort(key=lambda x: x["premium_usd"], reverse=True)
    inst_calls = sum(1 for u in unusual if u["type"] == "call" and "INSTITUTIONAL" in u["direction_signal"])
    inst_puts = sum(1 for u in unusual if u["type"] == "put" and "INSTITUTIONAL" in u["direction_signal"])
    inst_bias = (
        "INSTITUTIONAL_PUT_BIAS" if inst_puts > inst_calls else
        "INSTITUTIONAL_CALL_BIAS" if inst_calls > inst_puts else
        "INSTITUTIONAL_NEUTRAL"
    )
    result = {
        "status": "OK",
        "ticker": ticker,
        "fetched_at": datetime.now().strftime("%H:%M ET"),
        "source": "MARKETDATA_OPTIONS_CHAIN",
        "data_freshness": "DELAYED_OR_REALTIME_BY_ENTITLEMENT",
        "unusual_count": len(unusual),
        "institutional_bias": inst_bias,
        "inst_call_signals": inst_calls,
        "inst_put_signals": inst_puts,
        "flows": unusual[:10],
        "data_note": "MARKETDATA_FLOW_PROXY -- vol/OI method, no Polygon options calls",
    }
    print(f"  [LIVE] MarketData unusual activity: {ticker} | {len(unusual)} flags | bias={inst_bias}")
    return result

def fetch_live_contract_spread(
    contract_ticker: str,
) -> dict:
    """Fetch live/delayed bid/ask spread for a contract from MarketData.app."""
    print(f"  [LIVE] Fetching MarketData live spread: {contract_ticker}...")
    q = _marketdata_option_quote(contract_ticker)
    if not q:
        return {"status": "NO_DATA", "contract": contract_ticker, "source": "MARKETDATA_OPTIONS_QUOTE"}
    bid = float(q.get("bid") or 0)
    ask = float(q.get("ask") or 0)
    mid = float(q.get("mid") or ((bid + ask) / 2 if bid and ask else 0) or 0)
    spread_abs = round(ask - bid, 4) if bid and ask else None
    spread_pct = round(spread_abs / mid * 100, 2) if mid and spread_abs is not None else None
    if spread_pct is None:
        spread_quality = "UNKNOWN"
    elif spread_pct <= 5:
        spread_quality = "TIGHT -- tradeable"
    elif spread_pct <= 15:
        spread_quality = "ACCEPTABLE -- enter at mid"
    elif spread_pct <= 25:
        spread_quality = "WIDE -- use limit order at mid, may not fill"
    else:
        spread_quality = "VERY_WIDE -- consider different expiry or strike"
    result = {
        "status": "OK",
        "contract": contract_ticker,
        "fetched_at": datetime.now().strftime("%H:%M ET"),
        "source": "MARKETDATA_OPTIONS_QUOTE",
        "data_freshness": q.get("freshness") or "DELAYED_OR_REALTIME_BY_ENTITLEMENT",
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread_abs": spread_abs,
        "spread_pct": spread_pct,
        "spread_quality": spread_quality,
        "volume": q.get("volume"),
        "open_interest": q.get("open_interest"),
        "delta": q.get("delta"),
        "gamma": q.get("gamma"),
        "theta": q.get("theta"),
        "vega": q.get("vega"),
        "iv": q.get("iv"),
        "updated": q.get("updated"),
        "data_note": "MARKETDATA_LIVE_SPREAD -- no Polygon options calls",
    }
    print(f"  [LIVE] MarketData spread: {contract_ticker} | bid={bid} ask={ask} spread={spread_pct}% -- {spread_quality}")
    return result

def fetch_peer_quotes(
    ticker: str,
    peers: list = None,    # override auto-lookup if supplied
) -> dict:
    """
    Fetch live quotes for sector peers to confirm or deny thesis direction.

    If WFC is a PUT thesis (bearish banks), JPM/BAC/C should also be weak.
    If they are NOT weak, that is a divergence signal — thesis needs reassessment.

    Uses Polygon snapshot endpoint for equity tickers.
    """
    peers = peers or SECTOR_PEERS.get(ticker.upper(), SECTOR_PEERS["_DEFAULT"])
    print(f"  [LIVE] Fetching peer quotes: {ticker} peers={peers}...")

    quotes = []
    for peer_sym in peers:
        try:
            peer_data = _marketdata_get(f"stocks/quotes/{peer_sym.upper()}/")
            if not peer_data or peer_data.get("s") != "ok":
                continue
            def _one(key, default=None):
                v = peer_data.get(key, default)
                return v[0] if isinstance(v, list) and v else v
            chg = float(_one("changepct") or 0)
            direction = (
                "UP"   if chg >  0.3 else
                "DOWN" if chg < -0.3 else
                "FLAT"
            )
            quotes.append({
                "ticker":     peer_sym.upper(),
                "price":      _one("last") or _one("mid"),
                "change_pct": round(chg, 2),
                "direction":  direction,
                "volume":     _one("volume"),
                "vwap":       None,
            })
        except Exception:
            continue

    # Assess peer alignment with a PUT thesis (bearish = aligned)
    down_count = sum(1 for q in quotes if q["direction"] == "DOWN")
    up_count   = sum(1 for q in quotes if q["direction"] == "UP")
    flat_count = sum(1 for q in quotes if q["direction"] == "FLAT")

    peer_alignment_put  = round(down_count / len(quotes), 2) if quotes else 0
    peer_alignment_call = round(up_count   / len(quotes), 2) if quotes else 0

    if peer_alignment_put >= 0.75:
        alignment_verdict = "SECTOR_CONFIRMING_BEARISH — majority of peers declining, PUT thesis supported"
    elif peer_alignment_call >= 0.75:
        alignment_verdict = "SECTOR_CONFIRMING_BULLISH — majority of peers rising, CALL thesis supported"
    elif peer_alignment_put >= 0.5:
        alignment_verdict = "SECTOR_LEANING_BEARISH — more peers down than up"
    elif peer_alignment_call >= 0.5:
        alignment_verdict = "SECTOR_LEANING_BULLISH — more peers up than down"
    else:
        alignment_verdict = "SECTOR_DIVERGENT — peers mixed, sector thesis unclear"

    result = {
        "status":              "OK",
        "ticker":              ticker,
        "peers_checked":       peers,
        "fetched_at":          datetime.now().strftime("%H:%M ET"),
        "peer_quotes":         quotes,
        "peers_down":          down_count,
        "peers_up":            up_count,
        "peers_flat":          flat_count,
        "peer_alignment_put":  peer_alignment_put,
        "peer_alignment_call": peer_alignment_call,
        "alignment_verdict":   alignment_verdict,
        "data_note":           (
            "SECTOR_PEER_CONFIRMATION — use to confirm or flag divergence. "
            "Divergent sector = thesis faces friction, reduce size or wait."
        ),
    }

    print(f"  ✅ Peer quotes: {peers} | down={down_count} up={up_count} | {alignment_verdict[:40]}")
    return result


# ── Master fetch — all four gaps in one call ──────────────────────────────────

def fetch_all_live_data(
    ticker: str,
    contract_ticker: str = None,   # specific contract e.g. "WFC260618P00072500"
    expiry: str = None,            # e.g. "2026-06-18"
    direction: str = None,         # "call" or "put"
    peers: list = None,
    write_to_ma_inputs: bool = True,
) -> dict:
    """
    Fetch all four live data gaps for a ticker and return as a combined dict.
    Optionally write JSON files to MA_Inputs/options_data/ for Interpreter pickup.

    Call this from:
      - cmd_intraday() before building the intraday prompt
      - cmd_ticker() when session mode is MORNING
      - morning_thesis_validator.py --live after fetching live prices
    """
    print(f"\n  [LIVE DATA] Fetching all live data: {ticker}")
    print(f"  {'─' * 50}")

    results = {"ticker": ticker, "fetched_at": datetime.now().strftime("%H:%M ET")}

    # 1. Intraday options volume
    results["options_volume"] = fetch_intraday_options_volume(
        ticker, expiry=expiry, direction=direction
    )
    time.sleep(0.3)   # rate limit courtesy

    # 2. Unusual / institutional flow
    results["institutional_flow"] = fetch_unusual_options_activity(ticker)
    time.sleep(0.3)

    # 3. Live spread on specific contract (if supplied)
    if contract_ticker:
        results["live_spread"] = fetch_live_contract_spread(contract_ticker)
        time.sleep(0.3)
    else:
        results["live_spread"] = {
            "status": "NOT_REQUESTED",
            "note":   "Supply contract_ticker to fetch live spread. "
                      "Use: fetch_all_live_data(ticker, contract_ticker='WFC260618P00072500')"
        }

    # 4. Sector peer confirmation
    results["peer_confirmation"] = fetch_peer_quotes(ticker, peers=peers)

    # Write to MA_Inputs for Interpreter auto-pickup
    if write_to_ma_inputs:
        _MA_OPTIONS.mkdir(parents=True, exist_ok=True)
        out_path = _MA_OPTIONS / f"{ticker.upper()}_live_data_{_TODAY}.json"
        out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\n  ✅ Live data written: {out_path.name}")
        results["_output_path"] = str(out_path)

    print(f"  {'─' * 50}")
    print(f"  [LIVE DATA] Complete: {ticker}")

    return results


def format_live_data_for_prompt(live_data: dict) -> str:
    """
    Format the combined live data dict into a concise prompt block.
    Called by build_intraday_prompt and build_single_ticker_prompt.
    """
    if not live_data or live_data.get("status") == "NO_DATA":
        return ""

    ticker  = live_data.get("ticker", "")
    fetched = live_data.get("fetched_at", "")
    lines   = [f"LIVE MARKET DATA — {ticker} (fetched {fetched}):"]

    # Options volume
    ov = live_data.get("options_volume", {})
    if ov.get("status") == "OK":
        lines.append(f"\nINTRADAY OPTIONS VOLUME:")
        lines.append(f"  call_volume:    {ov.get('total_call_volume', 0):,}")
        lines.append(f"  put_volume:     {ov.get('total_put_volume', 0):,}")
        lines.append(f"  put_call_ratio: {ov.get('put_call_ratio')}")
        if ov.get("put_volume_flag"):
            lines.append(f"  FLAG: {ov['put_volume_flag']}")
        top = ov.get("contracts", [])[:5]
        if top:
            lines.append(f"  Top contracts by volume:")
            for c in top:
                lines.append(
                    f"    {c.get('type','').upper()} {c.get('strike')} "
                    f"exp={c.get('expiry')} vol={c.get('volume'):,} "
                    f"OI={c.get('open_interest'):,} "
                    f"vol/OI={c.get('vol_oi_ratio')}"
                )

    # Institutional flow
    iflow = live_data.get("institutional_flow", {})
    if iflow.get("status") == "OK" and iflow.get("unusual_count", 0) > 0:
        lines.append(f"\nINSTITUTIONAL FLOW:")
        lines.append(f"  bias:           {iflow.get('institutional_bias')}")
        lines.append(f"  unusual_signals:{iflow.get('unusual_count')}")
        lines.append(f"  inst_put_signals:{iflow.get('inst_put_signals')}")
        lines.append(f"  inst_call_signals:{iflow.get('inst_call_signals')}")
        top_flows = iflow.get("flows", [])[:3]
        if top_flows:
            lines.append(f"  Top flows:")
            for f in top_flows:
                lines.append(
                    f"    {f.get('type','').upper()} {f.get('strike')} "
                    f"exp={f.get('expiry')} "
                    f"vol/OI={f.get('vol_oi_ratio')} "
                    f"premium=${f.get('premium_usd'):,.0f} "
                    f"[{f.get('flag')}]"
                )

    # Live spread
    ls = live_data.get("live_spread", {})
    if ls.get("status") == "OK":
        lines.append(f"\nLIVE CONTRACT SPREAD:")
        lines.append(f"  contract:       {ls.get('contract')}")
        lines.append(f"  bid:            {ls.get('bid')}")
        lines.append(f"  ask:            {ls.get('ask')}")
        lines.append(f"  spread_pct:     {ls.get('spread_pct')}%")
        lines.append(f"  spread_quality: {ls.get('spread_quality')}")
        lines.append(f"  delta:          {ls.get('delta')}")
        lines.append(f"  iv:             {ls.get('iv')}")

    # Peer confirmation
    pc = live_data.get("peer_confirmation", {})
    if pc.get("status") == "OK":
        lines.append(f"\nSECTOR PEER CONFIRMATION:")
        lines.append(f"  verdict:        {pc.get('alignment_verdict')}")
        lines.append(f"  peers_down:     {pc.get('peers_down')} / {len(pc.get('peer_quotes',[]))}")
        lines.append(f"  peers_up:       {pc.get('peers_up')} / {len(pc.get('peer_quotes',[]))}")
        for q in pc.get("peer_quotes", []):
            lines.append(
                f"    {q.get('ticker'):<6} "
                f"${q.get('price')}  "
                f"{q.get('change_pct'):+.2f}%  "
                f"{q.get('direction')}"
            )

    return "\n".join(lines)



# ── Batch fetch for morning validator ─────────────────────────────────────────

def fetch_all_live_data_for_candidates(
    candidates: list,
    write_path: "Path | str" = None,
    contract_field: str = "selected_contract",   # field in candidate row with contract ticker
    direction_field: str = "direction",
    expiry_field: str = "expiry",
) -> dict:
    """
    Fetch all four live data points for every candidate in the morning validation list.

    Called by morning_thesis_validator.py --live after the existing price fetch loop:

        from live_market_reader import fetch_all_live_data_for_candidates
        live_data = fetch_all_live_data_for_candidates(
            candidates   = morning_candidates,
            write_path   = run_dir / "morning_validation" / f"morning_live_data_{run_id}.json",
        )

    Args:
        candidates:     list of dicts — each must have a "ticker" key.
                        Optionally has "selected_contract", "direction", "expiry".
        write_path:     if supplied, writes consolidated JSON here.
                        prepare_interpreter_session.py --morning then splits
                        this into per-ticker files in MA_Inputs/options_data/.
        contract_field: field name in candidate row containing the contract ticker
                        (e.g. "WFC260618P00072500"). Used for live spread fetch.
        direction_field: field name containing "call" or "put".
        expiry_field:   field name containing the expiry date string.

    Returns:
        dict: { ticker: live_data_dict, ... }
              Top-level key "candidates" maps to this dict for prepare_interpreter_session.py.
    """
    if not candidates:
        return {}

    result = {}
    total  = len(candidates)
    print(f"\n  [LIVE MARKET READER] Fetching live data for {total} candidate(s)...")

    for i, row in enumerate(candidates, 1):
        ticker   = str(row.get("ticker") or row.get("underlying") or "").strip().upper()
        if not ticker:
            continue

        contract = str(row.get(contract_field) or "").strip() or None
        direction= str(row.get(direction_field) or "").strip().lower() or None
        expiry   = str(row.get(expiry_field) or "").strip() or None

        # Normalise direction to "call" / "put"
        if direction in ("long_call", "call", "buy_setup"):
            direction = "call"
        elif direction in ("long_put", "put", "sell_setup"):
            direction = "put"
        else:
            direction = None

        print(f"  [{i}/{total}] {ticker}", end="")
        if contract: print(f" contract={contract}", end="")
        print()

        try:
            data = fetch_all_live_data(
                ticker          = ticker,
                contract_ticker = contract,
                expiry          = expiry,
                direction       = direction,
                write_to_ma_inputs = False,  # batch write below, not individual files
            )
            result[ticker] = data
        except Exception as e:
            print(f"  ⚠  Error fetching {ticker}: {e}")
            result[ticker] = {"status": "ERROR", "ticker": ticker, "error": str(e)}

        # Polygon rate limit — 12 req/min on free, 100/min on starter
        # Four calls per ticker at ~0.3s gap = ~1.2s per ticker
        # For 20 candidates = ~24s total — acceptable for morning window
        time.sleep(0.2)

    # Write consolidated JSON
    if write_path:
        write_path = Path(write_path)
        write_path.parent.mkdir(parents=True, exist_ok=True)
        import json as _json
        payload = {
            "run_context":  "morning_thesis_validator",
            "fetched_at":   datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "candidate_count": len(result),
            "candidates":   result,
        }
        write_path.write_text(_json.dumps(payload, indent=2), encoding="utf-8")
        size_kb = write_path.stat().st_size // 1024
        print(f"\n  ✅ Live data written: {write_path.name} ({size_kb} KB, {len(result)} tickers)")

    print(f"  [LIVE MARKET READER] Complete — {len(result)} tickers fetched")
    return result

# ── CLI helper — run directly to test ────────────────────────────────────────

if __name__ == "__main__":
    import sys
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "WFC"
    contract = sys.argv[2] if len(sys.argv) > 2 else None
    data = fetch_all_live_data(ticker, contract_ticker=contract)
    print("\n" + "=" * 60)
    print(format_live_data_for_prompt(data))
