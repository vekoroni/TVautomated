"""
Entry Timing Engine — pre-trade probability and timing layer.
Standalone module. No imports from any interpreter engine file.
Standard library only: math, csv, pathlib.
"""
import csv
import math
from pathlib import Path


# ---------------------------------------------------------------------------
# Function 1
# ---------------------------------------------------------------------------

def compute_first_passage_probability(
    current_price: float,
    trigger_level: float,
    kill_switch_level: float,
    dte: int,
    garch_daily_vol: float,
    direction: str,
) -> dict:
    distance_to_trigger = abs(current_price - trigger_level)
    distance_to_kill    = abs(current_price - kill_switch_level)

    sigma_window = garch_daily_vol * math.sqrt(max(dte, 0)) if garch_daily_vol > 0 else 0.0

    if distance_to_trigger <= 0:
        p_trigger = 0.95
    elif sigma_window > 0:
        p_trigger = min(max(math.exp(-2.0 * distance_to_trigger / sigma_window), 0.0), 0.95)
    else:
        p_trigger = 0.0

    if distance_to_kill <= 0:
        p_kill_first = 0.95
    elif sigma_window > 0:
        p_kill_first = min(max(math.exp(-2.0 * distance_to_kill / sigma_window), 0.0), 0.95)
    else:
        p_kill_first = 0.0

    # expected_entry_days: guard divide-by-zero
    denom = 2.0 * abs(distance_to_trigger) * garch_daily_vol
    if denom > 0 and sigma_window > 0:
        raw = (sigma_window ** 2) / denom
        expected_entry_days = min(max(raw, 0.5), float(dte) if dte > 0 else 0.5)
    elif distance_to_trigger <= 0:
        expected_entry_days = 0.5
    else:
        expected_entry_days = float(dte) if dte > 0 else 0.5

    if expected_entry_days <= 1.0:
        entry_edge_window = "TODAY"
    elif expected_entry_days <= 3.0:
        entry_edge_window = "1-3D"
    elif expected_entry_days <= 7.0:
        entry_edge_window = "3-7D"
    else:
        entry_edge_window = "UNLIKELY_IN_WINDOW"

    confidence_note = "GARCH-derived" if garch_daily_vol > 0 else "NO_GARCH_DATA — estimate only"

    return {
        "p_trigger":           round(p_trigger, 2),
        "p_kill_first":        round(p_kill_first, 2),
        "expected_entry_days": round(expected_entry_days, 1),
        "entry_edge_window":   entry_edge_window,
        "sigma_window":        round(sigma_window, 4),
        "confidence_note":     confidence_note,
    }


# ---------------------------------------------------------------------------
# Function 2
# ---------------------------------------------------------------------------

def estimate_crowd_arrival_window(
    ivp: float,
    options_flow_zscore: float,
    days_since_phase_signal: int,
    volume_vs_20d_avg: float,
) -> dict:
    freshness_score = 100.0

    if ivp >= 80:
        freshness_score -= 35
    elif ivp >= 60:
        freshness_score -= 20
    elif ivp >= 40:
        freshness_score -= 10
    elif ivp < 20:
        freshness_score += 10

    if options_flow_zscore >= 3.0:
        freshness_score -= 25
    elif options_flow_zscore >= 1.5:
        freshness_score -= 15
    elif options_flow_zscore >= 0.5:
        freshness_score -= 5
    elif options_flow_zscore < 0.0:
        freshness_score += 5

    if days_since_phase_signal >= 10:
        freshness_score -= 20
    elif days_since_phase_signal >= 5:
        freshness_score -= 10
    elif days_since_phase_signal <= 1:
        freshness_score += 10

    if volume_vs_20d_avg >= 2.5:
        freshness_score -= 20
    elif volume_vs_20d_avg >= 1.5:
        freshness_score -= 10
    elif volume_vs_20d_avg < 0.8:
        freshness_score += 5

    freshness_score = min(max(freshness_score, 0.0), 100.0)

    if freshness_score >= 75:
        crowd_stage = "PRE_CROWD"
        estimated_hours_remaining = "12-48h before institutional discovery"
        edge_quality = "MAXIMUM"
    elif freshness_score >= 50:
        crowd_stage = "EARLY_CROWD"
        estimated_hours_remaining = "4-12h before retail momentum arrival"
        edge_quality = "PRESENT"
    elif freshness_score >= 25:
        crowd_stage = "LATE_CROWD"
        estimated_hours_remaining = "0-4h — crowd arriving now"
        edge_quality = "COMPRESSED"
    else:
        crowd_stage = "CROWD_PASSED"
        estimated_hours_remaining = "Edge window likely closed"
        edge_quality = "DETERIORATED"

    return {
        "freshness_score":           round(freshness_score, 1),
        "crowd_stage":               crowd_stage,
        "estimated_hours_remaining": estimated_hours_remaining,
        "edge_quality":              edge_quality,
    }


