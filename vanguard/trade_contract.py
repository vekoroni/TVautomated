"""
VANGUARD — Trade Contract
=========================
Written at trade entry (Day 0) to lock the thesis.
The entry block is IMMUTABLE after creation.
Only status, days_in_trade, governance_history, exit_date,
and exit_reason are updated during the life of the trade.

Location:
    open/    → vanguard/trades/open/
    closed/  → vanguard/trades/closed/
    logs/    → vanguard/trades/governance_log/

Filename convention: {TICKER}_{YYYYMMDD}.json
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

# ── PATHS ─────────────────────────────────────────────────────────────────────
# Resolves relative to this file: vanguard/trade_contract.py → vanguard/trades/
_VANGUARD_ROOT = Path(__file__).resolve().parent
TRADES_ROOT    = _VANGUARD_ROOT / "trades"
OPEN_DIR       = TRADES_ROOT / "open"
CLOSED_DIR     = TRADES_ROOT / "closed"
GOV_LOG_DIR    = TRADES_ROOT / "governance_log"


def _ensure_dirs():
    for d in [OPEN_DIR, CLOSED_DIR, GOV_LOG_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def create_contract(
    ticker:                   str,
    entry_price:              float,
    direction:                str,    # CALL | PUT
    horizon_type:             str,    # 5D | 10D | 20D
    edge_quality:             str,    # STRONG | MODERATE | WEAK
    entry_ev:                 float,
    entry_win_rate:           float,
    entry_state_hash:         str,
    entry_vol_regime:         str,
    entry_trend_direction:    str,
    entry_trend_maturity:     str,
    entry_structure_quality:  str,
    entry_macro_regime:       str,
    entry_catalyst_proximity: str,
    entry_adx:                float,
    entry_atr_percentile:     float,
    invalidation_price:       float,
    max_expected_mae:         float,
) -> dict:
    """
    Create and persist a Trade Contract at entry.
    Returns the contract dict.
    Raises ValueError if an open contract for this ticker already exists.
    """
    _ensure_dirs()

    existing = find_open_contract(ticker)
    if existing:
        raise ValueError(
            f"[CONTRACT] Open contract already exists for {ticker}: {existing.name}. "
            f"Close existing position before creating a new one."
        )

    entry_date = datetime.now().strftime("%Y%m%d")

    contract = {
        # ── ENTRY BLOCK (immutable after creation) ───────────────────
        "ticker":                    ticker,
        "entry_date":                entry_date,
        "entry_price":               entry_price,
        "direction":                 direction,
        "horizon_type":              horizon_type,
        "horizon_expiry_date":       _calc_expiry(entry_date, horizon_type),
        "edge_quality":              edge_quality,
        "entry_ev":                  round(entry_ev, 6),
        "entry_win_rate":            round(entry_win_rate, 6),
        "entry_state_hash":          entry_state_hash,
        "entry_vol_regime":          entry_vol_regime,
        "entry_trend_direction":     entry_trend_direction,
        "entry_trend_maturity":      entry_trend_maturity,
        "entry_structure_quality":   entry_structure_quality,
        "entry_macro_regime":        entry_macro_regime,
        "entry_catalyst_proximity":  entry_catalyst_proximity,
        "entry_adx":                 round(entry_adx, 2),
        "entry_atr_percentile":      round(entry_atr_percentile, 2),
        "invalidation_price":        round(invalidation_price, 4),
        "max_expected_mae":          round(max_expected_mae, 6),
        "thesis_locked":             True,

        # ── GOVERNANCE BLOCK (appended each daily run) ───────────────
        "status":            "HOLD",   # HOLD | TIGHTEN | EXIT
        "days_in_trade":     0,
        "governance_history": [],      # list of daily check result dicts
        "exit_date":         None,
        "exit_reason":       None,
    }

    path = _contract_path(ticker, entry_date)
    path.write_text(json.dumps(contract, indent=2))
    print(f"[CONTRACT] Created: {path.name} | {direction} {horizon_type} | "
          f"EV={entry_ev:.2%} | Invalidation={invalidation_price:.2f}")
    return contract


def find_open_contract(ticker: str) -> Optional[Path]:
    """Return the open contract Path for a ticker, or None."""
    _ensure_dirs()
    matches = list(OPEN_DIR.glob(f"{ticker}_*.json"))
    return sorted(matches)[-1] if matches else None


def load_contract(path: Path) -> dict:
    return json.loads(path.read_text())


def save_contract(contract: dict, path: Path):
    path.write_text(json.dumps(contract, indent=2))


def close_contract(contract: dict, path: Path, exit_reason: str):
    """Move contract from open/ to closed/ and record exit."""
    contract["status"]      = "EXIT"
    contract["exit_date"]   = datetime.now().strftime("%Y%m%d")
    contract["exit_reason"] = exit_reason
    closed_path = CLOSED_DIR / path.name
    closed_path.write_text(json.dumps(contract, indent=2))
    path.unlink()
    print(f"[CONTRACT] Closed → {closed_path.name} | Reason: {exit_reason}")


def list_open_contracts() -> list:
    """Return sorted list of all open contract Paths."""
    _ensure_dirs()
    return sorted(OPEN_DIR.glob("*.json"))


def list_open_tickers() -> set:
    """Return set of ticker symbols that have open contracts."""
    return {p.stem.split("_")[0] for p in list_open_contracts()}


# ── INTERNAL ──────────────────────────────────────────────────────────────────

def _contract_path(ticker: str, entry_date: str) -> Path:
    return OPEN_DIR / f"{ticker}_{entry_date}.json"


def _calc_expiry(entry_date: str, horizon_type: str) -> str:
    """Calendar expiry estimate — governance checks trading days separately."""
    horizon_days = {"5D": 5, "10D": 10, "20D": 20, "90D": 90}
    days = horizon_days.get(horizon_type.upper(), 20)
    entry_dt = datetime.strptime(entry_date, "%Y%m%d")
    expiry_dt = entry_dt + timedelta(days=int(days * 1.4))
    return expiry_dt.strftime("%Y%m%d")
