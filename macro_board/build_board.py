"""Build the standalone ETF macro board.

    venv\\Scripts\\python.exe -m macro_board [--as-of YYYY-MM-DD] [--open]

Reads AVSHUNTER stores read-only and writes only under macro_board/output:
  etf_macro_board.html          latest board (self-contained, open in any browser)
  snapshots/board_<session>.json  the evening build's leans: the scored record
  snapshots/board_<session>_<kind>.json  morning / intraday / off-session builds, kept, never scored

Build kind (ACK 8 Oct 2026): Run-MacroInputs.ps1 sets AVSH_RUN_SESSION (PreOpen -> MORNING,
PostClose -> EVENING); a manual build is labelled from the XNYS calendar and the clock. A
pre-open build shows the same closing session as the evening before, so it must never
overwrite the evening record.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import sys
import time
import webbrowser

import numpy as np
import pandas as pd

from . import BOARD_VERSION
from . import conditions as cond
from . import decision_points as dpts
from . import decision as dec
from . import desk_card as desk
from . import momentum as mom
from . import evidence as ev
from . import holdings as hold
from . import market_prices as mkt
from . import opportunity as opty
from . import options as opt
from . import measured_sheet as msheet
from . import money_index as mindex
from . import review as rvw
from . import session_plan as splan
from . import rotation as rot
from . import tastytrade_metrics as ttm
from . import scorecard as sc
from . import sources as src

PACKAGE = Path(__file__).resolve().parent
DEFAULT_CONFIG = PACKAGE / "config" / "macro_board_config_v1.json"
OUTPUT_DIR = PACKAGE / "output"
TEMPLATE = PACKAGE / "board_template.html"
ALWAYS_LOAD = ("SPY", "HYG", "LQD", "USO")


def _clean(value):
    """JSON-safe: NaN/inf -> None, numpy scalars -> python."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else round(float(value), 6)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def build_kind(now: datetime, run_session: str | None) -> tuple[str, str]:
    """(MORNING | INTRADAY | EVENING | OFF_SESSION, runner | clock). The runner's session wins;
    otherwise the XNYS calendar decides (before the open, during regular hours, after the close,
    half days included)."""
    session = (run_session or "").strip().lower()
    if session == "preopen":
        return "MORNING", "runner"
    if session == "postclose":
        return "EVENING", "runner"
    from zoneinfo import ZoneInfo
    from avshunter.shared.xnys_calendar import is_xnys_session, session_bounds
    day = now.astimezone(ZoneInfo("America/New_York")).date()
    if not is_xnys_session(day):
        return "OFF_SESSION", "clock"
    open_utc, close_utc = session_bounds(day)
    if now < open_utc:
        return "MORNING", "clock"
    return ("INTRADAY", "clock") if now < close_utc else ("EVENING", "clock")


def snapshot_name(session: str, kind: str) -> str:
    """Only the evening build writes the scored record; other builds are kept beside it."""
    return f"board_{session}.json" if kind == "EVENING" else f"board_{session}_{kind.lower()}.json"


def build_overnight(external: dict) -> dict:
    """The overnight capture (market intelligence L-06) as measured; display only."""
    read = external.get("overnight")
    if read is None or read.status in ("MISSING", "UNREADABLE") or not isinstance(read.data, dict):
        return {"status": "UNREADABLE" if read is not None and read.status == "UNREADABLE" else "MISSING"}
    doc = read.data
    keys = ("run_session", "us_reference_session", "us_reference_close_utc", "us_reference_source",
            "stale_after_minutes", "groups", "summary", "releases_today", "releases_ahead", "notes", "errors")
    return {"status": read.status, "as_of": read.as_of,
            "age_hours": None if read.age_hours is None else round(read.age_hours, 1),
            **{k: doc.get(k) for k in keys}}


def etf_metrics(ticker: str, closes: pd.DataFrame, volumes: pd.DataFrame, sessions: pd.DatetimeIndex,
                max_age_sessions: int, spark_sessions: int) -> dict:
    if ticker not in closes.columns or closes[ticker].dropna().empty:
        return {"status": "MISSING", "history_sessions": 0}
    c = closes[ticker].dropna()
    last_date = c.index[-1]
    behind = int(len(sessions) - 1 - sessions.get_loc(last_date))

    def ret(n):
        return float(c.iloc[-1] / c.iloc[-1 - n] - 1.0) * 100.0 if len(c) > n else None

    def sma_gap(n):
        return float(c.iloc[-1] / c.iloc[-n:].mean() - 1.0) * 100.0 if len(c) >= n else None

    log_returns = np.log(c).diff().dropna()
    rv20 = float(log_returns.iloc[-20:].std(ddof=1) * np.sqrt(252) * 100.0) if len(log_returns) >= 20 else None
    spy = closes["SPY"].dropna()
    rs20 = None
    if len(c) > 20 and len(spy) > 20:
        rs20 = (ret(20) or 0.0) - float(spy.iloc[-1] / spy.iloc[-21] - 1.0) * 100.0
    high = c.iloc[-252:].max()
    spark = c.iloc[-spark_sessions:]
    volume = volumes[ticker].dropna() if ticker in volumes.columns else pd.Series(dtype=float)
    return {
        "status": "FRESH" if behind <= max_age_sessions else "STALE",
        "last_session": str(last_date.date()), "sessions_behind": behind, "history_sessions": int(len(c)),
        "close": float(c.iloc[-1]), "ret_1d": ret(1), "ret_5d": ret(5), "ret_20d": ret(20), "ret_60d": ret(60),
        "vs_sma50": sma_gap(50), "vs_sma200": sma_gap(200), "rv20": rv20, "rs_vs_spy_20d": rs20,
        "from_252_high": float(c.iloc[-1] / high - 1.0) * 100.0,
        "avg_dollar_volume_20d_m": float((volume.iloc[-20:] * c.reindex(volume.index).iloc[-20:]).mean() / 1e6)
        if len(volume) >= 20 else None,
        "spark": [round(float(x), 4) for x in spark.to_numpy()],
    }


def recent_changes(states: pd.DataFrame, lookback: int) -> list[dict]:
    """Conditions whose state changed within the last ``lookback`` sessions."""
    changes = []
    window = states.iloc[-(lookback + 1):]
    for key in states.columns:
        column = window[key]
        for i in range(1, len(column)):
            if column.iloc[i] != column.iloc[i - 1]:
                changes.append({"condition": key, "session": str(column.index[i].date()),
                                "from": column.iloc[i - 1], "to": column.iloc[i]})
    return sorted(changes, key=lambda item: item["session"], reverse=True)