# ---------------------------------------------------------------------------
# Function 3
# ---------------------------------------------------------------------------

def compute_kill_switch_breach_probability(
    current_price: float,
    kill_switch_level: float,
    dte_remaining: int,
    garch_daily_vol: float,
    direction: str,
) -> dict:
    distance_to_kill = abs(current_price - kill_switch_level)

    if garch_daily_vol > 0:
        vol_1d = garch_daily_vol * math.sqrt(1)
        vol_3d = garch_daily_vol * math.sqrt(3)
        p_breach_today = min(max(math.exp(-2.0 * distance_to_kill / vol_1d), 0.0), 0.99)
        p_breach_3d    = min(max(math.exp(-2.0 * distance_to_kill / vol_3d), 0.0), 0.99)
    else:
        p_breach_today = 0.0
        p_breach_3d    = 0.0

    if p_breach_today >= 0.50:
        warning_tier = "CRITICAL — breach likely today"
        note = "Kill switch is within today's expected volatility range — review position sizing before entry."
    elif p_breach_today >= 0.25:
        warning_tier = "RED — elevated breach risk"
        note = "Elevated probability of hitting the kill switch today — confirm the stop level is intentional."
    elif p_breach_3d >= 0.40:
        warning_tier = "AMBER — breach possible within 3 days"
        note = "Kill switch may be reached within 3 days based on current volatility — monitor closely."
    elif p_breach_3d >= 0.20:
        warning_tier = "YELLOW — monitor closely"
        note = "Non-trivial chance of kill switch breach within 3 days — watch price action relative to the stop."
    else:
        warning_tier = "GREEN — kill switch well protected"
        note = "Kill switch is well outside the near-term volatility range — stop protection is adequate."

    distance_pct = (distance_to_kill / current_price * 100) if current_price > 0 else 0.0

    return {
        "p_breach_today":        round(p_breach_today, 2),
        "p_breach_3d":           round(p_breach_3d, 2),
        "warning_tier":          warning_tier,
        "distance_to_kill_pct":  round(distance_pct, 2),
        "note":                  note,
    }


# ---------------------------------------------------------------------------
# Function 4
# ---------------------------------------------------------------------------

