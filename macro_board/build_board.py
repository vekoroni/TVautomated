"""Build the standalone ETF macro board.

    venv\\Scripts\\python.exe -m macro_board [--as-of YYYY-MM-DD] [--open]

Reads AVSHUNTER stores read-only and writes only under macro_board/output:
  etf_macro_board.html          latest board (self-contained, open in any browser)
  snapshots/board_<session>.json  the leans shown, so later builds can score them
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time
import webbrowser

import numpy as np
import pandas as pd

from . import BOARD_VERSION
from . import conditions as cond
from . import decision as dec
from . import evidence as ev
from . import holdings as hold
from . import options as opt
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
    sessions = closes["SPY"].dropna().index
    if as_of:
        sessions = sessions[sessions <= pd.Timestamp(as_of)]
    opens, closes, volumes = (frame.reindex(sessions) for frame in (opens, closes, volumes))
    print(f"[board] prices: {len(load)} tickers, {len(sessions)} sessions to {sessions[-1].date()}")

    panel = src.load_breadth_panel(price_db, config["history_start"], sessions, output_dir / "cache")
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
                     "path_dependent": t in path_dependent} for t in universe},
        "pipeline": {k: v for k, v in proposals.items() if k != "rows"},
        "tastytrade": {k: v for k, v in tasty.items() if k != "metrics"},
        "rotation": rotation_payload,
        "holdings_status": {etf: {k: v for k, v in block.items() if k in ("status", "as_of", "sessions_old", "issuer", "count")}
                            for etf, block in holdings_payload.items()},
        "refresh_report": refresh_report,
        "external": {name: read.public() for name, read in external.items()},
        "intel": build_intel(external, packet),
        "scorecards": scorecards,
        "settings": {"evidence": evidence_cfg, "conditions": config["conditions"], "extension": config["extension"],
                     "response": config["response"], "options": options_cfg, "path_dependent": path_cfg,
                     "holdings": {k: v for k, v in holdings_cfg.items() if k != "sources"}, "tastytrade": tasty_cfg,
                     "fred_publication_lag_days": config["fred_publication_lag_days"],
                     "c12": {"trend": [c12.trend_short_sessions, c12.trend_long_sessions],
                             "vol_sessions": c12.vol_sessions, "vol_bands": list(c12.vol_state_bands),
                             "breadth_sessions": c12.breadth_sessions, "breadth_bands": list(c12.breadth_state_bands)}},
        "price_universe_in_breadth": int(panel.shape[1]),
    }
    payload = _clean(payload)

    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    fresh = [t for t in universe if payload["etfs"][t]["metrics"].get("status") == "FRESH"]
    leans = {t: {h: e["lean"] for h, e in payload["etfs"][t].get("evidence", {}).items()} for t in fresh}
    baseline = {t: {h: e.get("baseline_lean") for h, e in payload["etfs"][t].get("evidence", {}).items()} for t in fresh}
    snapshot = {"board_version": BOARD_VERSION, "config_version": config["config_version"],
                "as_of_session": payload["as_of_session"], "built_at_utc": payload["built_at_utc"],
                "conditions": current, "leans": leans, "baseline_leans": baseline}
    if not as_of and config.get("archive_inputs"):
        files = {name: read.file for name, read in external.items()}
        files.update({f"holdings_{etf}": holdings_dir / f"{etf}_latest.json" for etf in holdings_cfg["sources"]})
        if tasty.get("file"):
            files["tastytrade_metrics"] = tasty_dir / tasty["file"]
        files.update({"fred_master": src.resolve(sources_cfg["fred_master"]),
                      "pipeline_proposals": src.resolve(proposals["file"]) if proposals.get("file") else None})
        snapshot["inputs"] = src.archive_inputs(files, output_dir / "inputs")
        snapshot["price_store_fingerprint"] = src._store_fingerprint(price_db)
        archived = len([v for v in snapshot["inputs"].values() if v.get("sha256")])
        payload["inputs_archived"] = archived
        print(f"[board] archived {archived} input files")
    if not as_of:
        (snapshot_dir / f"board_{payload['as_of_session']}.json").write_text(json.dumps(snapshot, indent=1), encoding="utf-8")

    html = TEMPLATE.read_text(encoding="utf-8")
    blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("/*__BOARD_PAYLOAD__*/null", blob)
    name = "etf_macro_board.html" if not as_of else f"etf_macro_board_asof_{as_of}.html"
    target = output_dir / name
    target.write_text(html, encoding="utf-8")
    print(f"[board] wrote {target} ({target.stat().st_size / 1024:.0f} KB) in {time.time() - started:.1f}s")
    return target


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