def analog_episodes(mask: pd.Series, opens: pd.DataFrame, closes: pd.DataFrame, tickers, horizon: int,
                    limit: int) -> list[dict]:
    """Most recent independent analog episodes with what the focus ETFs did next."""
    positions = np.flatnonzero(mask.to_numpy())
    episodes, last = [], None
    for position in positions:
        if last is None or position - last >= horizon:
            episodes.append(int(position))
            last = position
    fwd = ev.forward_returns(opens, closes, horizon)
    rows = []
    for position in episodes[-limit:][::-1]:
        session = mask.index[position]
        rows.append({"session": str(session.date()),
                     "forward": {t: (None if t not in fwd.columns or pd.isna(fwd[t].iloc[position])
                                     else round(float(fwd[t].iloc[position]) * 100.0, 3)) for t in tickers}})
    return rows


def build(config_path: Path = DEFAULT_CONFIG, as_of: str | None = None, output_dir: Path = OUTPUT_DIR,
          refresh: bool = False) -> Path:
    started = time.time()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    run_session = os.environ.get("AVSH_RUN_SESSION", "")
    kind, kind_source = build_kind(now, run_session)
    print(f"[board] build kind: {kind} ({kind_source}{', ' + run_session if run_session else ''})")
    holdings_cfg, tasty_cfg = config["holdings"], config["tastytrade"]
    holdings_dir, tasty_dir = src.resolve(holdings_cfg["dir"]), src.resolve(tasty_cfg["dir"])
    refresh_report = {}
    if refresh and not as_of:
        refresh_report["holdings"] = hold.refresh(holdings_cfg["sources"], holdings_dir)
        universe_all = [t for group in config["universe"] for t in group["tickers"]]
        refresh_report["tastytrade"] = ttm.fetch(universe_all, tasty_dir)
        print(f"[board] refresh: {refresh_report}")
    sources_cfg, evidence_cfg = config["sources"], config["evidence"]
    horizons = [int(h) for h in config["horizons_sessions"]]
    groups = config["universe"]
    universe = [t for group in groups for t in group["tickers"]]
    load = sorted(set(universe) | set(ALWAYS_LOAD))

    price_db = src.resolve(sources_cfg["price_db"])
    opens, closes, volumes = src.load_prices(price_db, load, config["history_start"])
    highs, lows = src.load_ranges(price_db, load, config["history_start"])
    store_last = closes["SPY"].dropna().index[-1]
    prices_info, grouped = {"store_last_session": str(store_last.date()), "fill": None}, {}
    if not as_of:
        prices_cfg = config["prices"]
        last_completed = mkt.last_eligible_session(now, settle_minutes=float(prices_cfg["settle_minutes"]))
        grouped_dir = output_dir / "cache" / "grouped"
        plan, too_long = mkt.plan_fill(closes, load, last_completed=last_completed,
                                       max_gap_sessions=int(prices_cfg["max_gap_sessions"]),
                                       cached_sessions=mkt.cached_sessions(grouped_dir))
        offline = lambda url, params: (599, {})
        for day in plan:
            grouped[day] = mkt.fetch_grouped_daily(day, cache_dir=grouped_dir,
                                                   transport=None if refresh else offline)
        filled, report = mkt.apply_fill({"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
                                        grouped, plan)
        opens, highs, lows, closes, volumes = (filled[k] for k in ("open", "high", "low", "close", "volume"))
        report["gap_too_long"] = too_long
        prices_info.update({"last_completed_session": str(last_completed), "fill": report,
                            "settle_minutes": prices_cfg["settle_minutes"],
                            "grouped_sessions": [str(d) for d, bars in grouped.items() if bars]})
        if plan:
            print(f"[board] price fill: {len(plan)} session(s) planned, filled {len(report['filled'])} tickers, "
                  f"unavailable {len(report['unavailable'])}")
    sessions = closes["SPY"].dropna().index
    if as_of:
        sessions = sessions[sessions <= pd.Timestamp(as_of)]
    opens, closes, volumes, highs, lows = (frame.reindex(sessions) for frame in (opens, closes, volumes, highs, lows))
    print(f"[board] prices: {len(load)} tickers, {len(sessions)} sessions to {sessions[-1].date()} "
          f"(store to {store_last.date()})")

    panel = src.load_breadth_panel(price_db, config["history_start"], sessions, output_dir / "cache",
                                   grouped={d: b for d, b in grouped.items() if b})
    fred = src.load_fred(src.resolve(sources_cfg["fred_master"]))
    c12 = src.load_c12_settings(src.resolve(sources_cfg["c12_registry_dir"]), sessions[-1])
    states, values = cond.build_condition_frame(sessions=sessions, closes=closes, breadth_panel=panel,
                                                fred=fred, c12=c12, config=config)
    current = {key: str(states[key].iloc[-1]) for key in states.columns}
    print(f"[board] conditions today: {current}")

    observations = cond.current_observations(session=sessions[-1], sessions=sessions, closes=closes, fred=fred,
                                             config=config)

    tickers = [t for t in universe if t in closes.columns]
    path_cfg = config["path_dependent"]
    path_dependent = {t: [int(h) for h in path_cfg["lean_horizons_allowed"]]
                      for g in groups if g["group"] in path_cfg["groups"] for t in g["tickers"]}
    evidence = ev.build_evidence(opens=opens, closes=closes, states=states, current=current, tickers=tickers,
                                 horizons=horizons, settings=evidence_cfg, path_dependent=path_dependent)
    mask = evidence.pop("mask")

    spark_n = int(config["board_history_display_sessions"])
    metrics = {t: etf_metrics(t, closes, volumes, sessions, int(config["freshness"]["price_max_age_sessions"]), spark_n)
               for t in universe}
    decision_aids = build_decision_aids(metrics, evidence["per_ticker"], horizons, config)
    latest = build_latest(metrics, universe, config, now, refresh=refresh, as_of=as_of)
    fwd_by_h = {h: ev.forward_returns(opens, closes, h) for h in horizons}
    momentum_payload = {}
    for t in tickers:
        momentum_payload[t] = mom.momentum_block(closes[t], {h: fwd_by_h[h][t] for h in horizons}, evidence_cfg,
                                                 config["momentum"])
    print(f"[board] momentum evidence: {sum(1 for v in momentum_payload.values() if v.get('status') == 'OK')} ETFs")

    options_cfg = config["options"]
    implied = opt.load_implied_moves(src.resolve(options_cfg["chain_db"]), tickers, str(sessions[-1].date()),
                                     sessions, options_cfg["target_dte_calendar"])
    for ticker, block in implied.items():
        block["status"] = "FRESH" if block["sessions_old"] <= int(options_cfg["max_quote_age_sessions"]) else "STALE"
        for h, move in block["moves"].items():
            analog = (((evidence["per_ticker"].get(ticker) or {}).get("evidence") or {}).get(h) or {}).get("analog") or {}
            history_abs = analog.get("mean_abs_pct")
            if move and history_abs:
                move["analog_mean_abs_pct"] = history_abs
                move["priced_vs_history"] = round(move["implied_move_horizon_pct"] / history_abs, 3)
    print(f"[board] option chains: {len(implied)} ETFs")

    holdings_payload = build_holdings(holdings_dir, holdings_cfg, price_db, sessions, metrics, horizons)
    tasty = ttm.load_latest(tasty_dir, now, float(tasty_cfg["max_age_hours"]))
    factor = float(tasty_cfg["mean_abs_factor"])
    for ticker, m in tasty["metrics"].items():
        iv = m.get("iv_index_pct")
        m["iv_expected_abs_move_pct"] = ({str(h): round(iv * math.sqrt(h / 252.0) * factor, 4) for h in horizons}
                                         if iv is not None else None)
    print(f"[board] holdings: {list(holdings_payload)} · tastytrade metrics: {tasty['status']} ({len(tasty['metrics'])})")


    pipe_cfg = config["pipeline"]
    proposals = src.load_pipeline_proposals(src.resolve(pipe_cfg["runs_dir"]), pipe_cfg["file"], pipe_cfg["columns"], universe)
    for ticker, row in proposals["rows"].items():
        num = lambda k: row.get(k) if isinstance(row.get(k), (int, float)) and math.isfinite(row.get(k)) else None
        row["remaining"] = dec.remaining_opportunity(close=metrics.get(ticker, {}).get("close"), entry=num("entry_spot"),
                                                     target=num("target_spot"), invalidation=num("invalidation_spot"),
                                                     direction=row.get("canonical_direction"))

    external = src.load_external(config, now)
    packet = external["macro_packet"].data if external["macro_packet"].status != "MISSING" else None
    rotation_payload = build_rotation(opens=opens, closes=closes, states=states, current=current, mask=mask,
                                      sessions=sessions, config=config, horizons=horizons, metrics=metrics,
                                      holdings_payload=holdings_payload, packet=packet,
                                      packets=sc.load_archive_packets(src.resolve(sources_cfg["macro_archive_dir"])))
    print(f"[board] rotation: {len(rotation_payload['rows'])} ETFs")

    score_cfg = config["scorecard"]
    score_tickers = [t for t in score_cfg["score_tickers"] if t in closes.columns]
    packets = sc.load_archive_packets(src.resolve(sources_cfg["macro_archive_dir"]))
    snapshot_dir = output_dir / "snapshots"
    scorecards = {
        "regime_model": sc.score_regime_model(src.resolve(sources_cfg["daily_regime_model"]), opens, closes,
                                              score_tickers, horizons),
        "packets": sc.score_packets(packets, opens, closes, score_tickers, horizons, score_cfg),
        "board": sc.score_board_snapshots(snapshot_dir, opens, closes, horizons),
        "money_index": sc.score_money_index(external["us_money_index"].data if external["us_money_index"].status
                                            not in ("MISSING", "UNREADABLE") else None,
                                            opens, closes, score_tickers, horizons, score_cfg),
    }

    condition_meta = [{"key": d.key, "label": d.label, "measured": d.measured, "source": d.source,
                       "states": list(d.states)} for d in cond.CONDITION_DEFS]
    history = states.iloc[-spark_n:]
    value_history = values.iloc[-spark_n:]
    fred_last = {name: (str(fred[name].dropna().index[-1].date()) if name in fred.columns and fred[name].notna().any()
                        else None) for name in ("WALCL", "WTREGEN", "RRPONTSYD", "SPREAD_2Y10Y", "DGS10", "DEXUSEU")}

    payload = {
        "board_version": BOARD_VERSION,
        "config_version": config["config_version"],
        "authority": config["authority"],
        "built_at_utc": now.isoformat(timespec="seconds"),
        "as_of_session": str(sessions[-1].date()),
        "prices": prices_info,
        "build": {"kind": kind, "source": kind_source, "run_session": run_session or None,
                  "snapshot": None if as_of else snapshot_name(str(sessions[-1].date()), kind),
                  "scored_record": kind == "EVENING" and not as_of},
        "horizons": horizons,
        "focus": config["focus_tickers"],
        "groups": groups,
        "conditions": {"meta": condition_meta, "current": current,
                       "current_values": {k: values[k].iloc[-1] for k in values.columns},
                       "history_sessions": [str(d.date()) for d in history.index],
                       "history_states": {k: list(history[k]) for k in history.columns},
                       "history_values": {k: list(value_history[k]) for k in value_history.columns},
                       "changes": recent_changes(states, 10), "fred_last_observation": fred_last,
                       "observations": observations},
        "analogs": {"count": evidence["analog_sessions"], "match_level": evidence["match_level"],
                    "ladder": evidence["ladder"], "dimensions": sum(1 for v in current.values() if v != cond.MISSING),
                    "episodes": analog_episodes(mask, opens, closes, config["focus_tickers"], max(horizons), 10)},
        "etfs": {t: {"metrics": metrics[t], **evidence["per_ticker"].get(t, {}), "decision": decision_aids.get(t, {}),
                     "options": implied.get(t), "pipeline": proposals["rows"].get(t),
                     "tastytrade": tasty["metrics"].get(t), "holdings": holdings_payload.get(t),
                     "momentum": momentum_payload.get(t),
                     "path_dependent": t in path_dependent} for t in universe},
        "pipeline": {k: v for k, v in proposals.items() if k != "rows"},
        "tastytrade": {k: v for k, v in tasty.items() if k != "metrics"},
        "rotation": rotation_payload,
        "holdings_status": {etf: {k: v for k, v in block.items() if k in ("status", "as_of", "sessions_old", "issuer", "count")}
                            for etf, block in holdings_payload.items()},
        "refresh_report": refresh_report,
        "external": {name: read.public() for name, read in external.items()},
        "intel": build_intel(external, packet),
        "overnight": build_overnight(external),
        "latest": latest,
        "review": None,
        "decision_points": None,
        "opportunity": opty.build(metrics=metrics, closes=closes, holdings=holdings_payload, horizons=horizons,
                                  sectors=[t for t in config["rotation"]["sectors"] if t in metrics],
                                  gex_records=src.records(external["gex"].data) if external["gex"].status
                                  not in ("MISSING", "UNREADABLE") else [],
                                  proposals=proposals["rows"],
                                  room_tickers=list(dict.fromkeys(list(config["focus_tickers"]) + list(config["rotation"]["sectors"]))),
                                  cfg=config["opportunity"], highs=highs, lows=lows, latest=latest["rows"]),
        "scorecards": scorecards,
        "settings": {"evidence": evidence_cfg, "conditions": config["conditions"], "extension": config["extension"],
                     "response": config["response"], "options": options_cfg, "path_dependent": path_cfg,
                     "holdings": {k: v for k, v in holdings_cfg.items() if k != "sources"}, "tastytrade": tasty_cfg,
                     "momentum": config["momentum"], "desk_card": config["desk_card"],
                     "decision_points": {k: v for k, v in config["decision_points"].items() if k != "fomc"},
                     "opportunity": config["opportunity"], "review": config["review"],
                     "session_plan": config["session_plan"], "money_index": config["money_index"],
                     "measured_sheet": {k: v for k, v in config["measured_sheet"].items() if k != "rationale"},
                     "fred_publication_lag_days": config["fred_publication_lag_days"],
                     "fred_release_calendar": config["fred_release_calendar"],
                     "c12": {"trend": [c12.trend_short_sessions, c12.trend_long_sessions],
                             "vol_sessions": c12.vol_sessions, "vol_bands": list(c12.vol_state_bands),
                             "breadth_sessions": c12.breadth_sessions, "breadth_bands": list(c12.breadth_state_bands)}},
        "price_universe_in_breadth": int(panel.shape[1]),
    }
    payload["review"] = build_review(payload, config, opens, closes, holdings_payload, external)
    payload["decision_points"] = build_decision_points(payload, config, holdings_payload, external, sessions,
                                                       output_dir, refresh=refresh, as_of=as_of)
    payload["desk_cards"] = build_desk_cards(payload, config)
    payload["money_index"] = build_money_index(payload, config, values=values, fred=fred, sessions=sessions,
                                               opens=opens, closes=closes, tickers=tickers)
    payload.update(build_plan_inputs(payload, config, opens=opens, closes=closes, highs=highs, lows=lows, metrics=metrics,
                                     proposals=proposals["rows"], external=external, latest=latest, sessions=sessions,
                                     price_db=price_db, universe=universe))
    payload["session_plan"] = splan.build(payload, config["session_plan"])
    payload["measured_sheet"] = write_measured_sheet(payload, config, output_dir, kind=kind, as_of=as_of)
    print(f"[board] next session plan: {payload['session_plan']['call']['key']}, "
          f"agreement {payload['session_plan']['jigsaw']['agreement']['all']}")
    payload = _clean(payload)

    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    fresh = [t for t in universe if payload["etfs"][t]["metrics"].get("status") == "FRESH"]
    leans = {t: {h: e["lean"] for h, e in payload["etfs"][t].get("evidence", {}).items()} for t in fresh}
    baseline = {t: {h: e.get("baseline_lean") for h, e in payload["etfs"][t].get("evidence", {}).items()} for t in fresh}
    snapshot = {"board_version": BOARD_VERSION, "config_version": config["config_version"],
                "as_of_session": payload["as_of_session"], "built_at_utc": payload["built_at_utc"],
                "build_kind": kind, "build_kind_source": kind_source,
                "conditions": current, "leans": leans, "baseline_leans": baseline,
                "overnight": {k: payload["overnight"].get(k) for k in ("status", "as_of", "run_session", "summary")}}
    if not as_of and config.get("archive_inputs"):
        files = {name: read.file for name, read in external.items()}
        files.update({f"holdings_{etf}": holdings_dir / f"{etf}_latest.json" for etf in holdings_cfg["sources"]})
        if tasty.get("file"):
            files["tastytrade_metrics"] = tasty_dir / tasty["file"]
        earnings_file = (payload.get("decision_points") or {}).get("earnings_file")
        files["constituent_earnings"] = Path(earnings_file) if earnings_file else None
        files.update({"fred_master": src.resolve(sources_cfg["fred_master"]),
                      "pipeline_proposals": src.resolve(proposals["file"]) if proposals.get("file") else None})
        snapshot["inputs"] = src.archive_inputs(files, output_dir / "inputs")
        snapshot["price_store_fingerprint"] = src._store_fingerprint(price_db)
        archived = len([v for v in snapshot["inputs"].values() if v.get("sha256")])
        payload["inputs_archived"] = archived
        print(f"[board] archived {archived} input files")
    if not as_of:
        (snapshot_dir / snapshot_name(payload["as_of_session"], kind)).write_text(json.dumps(snapshot, indent=1), encoding="utf-8")

    html = TEMPLATE.read_text(encoding="utf-8")
    blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("/*__BOARD_PAYLOAD__*/null", blob)
    name = "etf_macro_board.html" if not as_of else f"etf_macro_board_asof_{as_of}.html"
    target = output_dir / name
    target.write_text(html, encoding="utf-8")
    print(f"[board] wrote {target} ({target.stat().st_size / 1024:.0f} KB) in {time.time() - started:.1f}s")
    return target


def build_latest(metrics: dict, universe, config: dict, now: datetime, *, refresh: bool, as_of: str | None) -> dict:
    """Latest price per ETF (ACK 9 Oct 2026: pre-market data supersedes the end of day). One Polygon
    snapshot on refresh builds; a quote after the board's close becomes the current price for room,
    levels and focus cards. The reaction review and the leans stay on completed sessions."""
    if as_of:
        return {"status": "NOT_APPLICABLE_AS_OF_BUILD", "fetched_utc": None, "rows": {}}
    if not refresh:
        return {"status": "NOT_REFRESHED", "fetched_utc": None, "rows": {}}
    closes = {t: (m["close"], m["last_session"]) for t, m in metrics.items()
              if m.get("status") != "MISSING" and m.get("close") is not None}
    snap = mkt.fetch_snapshot(list(closes))
    rows = mkt.latest_layer(snap["rows"], closes, now=now,
                            stale_after_minutes=float(config["prices"]["latest_stale_after_minutes"]))
    superseded = sum(1 for r in rows.values() if r["supersedes_close"])
    print(f"[board] latest prices: {snap['status']}, {len(snap['rows'])} quotes, {superseded} supersede the close")
    return {"status": snap["status"], "fetched_utc": now.isoformat(timespec="seconds"), "rows": rows,
            "superseding": superseded}


def build_review(payload: dict, config: dict, opens, closes, holdings_payload: dict, external: dict) -> dict:
    """Daily review section 1: what changed, what was expected, how markets reacted (accepted /
    rejected / absorbed, scored on what followed), what disagreed, what remains unresolved."""
    usable = lambda name: (external[name].data if name in external and external[name].status
                           not in ("MISSING", "UNREADABLE") else None)
    overnight = payload.get("overnight") or {}
    block = rvw.build(opens=opens, closes=closes, instruments=config["review"]["instruments"],
                      sectors=config["rotation"]["sectors"], focus=config["focus_tickers"], horizons=payload["horizons"],
                      evidence_settings=config["evidence"], holdings=holdings_payload,
                      event_payload=usable("event_payload"),
                      overnight=overnight if overnight.get("status") not in (None, "MISSING", "UNREADABLE") else None,
                      cfg=config["review"])
    block["sources"] = {"event_payload": external["event_payload"].public() if "event_payload" in external else None}
    print(f"[board] review: {block['headline']}")
    return block


def build_decision_points(payload: dict, config: dict, holdings_payload: dict, external: dict, sessions,
                          output_dir: Path, *, refresh: bool, as_of: str | None) -> dict:
    """Daily review section 2. Constituent earnings come from MarketData through the existing owner
    (canonical_data.marketdata_earnings, cached per session); only a refresh build calls the API,
    other builds use the cache and state the rest UNKNOWN. A back-dated build has no earnings."""
    cfg = config["decision_points"]
    sectors = [t for t in config["rotation"]["sectors"]]
    owners = dpts.constituent_tickers(holdings_payload, cfg, sectors)
    earnings, earnings_file = None, None
    if not as_of and owners:
        from canonical_data.marketdata_earnings import fetch_marketdata_earnings
        start = (sessions[-1] + timedelta(days=1)).date()
        cache = output_dir / "external" / "earnings"
        offline = lambda symbol, a, b: (599, {"s": "error", "errmsg": "NOT_REFRESHED"})
        earnings = fetch_marketdata_earnings(list(owners), as_of=start, cache_dir=cache,
                                             transport=None if refresh else offline)
        candidate = cache / f"{start.isoformat()}.json"
        earnings_file = str(candidate) if candidate.exists() else None
    usable = lambda name: (external[name].data if name in external and external[name].status
                           not in ("MISSING", "UNREADABLE") else None)
    overnight = payload.get("overnight") or {}
    block = dpts.build(as_of_session=payload["as_of_session"],
                       overnight=overnight if overnight.get("status") not in (None, "MISSING", "UNREADABLE") else None,
                       holdings=holdings_payload, earnings=earnings, enrichment=usable("enrichment"),
                       event_payload=usable("event_payload"), room=(payload.get("opportunity") or {}).get("room") or {},
                       focus=config["focus_tickers"], sectors=sectors, cfg=cfg, horizons=payload["horizons"])
    block["earnings_file"] = earnings_file
    block["sources"] = {"enrichment": external["enrichment"].public() if "enrichment" in external else None,
                        "event_payload": external["event_payload"].public() if "event_payload" in external else None}
    print(f"[board] decision points: {len(block['calendar'])} scheduled, "
          f"{len(block['unscheduled']['items'])} unscheduled, earnings unknown {len(block['coverage']['earnings_unknown'])}")
    return block


def write_measured_sheet(payload: dict, config: dict, output_dir: Path, *, kind: str, as_of: str | None) -> dict:
    """The measured sheet ACK pastes into ChatGPT (ACK 10 Oct 2026): measured facts + instructions, no LLM."""
    text = msheet.render(payload, config["measured_sheet"])
    files = []
    if not as_of:
        sheets = output_dir / "sheets"
        sheets.mkdir(parents=True, exist_ok=True)
        dated = sheets / f"measured_sheet_{payload['as_of_session']}_{kind.lower()}.md"
        latest = output_dir / "measured_sheet_latest.md"
        for target in (dated, latest):
            target.write_text(text, encoding="utf-8")
        files = [str(latest), str(dated)]
        print(f"[board] measured sheet for ChatGPT: {latest}")
    return {"text": text, "files": files}


def build_plan_inputs(payload: dict, config: dict, *, opens, closes, highs, lows, metrics, proposals, external, latest,
                      sessions, price_db, universe) -> dict:
    """Per-ETF inputs for the Next session plan (ACK 10 Oct 2026: the plan works per ETF with its correlation and
    reads the pipeline's candidates): each ETF's reaction and levels, and the pipeline's top candidates (read-only,
    ranked order) with their measured link to their sector ETF."""
    rcfg, pcfg = config["review"], config["session_plan"]
    reactions = {}
    for t in universe:
        if t not in closes.columns or closes[t].dropna().empty:
            continue
        c = closes[t].dropna()
        last = rvw.label_history(opens[t].reindex(c.index), c, k=float(rcfg["threshold_daily_moves"]),
                                 vol_sessions=int(rcfg["vol_sessions"])).iloc[-1]
        reactions[t] = {"key": last["key"], "close_pct": None if pd.isna(last["close_pct"]) else float(last["close_pct"]),
                        "session": str(c.index[-1].date())}
    gex = src.records(external["gex"].data) if external["gex"].status not in ("MISSING", "UNREADABLE") else []
    levels = opty.rooms(metrics=metrics, closes=closes, gex_records=gex, proposals=proposals, tickers=universe,
                        highs=highs, lows=lows, latest=latest["rows"])
    pipe = config["pipeline"]
    cands = src.load_pipeline_candidates(src.resolve(pipe["runs_dir"]), pipe["file"], pcfg["candidate_columns"],
                                         sides=pcfg["candidate_sides"], limit=int(pcfg["max_candidates"]))
    window = int(config["money_index"]["corr_window_sessions"])
    stocks = [r["ticker"] for r in cands["rows"] if r.get("ticker") and r["ticker"] not in closes.columns]
    stock_closes = pd.DataFrame()
    if stocks:
        start = str(sessions[max(0, len(sessions) - window - 30)].date())
        _, stock_closes, _ = src.load_prices(price_db, stocks, start)
    for r in cands["rows"]:
        t, etf = r.get("ticker"), r.get("sector_etf")
        series = closes[t] if t in closes.columns else (stock_closes[t] if t in stock_closes.columns else None)
        r["link"] = (mindex.beta_corr(series, closes[etf], window=window)
                     if series is not None and etf in closes.columns else {"beta": None, "corr": None, "n": 0})
    print(f"[board] plan inputs: {len(reactions)} ETF reactions, {len(levels)} ETF level maps, "
          f"{len(cands['rows'])} pipeline candidates ({cands.get('run_id')})")
    return {"etf_reactions": reactions, "etf_levels": levels, "pipeline_candidates": cands}


def build_money_index(payload: dict, config: dict, *, values, fred, sessions, opens, closes, tickers) -> dict:
    """The US Money Index risk-off score measured locally (ACK 10 Oct 2026), beside the published one."""
    cfg = config["money_index"]
    n = int(config["conditions"]["change_sessions"])

    def rel(a: str, b: str, sessions_back: int) -> pd.Series:
        if a not in closes.columns or b not in closes.columns:
            return pd.Series(np.nan, index=sessions)
        return np.log(closes[a] / closes[b]).diff(sessions_back) * 100.0

    raw = pd.DataFrame(index=sessions)
    raw["oil"] = values["oil"]
    raw["rates"] = values["yields"].diff(n) * 100.0
    raw["credit"] = values["credit"]
    raw["volatility"] = cond.fred_point_in_time(fred, "VIXCLS", "daily", sessions, config)
    raw["breadth"] = values["market_breadth"]
    raw["small_caps"] = rel("IWM", "SPY", n)
    raw["ai_semis"] = rel(cfg["ai_semis_ticker"], "SPY", int(cfg["ai_semis_sessions"]))
    u = (payload.get("intel") or {}).get("usmi") or {}
    published = {"score": u.get("score"),
                 "components": {c["name"]: c for c in u.get("components") or [] if isinstance(c, dict)}} if u else None
    block = mindex.build(raw=raw, opens=opens, closes=closes, tickers=tickers, published=published, cfg=cfg,
                         evidence_settings=config["evidence"], spark_sessions=int(config["board_history_display_sessions"]))
    r = block["reading"]
    print(f"[board] money index (measured): {r['score']} {r['band']} · published {block['comparison']['published_score']}"
          + (f" · missing {r['missing']}" if r["missing"] else ""))
    return block


def build_desk_cards(payload: dict, config: dict) -> dict:
    """Desk cards for pipeline candidates (CALL/PUT) and the focus ETFs, for every horizon."""
    cfg = config["desk_card"]
    labels = {m["key"]: m["label"] for m in payload["conditions"]["meta"]}
    candidates = [t for t, e in payload["etfs"].items()
                  if (e.get("pipeline") or {}).get("canonical_direction") in ("CALL", "PUT")]
    tickers = list(dict.fromkeys(list(config["focus_tickers"]) + candidates))
    cards = {}
    for t in tickers:
        etf = payload["etfs"].get(t)
        if not etf or (etf.get("metrics") or {}).get("status") == "MISSING":
            continue
        bucket = (etf.get("pipeline") or {}).get("horizon_bucket")
        cards[t] = {"default_horizon": cfg["pipeline_horizon_map"].get(bucket, cfg["default_horizon"]),
                    "by_horizon": {str(h): desk.build_card(t, etf, horizon=str(h), conditions=payload["conditions"],
                                                           intel=payload["intel"], external=payload["external"],
                                                           cfg=cfg, condition_labels=labels)
                                   for h in payload["horizons"]}}
    return cards


def build_rotation(*, opens, closes, states, current, mask, sessions, config, horizons, metrics, holdings_payload,
                   packet, packets) -> dict:
    """Sector rotation and the macro's measured impact on it (relative to SPY)."""
    cfg = config["rotation"]
    bench = cfg["benchmark"]
    sectors = [t for t in cfg["sectors"] if t in closes.columns]
    industries = [t for t in cfg["industries"] if t in closes.columns]
    names = sectors + industries
    coords = rot.rotation_coordinates(closes, names, bench, trend_sessions=int(cfg["trend_sessions"]),
                                      momentum_sessions=int(cfg["momentum_sessions"]))
    step, points = int(cfg["tail_step_sessions"]), int(cfg["tail_points"])
    sector_map_doc = json.loads(src.resolve(cfg["sector_map"]).read_text(encoding="utf-8"))
    etf_to_sector = sector_map_doc.get("etf_to_sector", {})
    name_to_etf = rot.sector_name_to_etf(etf_to_sector)

    rel_settings = {**config["evidence"], "lean_min_abs_mean_pct": cfg["relative_lean_min_abs_mean_pct"]}
    rel_fwd = {h: rot.relative_forward_returns(opens, closes, names, bench, h) for h in horizons}

    bias_map = ((packet or {}).get("sector_rotation") or {}).get("sector_bias_map") or {}
    packet_bias = {name_to_etf[k.strip().lower()]: v for k, v in bias_map.items() if k.strip().lower() in name_to_etf}

    def rel_return(ticker, n):
        c, b = closes[ticker].dropna(), closes[bench].dropna()
        if len(c) <= n or len(b) <= n:
            return None
        return float((c.iloc[-1] / c.iloc[-1 - n] - 1.0) - (b.iloc[-1] / b.iloc[-1 - n] - 1.0)) * 100.0

    rows = []
    for ticker in names:
        frame = coords.get(ticker)
        if frame is None or frame.dropna().empty:
            continue
        q_now = frame["quadrant"].iloc[-1]
        run = 0
        for value in reversed(frame["quadrant"].tolist()):
            if value != q_now:
                break
            run += 1
        tail_idx = list(range(len(frame) - 1, max(-1, len(frame) - 1 - step * points), -step))[::-1]
        tail = [{"session": str(frame.index[i].date()), "trend": frame["trend"].iloc[i], "momentum": frame["momentum"].iloc[i]}
                for i in tail_idx if np.isfinite(frame["trend"].iloc[i]) and np.isfinite(frame["momentum"].iloc[i])]
        evidence = {str(h): ev.ticker_evidence(rel_fwd[h][ticker], mask, h, rel_settings) for h in horizons}
        sensitivity = {str(h): ev.condition_sensitivity(rel_fwd[h][ticker], states, current, h) for h in horizons}
        bias = packet_bias.get(ticker)
        agreement = {}
        for h in horizons:
            lean = evidence[str(h)].get("lean")
            if bias in ("TAILWIND", "HEADWIND") and lean in ("UP", "DOWN"):
                agreement[str(h)] = "AGREES" if (bias == "TAILWIND") == (lean == "UP") else "DISAGREES"
            elif bias in ("TAILWIND", "HEADWIND"):
                agreement[str(h)] = "UNMEASURED"
            else:
                agreement[str(h)] = None
        hold_block = holdings_payload.get(ticker) or {}
        rows.append({
            "ticker": ticker, "kind": "sector" if ticker in sectors else "industry",
            "sector_name": etf_to_sector.get(ticker), "quadrant": q_now, "sessions_in_quadrant": run,
            "quadrant_5_ago": frame["quadrant"].iloc[-1 - step] if len(frame) > step else None,
            "trend": frame["trend"].iloc[-1], "momentum": frame["momentum"].iloc[-1], "tail": tail,
            "rel_5d": rel_return(ticker, 5), "rel_20d": rel_return(ticker, 20), "rel_60d": rel_return(ticker, 60),
            "participation_pct": ((hold_block.get("windows") or {}).get("20") or {}).get("participation_weight_pct"),
            "holdings_as_of": hold_block.get("as_of"),
            "top_contributors_20d": [r["ticker"] for r in (((hold_block.get("windows") or {}).get("20") or {}).get("top_contributors") or [])[:3]],
            "packet_bias": bias, "packet_agreement": agreement,
            "relative_evidence": evidence, "relative_sensitivity": sensitivity,
        })

    quadrant_series = {t: coords[t]["quadrant"] for t in sectors if t in coords}
    quadrant_evidence = {str(h): rot.quadrant_forward_evidence(quadrant_series, rel_fwd[h], h) for h in horizons}
    transitions = rot.transition_counts(quadrant_series, int(cfg["transition_step_sessions"]))

    score_cfg = config["scorecard"]
    by_entry = {}
    for item in packets:
        entry = sc.packet_entry_index(item["when"].to_pydatetime(), closes.index, score_cfg["us_regular_open_utc"])
        lead, lag = rot.etfs_for(item.get("leading"), name_to_etf), rot.etfs_for(item.get("lagging"), name_to_etf)
        if entry is not None and lead and lag:
            by_entry[entry] = (lead, lag, item["when"])
    calls = [(e, lead, lag) for e, (lead, lag, _) in sorted(by_entry.items())]
    lead_lag = {"calls": len(calls),
                "results": {str(h): rot.score_lead_lag(calls, opens, closes, bench, h) for h in horizons},
                "latest": [{"entry_session": str(closes.index[e].date()), "lead": lead, "lag": lag}
                           for e, (lead, lag, _) in sorted(by_entry.items())][-6:][::-1]}
    return {"settings": cfg, "rows": rows, "quadrant_evidence": quadrant_evidence, "transitions": transitions,
            "packet": {"strongest": ((packet or {}).get("sector_rotation") or {}).get("strongest_sectors"),
                       "weakest": ((packet or {}).get("sector_rotation") or {}).get("weakest_sectors"),
                       "signal": ((packet or {}).get("sector_rotation") or {}).get("rotation_signal"),
                       "bias": packet_bias},
            "lead_lag_scorecard": lead_lag}


def build_holdings(holdings_dir: Path, cfg: dict, price_db: Path, sessions: pd.DatetimeIndex, metrics: dict,
                   horizons) -> dict:
    """What each ETF's issuer-reported holdings did: weight x return per window, participation."""
    loaded = hold.load_latest(holdings_dir, list(cfg["sources"]))
    if not loaded:
        return {}
    tickers = sorted({h["ticker"] for record in loaded.values() for h in record["holdings"]})
    start = str(sessions[max(0, len(sessions) - 300)].date())
    _, closes, _ = src.load_prices(price_db, tickers, start)
    closes = closes.reindex(sessions[sessions >= pd.Timestamp(start)])
    own = {1: "ret_1d", 5: "ret_5d", 20: "ret_20d"}
    out = {}
    for etf, record in loaded.items():
        as_of = pd.Timestamp(record["as_of"]) if record.get("as_of") else None
        behind = None if as_of is None else int(((sessions > as_of) & (sessions <= sessions[-1])).sum())
        windows, table = {}, {}
        for h in horizons:
            result = hold.contribution(record["holdings"], closes, window=int(h), trend_sessions=int(cfg["participation_sessions"]),
                                       holdings_as_of=as_of)
            etf_return = (metrics.get(etf) or {}).get(own.get(int(h), ""))
            rows = result.pop("rows")
            windows[str(h)] = {**result, "etf_return_pct": etf_return,
                               "top_contributors": sorted(rows, key=lambda r: r["contribution_pp"], reverse=True)[:5],
                               "top_detractors": sorted(rows, key=lambda r: r["contribution_pp"])[:5]}
            for row in rows[: int(cfg["top_rows"])]:
                entry = table.setdefault(row["ticker"], {"ticker": row["ticker"], "name": row["name"], "weight_pct": row["weight_pct"]})
                entry[f"ret_{h}"] = row["return_pct"]
                entry[f"contrib_{h}"] = row["contribution_pp"]
        out[etf] = {"issuer": record.get("issuer"), "as_of": record.get("as_of"), "sessions_old": behind,
                    "status": "FRESH" if behind is not None and behind <= int(cfg["max_age_sessions"]) else "STALE",
                    "count": len(record["holdings"]), "fetched_utc": record.get("fetched_utc"),
                    "raw_sha256": record.get("raw_sha256"), "windows": windows,
                    "top": sorted(table.values(), key=lambda r: r["weight_pct"], reverse=True)}
    return out


def build_decision_aids(metrics: dict, per_ticker: dict, horizons, config: dict) -> dict:
    """Extension (move already made) and response label per ETF and horizon."""
    band = float(config["extension"]["band_sd"])
    t_min = float(config["response"]["t_min"])
    own = {1: "ret_1d", 5: "ret_5d", 20: "ret_20d"}
    out = {}
    for ticker, m in metrics.items():
        if m.get("status") == "MISSING":
            continue
        extension = {str(w): dec.extension_state(m.get(own.get(w, "")), m.get("rv20"), w, band)
                     for w in config["extension"]["windows_sessions"]}
        response = {}
        for h in horizons:
            sens = ((per_ticker.get(ticker) or {}).get("sensitivity") or {}).get(str(h)) or {}
            response[str(h)] = dec.classify_response(sens, m.get(own.get(h, "")), t_min)
        out[ticker] = {"extension": extension, "response": response}
    return out


def _dated(usmi: dict) -> list[dict]:
    """Observations inside the Money Index with their own dates (a packet date is not the
    date of every value it carries)."""
    cross = usmi.get("cross_asset") or {}
    eq, cr, vol, ff, rates = (cross.get(k) or {} for k in ("equities", "credit", "volatility", "fund_flows", "rates"))
    last_cash = eq.get("last_us_cash_session") or {}
    close_snaps = sorted(k for k in eq if k.startswith("cash_close_snapshot_"))
    credit_snaps = sorted(k for k in cr if k.startswith("latest_official_snapshot_"))
    credit_date = credit_snaps[-1].rsplit("_", 3)[-3:] if credit_snaps else None
    credit_date = "-".join(credit_date) if credit_date else None
    front = vol.get("front_vix_future") or {}
    rows = [
        ("S&P 500 % (last_us_cash_session object)", last_cash.get("sp500_pct"), last_cash.get("date")),
    ]
    if close_snaps:
        snap = eq.get(close_snaps[-1]) or {}
        day = "-".join(close_snaps[-1].rsplit("_", 3)[-3:])
        rows += [("S&P 500 % (cash close snapshot)", snap.get("sp500_pct"), day),
                 ("Nasdaq Composite % (not QQQ)", snap.get("nasdaq_composite_pct"), day)]
    rows += [
        ("HY OAS %", cr.get("hy_oas_pct"), credit_date),
        ("Single-B OAS %", cr.get("single_b_oas_pct"), credit_date),
        ("HYG close", cr.get("hyg_close"), cr.get("hyg_close_date")),
        ("VIX spot", vol.get("vix_spot"), vol.get("vix_date")),
        ("Front VIX future", front.get("value"), ("expiry " + str(front.get("expiry"))) if front.get("expiry") else None),
        ("US equity fund flows $bn", ff.get("us_equity_funds_usd_bn"), ("week to " + str(ff.get("week_ending"))) if ff.get("week_ending") else None),
        ("10Y %", rates.get("us_10y_pct"), None),
        ("October hike probability %", (cross.get("fed") or {}).get("october_hike_probability_pct"), None),
    ]
    return [{"metric": m, "value": v, "observed": d or "not dated in packet"} for m, v, d in rows if v is not None]


def build_intel(external: dict, packet: dict | None) -> dict:
    """Pick the human-relevant fields from each advisory source (display only)."""
    def data(name):
        read = external.get(name)
        return None if read is None or read.status in ("MISSING", "UNREADABLE") else read.data

    intel: dict = {}
    if packet:
        keys = ("regime_label", "regime_state", "regime_probability", "macro_conviction", "risk_on_off_switch",
                "dir_bias", "trend_energy", "vol_mode", "liquidity_pulse", "rates_impulse", "usd_state",
                "credit_state", "credit_risk_score", "sector_lead", "sector_avoid", "horizon_routing", "notes",
                "macro_authority", "conflict_flags", "rotation_override", "vix_spot", "net_liquidity_score",
                "vix_regime_score", "gex_regime_score", "macro_momentum_score", "macro_filter", "regime_drift_status")
        intel["packet"] = {k: packet.get(k) for k in keys}
        intel["packet"]["sector_rotation"] = packet.get("sector_rotation")
    usmi = data("us_money_index")
    if isinstance(usmi, dict):
        score = usmi.get("risk_off_transmission_score") or {}
        state = usmi.get("current_state") or {}
        components = score.get("components") or {}
        intel["usmi"] = {
            "state": state.get("US_MONEY_INDEX_STATE"), "summary": state.get("summary"),
            "confidence": state.get("state_confidence"), "transmission_state": state.get("risk_off_transmission_state"),
            "score": score.get("current_score"), "previous_score": score.get("previous_score"),
            "components": [{"name": k, "weight": v.get("weight"), "score": v.get("score"), "status": v.get("status")}
                           for k, v in components.items() if isinstance(v, dict)],
            "forward_triggers": usmi.get("forward_triggers"),
            "revision": usmi.get("packet_revision"),
            "execution_permission": usmi.get("execution_permission"),
            "method": score.get("method"), "ladder": score.get("ladder"),
            "dealer_gamma": (usmi.get("cross_asset") or {}).get("dealer_gamma_gex"),
            "dated": _dated(usmi),
        }
    events = data("event_payload")
    if isinstance(events, dict):
        intel["events"] = {
            "classification": (events.get("regime_summary") or {}).get("classification"),
            "narrative": (events.get("regime_summary") or {}).get("core_narrative"),
            "verdict": events.get("final_verdict"),
            "events": [{k: e.get(k) for k in ("event_name", "country_or_institution", "release_time_utc", "status",
                                                "actual", "forecast", "previous", "surprise_direction", "surprise_score",
                                                "expected_magnitude", "why_it_matters_to_us_markets")}
                       for e in events.get("events") or []][:8],
            "counter_case": (events.get("counter_case") or {}).get("summary"),
        }
    enrichment = data("enrichment")
    if isinstance(enrichment, dict):
        overlay = enrichment.get("narrative_overlay") or {}
        intel["enrichment"] = {"alert_level": overlay.get("alert_level"), "fragility_score": overlay.get("fragility_score"),
                               "summary": overlay.get("overlay_summary"), "batch_id": enrichment.get("batch_id")}
    bond = data("bond_state")
    if isinstance(bond, dict):
        intel["bond"] = {k: bond.get(k) for k in ("yield_curve", "zn_futures", "credit_stress", "composite", "auction")}
    for name in ("vix_engine", "gex", "liquidity_monitor", "macro_filter", "breadth_rsp_spy", "forward_bias",
                 "economic_prints", "threshold_flags"):
        frame = data(name)
        intel[name] = src.records(frame) if frame is not None else []
    regime = data("regime_model")
    intel["regime_model_latest"] = src.records(regime.tail(10)) if regime is not None else []
    return intel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the standalone ETF macro board (read-only).")
    parser.add_argument("--as-of", help="Rebuild the measured layers as of a past session (YYYY-MM-DD); no snapshot is written.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--open", action="store_true", help="Open the board in the default browser when done.")
    parser.add_argument("--refresh", action="store_true",
                        help="Download issuer holdings and fetch tastytrade metrics (read-only bridge) before building.")
    args = parser.parse_args(argv)
    target = build(args.config, args.as_of, refresh=args.refresh)
    if args.open:
        webbrowser.open(target.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