def build_pre_trade_probability_block(
    ticker: str,
    pipeline_row: dict,
    garch_row: dict,
    lab_row: dict,
    days_since_phase_signal: int,
) -> str:
    def _float(d, *keys):
        for k in keys:
            v = d.get(k, "")
            if v == "" or v is None:
                continue
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
        return None

    def _int(d, *keys):
        for k in keys:
            v = d.get(k, "")
            if v == "" or v is None:
                continue
            try:
                return int(float(v))
            except (TypeError, ValueError):
                continue
        return None

    current_price     = _float(pipeline_row, "current_price", "last_price", "close",
                                   "signal_price", "underlying_price", "scanner_price") or 0.0
    trigger_level     = _float(pipeline_row, "trigger_level", "armed_trigger", "probe_trigger",
                               "entry_trigger", "scenario_entry_trigger") or 0.0
    kill_switch_level = _float(pipeline_row, "kill_switch_level", "exit_stop_price",
                               "stop_price", "exit_stop", "invalidation_price") or 0.0
    dte               = _int(pipeline_row, "dte") or 10
    _ivp_raw          = _float(pipeline_row, "ivp", "iv_percentile", "iv_rank") or 50.0
    # Normalise: iv_percentile may be stored as 0-1 decimal (0.635) or 0-100 (63.5)
    ivp               = (_ivp_raw * 100.0) if _ivp_raw <= 1.1 else _ivp_raw
    volume_vs_20d     = _float(pipeline_row, "volume_vs_20d_avg", "vol_ratio") or 1.0
    options_flow_z    = _float(pipeline_row, "options_flow_zscore", "flow_zscore") or 0.0

    raw_dir = ""
    for k in ("direction", "canonical_direction", "resolved_direction"):
        v = pipeline_row.get(k, "")
        if v:
            raw_dir = str(v).upper()
            break
    if "PUT" in raw_dir:
        direction = "PUT"
    elif "CALL" in raw_dir:
        direction = "CALL"
    else:
        direction = "UNKNOWN"

    garch_daily_vol = _float(garch_row, "daily_vol", "garch_vol_1d", "vol_1d", "sigma_1d") or 0.0

    if garch_daily_vol == 0.0 and current_price > 0:
        garch_daily_vol = (0.20 + (ivp / 100.0) * 0.40) / (252 ** 0.5)

    crowd = estimate_crowd_arrival_window(
        ivp=ivp,
        options_flow_zscore=options_flow_z,
        days_since_phase_signal=days_since_phase_signal,
        volume_vs_20d_avg=volume_vs_20d,
    )

    trigger_ok = trigger_level > 0 and kill_switch_level > 0 and current_price > 0 and direction in ("CALL", "PUT")
    ks_ok      = kill_switch_level > 0 and current_price > 0

    if trigger_ok:
        fp = compute_first_passage_probability(
            current_price=current_price,
            trigger_level=trigger_level,
            kill_switch_level=kill_switch_level,
            dte=dte,
            garch_daily_vol=garch_daily_vol,
            direction=direction,
        )
    else:
        fp = None

    if ks_ok:
        ks = compute_kill_switch_breach_probability(
            current_price=current_price,
            kill_switch_level=kill_switch_level,
            dte_remaining=dte,
            garch_daily_vol=garch_daily_vol,
            direction=direction,
        )
    else:
        ks = None

    lines = [f"PRE_TRADE_PROBABILITY_{ticker.upper()}:"]
    lines.append(f"  crowd_stage:         {crowd['crowd_stage']}  |  freshness: {crowd['freshness_score']}/100")
    lines.append(f"  edge_quality:        {crowd['edge_quality']}")
    lines.append(f"  estimated_hours:     {crowd['estimated_hours_remaining']}")

    if fp:
        lines.append(f"  p_trigger_hit:       {fp['p_trigger']:.0%}  (within {dte}d DTE)")
        lines.append(f"  p_kill_first:        {fp['p_kill_first']:.0%}")
        lines.append(f"  entry_edge_window:   {fp['entry_edge_window']}")
    else:
        lines.append("  p_trigger_hit:       NOT_COMPUTED — trigger_level or kill_switch_level missing")

    if ks:
        lines.append(f"  kill_switch_warning: {ks['warning_tier']}")
        lines.append(f"  ks_breach_today:     {ks['p_breach_today']:.0%}")
        lines.append(f"  ks_breach_3d:        {ks['p_breach_3d']:.0%}")
        lines.append(f"  distance_to_ks:      {ks['distance_to_kill_pct']:.1f}% away")
    else:
        lines.append("  kill_switch_warning: NOT_COMPUTED — kill_switch_level missing")

    # Build data quality note distinguishing garch states
    if garch_row and any(garch_row.get(f, "") for f in ("daily_vol", "garch_vol_1d", "vol_1d", "sigma_1d")):
        _garch_status = "LIVE"
    elif garch_row == {}:
        _garch_status = "NOT_RUN"  # load_garch_rows returned empty dict for this ticker
    else:
        _garch_status = "PROPAGATION_GAP"  # row dict exists but vol fields absent/zero
    if fp:
        confidence = fp["confidence_note"]
    elif _garch_status == "LIVE":
        confidence = "GARCH-derived (vol present but trigger fields missing)"
    elif _garch_status == "PROPAGATION_GAP":
        confidence = "NO_GARCH_DATA[PROPAGATION_GAP] — vol estimate used"
    else:
        confidence = "NO_GARCH_DATA[NOT_RUN] — vol estimate used"
    lines.append(f"  data_quality:        {confidence}")
    lines.append(f"  garch_status:        {_garch_status}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Function 5
# ---------------------------------------------------------------------------

def load_garch_rows(ma_pipeline_dir: Path) -> dict:
    """Scan ma_pipeline_dir for garch_forecasts_*.csv, load most recent."""
    if not ma_pipeline_dir or not Path(ma_pipeline_dir).exists():
        return {}

    candidates = sorted(
        Path(ma_pipeline_dir).glob("garch_forecasts_*.csv"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return {}

    result = {}
    with open(candidates[0], newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = row.get("ticker") or row.get("underlying") or ""
            key = key.strip().upper()
            if key:
                result[key] = dict(row)
    return result


# ---------------------------------------------------------------------------
# Function 6  (GAP 3 fix)
# ---------------------------------------------------------------------------

def assess_garch_availability(ma_pipeline_dir: Path, ticker: str) -> dict:
    """
    Distinguish three GARCH states for a given ticker:
      NOT_RUN         — no garch_forecasts_*.csv file found in pipeline dir
      PROPAGATION_GAP — file found but ticker row is missing or has zero vol
      LIVE            — file found and ticker has a valid non-zero daily vol

    Returns dict: { status, daily_vol, note }
    """
    if not ma_pipeline_dir or not Path(ma_pipeline_dir).exists():
        return {"status": "NOT_RUN", "daily_vol": 0.0,
                "note": "GARCH dir not found — pipeline may not have run"}

    candidates = sorted(
        Path(ma_pipeline_dir).glob("garch_forecasts_*.csv"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return {"status": "NOT_RUN", "daily_vol": 0.0,
                "note": "No garch_forecasts_*.csv in pipeline outputs — GARCH engine did not run"}

    # File exists — check if this ticker's row is present and non-zero
    ticker_upper = str(ticker).strip().upper()
    try:
        with open(candidates[0], newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                key = (row.get("ticker") or row.get("underlying") or "").strip().upper()
                if key == ticker_upper:
                    for vol_field in ("daily_vol", "garch_vol_1d", "vol_1d", "sigma_1d"):
                        v = row.get(vol_field, "")
                        try:
                            dv = float(v)
                            if dv > 0:
                                return {"status": "LIVE", "daily_vol": dv,
                                        "note": f"GARCH vol loaded from {candidates[0].name}"}
                        except (TypeError, ValueError):
                            continue
                    return {"status": "PROPAGATION_GAP", "daily_vol": 0.0,
                            "note": f"Ticker {ticker_upper} in GARCH file but vol=0 — propagation gap"}
    except (OSError, csv.Error):
        pass

    return {"status": "PROPAGATION_GAP", "daily_vol": 0.0,
            "note": f"Ticker {ticker_upper} not found in GARCH file — propagation gap"}

# ---------------------------------------------------------------------------
# Function 7  (Phantom 2 → Production)
# ---------------------------------------------------------------------------

def compute_entry_quality(
    current_price: float,
    pivot_levels: dict,
    direction: str,
) -> dict:
    """
    Score entry quality as OPTIMAL/ACCEPTABLE/MARGINAL/POOR based on
    current price position relative to key pivot levels.

    pivot_levels keys (all optional, pass what you have):
      support_1, support_2, resistance_1, resistance_2,
      gamma_flip, call_wall, put_wall, gamma_island_level,
      vwap, kill_switch_level

    direction: "CALL" or "PUT"

    Logic:
      PUT thesis  → OPTIMAL if entering near resistance (crowded / at wall);
                    POOR if entering near support (early — favourable distance)
                    Wait — that is backwards. For a PUT:
                    OPTIMAL = entering at/near resistance (price about to turn down)
                    POOR    = entering far from resistance deep in no-man's-land

      CALL thesis → OPTIMAL = entering at/near support (price about to bounce)
                    POOR    = entering far from support, deep in no-man's-land
    """
    if current_price <= 0 or not pivot_levels:
        return {
            "entry_quality":              "UNAVAILABLE",
            "zone_position":              "UNKNOWN",
            "distance_to_nearest_pct":    None,
            "nearest_level_type":         "NONE",
            "note":                       "Insufficient price or pivot data",
        }

    direction = str(direction).upper()

    # Classify each pivot as support or resistance relative to current price
    support_levels    = []
    resistance_levels = []
    for label, level in pivot_levels.items():
        if not level:
            continue
        try:
            lv = float(level)
        except (TypeError, ValueError):
            continue
        if lv <= 0:
            continue
        if lv < current_price:
            support_levels.append((label, lv))
        else:
            resistance_levels.append((label, lv))

    nearest_support    = max(support_levels,    key=lambda x: x[1]) if support_levels    else None
    nearest_resistance = min(resistance_levels, key=lambda x: x[1]) if resistance_levels else None

    if direction == "PUT":
        # OPTIMAL: entering near resistance (high probability of reversal point)
        anchor_label, anchor_level = nearest_resistance or (None, None)
    elif direction == "CALL":
        # OPTIMAL: entering near support (high probability of bounce)
        anchor_label, anchor_level = nearest_support or (None, None)
    else:
        anchor_label, anchor_level = None, None

    if anchor_level is None or anchor_level <= 0:
        return {
            "entry_quality":           "MARGINAL",
            "zone_position":           "NO_ANCHOR_LEVEL",
            "distance_to_nearest_pct": None,
            "nearest_level_type":      "NONE",
            "note":                    f"No {'resistance' if direction == 'PUT' else 'support'} level available",
        }

    distance_pct = abs(current_price - anchor_level) / current_price * 100.0

    if distance_pct <= 0.5:
        quality = "OPTIMAL"
        note    = f"Price at {anchor_label} ({anchor_level:.2f}) — {distance_pct:.1f}% away; ideal reversal zone"
    elif distance_pct <= 2.0:
        quality = "ACCEPTABLE"
        note    = f"Price within 2% of {anchor_label} ({anchor_level:.2f}); acceptable entry proximity"
    elif distance_pct <= 5.0:
        quality = "MARGINAL"
        note    = f"Price {distance_pct:.1f}% from {anchor_label} ({anchor_level:.2f}); marginal entry positioning"
    else:
        quality = "POOR"
        note    = f"Price {distance_pct:.1f}% from {anchor_label} ({anchor_level:.2f}); entry far from key level"

    return {
        "entry_quality":           quality,
        "zone_position":           f"{'NEAR' if distance_pct <= 2.0 else 'FAR_FROM'}_{anchor_label.upper().replace(' ','_') if anchor_label else 'ANCHOR'}",
        "distance_to_nearest_pct": round(distance_pct, 2),
        "nearest_level_type":      anchor_label or "UNKNOWN",
        "note":                    note,
    }
