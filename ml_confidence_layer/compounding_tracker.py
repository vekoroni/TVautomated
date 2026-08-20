"""
AVSHUNTER $200 Compounding Tracker
====================================
Tracks every options trade against the $200 test account.
Logs P&L, updates running equity, feeds outcomes to ML layer.

Usage:
    from ml_confidence_layer.compounding_tracker import CompoundingTracker
    tracker = CompoundingTracker()
    tracker.open_trade(...)
    tracker.close_trade(...)
    tracker.print_summary()
"""

import json
import csv
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

LOG_DIR   = Path(__file__).parent / "trade_log"
LOG_FILE  = LOG_DIR / "trades.json"
CSV_FILE  = LOG_DIR / "equity_curve.csv"

STARTING_CAPITAL   = 200.0
MAX_DRAWDOWN_HALT  = 0.25   # halt compounding if equity falls 25% from peak
MAX_OPEN_TRADES    = 3      # max concurrent options positions on $200


@dataclass
class Trade:
    trade_id:         str
    ticker:           str
    direction:        str        # CALL / PUT
    entry_date:       str
    entry_price:      float      # option premium paid per contract
    contracts:        int
    max_risk_usd:     float
    ml_score:         float
    confidence_tier:  str
    wyckoff_phase:    str
    stop_loss:        float      # underlying price stop
    target_1:         float      # T1 underlying price
    target_2:         float      # T2 underlying price
    status:           str = "OPEN"
    exit_date:        str = ""
    exit_price:       float = 0.0
    pnl_usd:          float = 0.0
    outcome:          str = ""   # WIN / LOSS / SCRATCH
    notes:            str = ""


class CompoundingTracker:
    """
    Full lifecycle tracker for the $200 options compounding test.
    Every trade is logged to JSON + CSV for ML feedback and audit.
    """

    def __init__(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.trades:  list = self._load_trades()
        self.equity:  float = self._calculate_current_equity()
        self.peak_equity: float = self._calculate_peak_equity()
        self._init_csv()

    # ── Opening a Trade ───────────────────────────────────────────────────────
    def open_trade(self,
                   ticker:          str,
                   direction:       str,
                   entry_price:     float,
                   contracts:       int,
                   max_risk_usd:    float,
                   ml_score:        float,
                   confidence_tier: str,
                   wyckoff_phase:   str,
                   stop_loss:       float,
                   target_1:        float,
                   target_2:        float,
                   notes:           str = "") -> Optional[Trade]:
        """
        Register a new trade. Returns None if risk controls block the trade.
        """
        # Risk controls
        open_trades = [t for t in self.trades if t.status == "OPEN"]
        if len(open_trades) >= MAX_OPEN_TRADES:
            print(f"⛔ BLOCKED: {MAX_OPEN_TRADES} trades already open. Close one first.")
            return None

        drawdown = (self.peak_equity - self.equity) / self.peak_equity
        if drawdown >= MAX_DRAWDOWN_HALT:
            print(f"⛔ DRAWDOWN HALT: Equity down {drawdown:.0%} from peak ${self.peak_equity:.2f}. "
                  f"Review system before continuing.")
            return None

        if max_risk_usd > self.equity * 0.10:   # hard cap at 10% even for HIGH tier
            print(f"⚠️ Risk ${max_risk_usd:.2f} exceeds 10% equity cap. Reducing.")
            max_risk_usd = round(self.equity * 0.10, 2)

        trade_id = f"{ticker}_{direction}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        trade = Trade(
            trade_id       = trade_id,
            ticker         = ticker,
            direction      = direction.upper(),
            entry_date     = datetime.utcnow().isoformat(),
            entry_price    = entry_price,
            contracts      = contracts,
            max_risk_usd   = max_risk_usd,
            ml_score       = ml_score,
            confidence_tier= confidence_tier,
            wyckoff_phase  = wyckoff_phase,
            stop_loss      = stop_loss,
            target_1       = target_1,
            target_2       = target_2,
            notes          = notes
        )
        self.trades.append(trade)
        self._save()
        print(f"✅ TRADE OPENED: {ticker} {direction} | {contracts}x @ ${entry_price:.2f} | "
              f"Risk: ${max_risk_usd:.2f} | ML: {ml_score:.0f}/100 ({confidence_tier})")
        return trade

    # ── Closing a Trade ───────────────────────────────────────────────────────
    def close_trade(self, trade_id: str,
                    exit_price: float,
                    notes: str = "") -> Optional[Trade]:
        """
        Close an open trade. Calculates P&L and updates equity.
        """
        trade = next((t for t in self.trades if t.trade_id == trade_id
                      and t.status == "OPEN"), None)
        if not trade:
            print(f"Trade {trade_id} not found or already closed.")
            return None

        trade.exit_date  = datetime.utcnow().isoformat()
        trade.exit_price = exit_price
        trade.pnl_usd    = round((exit_price - trade.entry_price) * trade.contracts * 100, 2)
        trade.status     = "CLOSED"
        trade.outcome    = "WIN" if trade.pnl_usd > 0 else ("SCRATCH" if trade.pnl_usd == 0 else "LOSS")
        trade.notes      = notes

        self.equity = self._calculate_current_equity()
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity

        self._save()
        self._append_csv(trade)

        emoji = "🟢" if trade.outcome == "WIN" else ("🟡" if trade.outcome == "SCRATCH" else "🔴")
        print(f"{emoji} TRADE CLOSED: {trade.ticker} | P&L: ${trade.pnl_usd:+.2f} | "
              f"Equity: ${self.equity:.2f} | Outcome: {trade.outcome}")
        return trade

    # ── Summary ───────────────────────────────────────────────────────────────
    def print_summary(self):
        closed = [t for t in self.trades if t.status == "CLOSED"]
        open_t = [t for t in self.trades if t.status == "OPEN"]

        if not closed and not open_t:
            print("No trades logged yet.")
            return

        wins     = [t for t in closed if t.outcome == "WIN"]
        losses   = [t for t in closed if t.outcome == "LOSS"]
        total_pnl = sum(t.pnl_usd for t in closed)
        win_rate  = len(wins) / len(closed) if closed else 0
        avg_win   = sum(t.pnl_usd for t in wins) / len(wins) if wins else 0
        avg_loss  = sum(t.pnl_usd for t in losses) / len(losses) if losses else 0
        rr        = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        drawdown  = (self.peak_equity - self.equity) / self.peak_equity if self.peak_equity > 0 else 0

        print("\n" + "═"*55)
        print("   AVSHUNTER $200 COMPOUNDING TEST — SUMMARY")
        print("═"*55)
        print(f"  Starting Capital : $200.00")
        print(f"  Current Equity   : ${self.equity:.2f}  ({(self.equity/200-1)*100:+.1f}%)")
        print(f"  Peak Equity      : ${self.peak_equity:.2f}")
        print(f"  Max Drawdown     : {drawdown:.1%}")
        print(f"  Total P&L        : ${total_pnl:+.2f}")
        print("─"*55)
        print(f"  Total Trades     : {len(closed)} closed, {len(open_t)} open")
        print(f"  Win Rate         : {win_rate:.0%}  ({len(wins)}W / {len(losses)}L)")
        print(f"  Avg Win          : ${avg_win:+.2f}")
        print(f"  Avg Loss         : ${avg_loss:+.2f}")
        print(f"  Risk/Reward      : {rr:.2f}:1")

        # ML tier breakdown
        if closed:
            print("─"*55)
            print("  Performance by ML Tier:")
            for tier in ["HIGH", "STANDARD", "MODERATE", "CAUTIOUS", "MINIMAL"]:
                tier_trades = [t for t in closed if t.confidence_tier == tier]
                if tier_trades:
                    t_wins = sum(1 for t in tier_trades if t.outcome == "WIN")
                    t_pnl  = sum(t.pnl_usd for t in tier_trades)
                    print(f"    {tier:<10} {len(tier_trades):>3} trades | "
                          f"{t_wins/len(tier_trades):.0%} win | ${t_pnl:+.2f}")

        if open_t:
            print("─"*55)
            print("  Open Positions:")
            for t in open_t:
                print(f"    {t.ticker} {t.direction} | {t.contracts}x @ ${t.entry_price:.2f} | "
                      f"ML: {t.ml_score:.0f} ({t.confidence_tier})")
        print("═"*55 + "\n")

    def get_open_trades(self) -> list:
        return [t for t in self.trades if t.status == "OPEN"]

    # ── Internal ──────────────────────────────────────────────────────────────
    def _calculate_current_equity(self) -> float:
        closed_pnl = sum(t.pnl_usd for t in self.trades if t.status == "CLOSED")
        return round(STARTING_CAPITAL + closed_pnl, 2)

    def _calculate_peak_equity(self) -> float:
        running = STARTING_CAPITAL
        peak    = STARTING_CAPITAL
        for t in sorted(self.trades, key=lambda x: x.entry_date):
            if t.status == "CLOSED":
                running += t.pnl_usd
                if running > peak:
                    peak = running
        return round(peak, 2)

    def _load_trades(self) -> list:
        if LOG_FILE.exists():
            with open(LOG_FILE) as f:
                raw = json.load(f)
            return [Trade(**r) for r in raw]
        return []

    def _save(self):
        with open(LOG_FILE, "w") as f:
            json.dump([asdict(t) for t in self.trades], f, indent=2)

    def _init_csv(self):
        if not CSV_FILE.exists():
            with open(CSV_FILE, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "date", "ticker", "direction", "contracts",
                    "entry", "exit", "pnl_usd", "outcome",
                    "ml_score", "confidence_tier", "equity_after"
                ])

    def _append_csv(self, t: Trade):
        with open(CSV_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                t.exit_date[:10], t.ticker, t.direction, t.contracts,
                t.entry_price, t.exit_price, t.pnl_usd, t.outcome,
                t.ml_score, t.confidence_tier, self.equity
            ])


# ─────────────────────────────────────────────────────────────────────────────
# ENHANCEMENT 5 — Historical Trade Reconstruction (2026-04-16)
# ─────────────────────────────────────────────────────────────────────────────
# Logs known past trades so the ML feedback loop has real training data.
# Run once: python compounding_tracker.py --reconstruct
# After 10 closed trades, MLConfidenceEngine auto-retrains on real outcomes.
#
# AT&T (T) — the confirmed 200% return trade that proved the structural thesis.
# The pipeline correctly identified: Phase C accumulation, Crabel compression,
# BUYERS control, SELECTIVE_BULLISH macro. Premium tripled over ~2 months.
# Reconstructed from known outcome; approximated entry/exit from pattern timing.
#
# Add additional trades in the HISTORICAL_TRADES list as they are recalled.

HISTORICAL_TRADES = [
    {
        "ticker":           "T",
        "direction":        "CALL",
        "entry_date":       "2026-02-14",    # approximate — Phase C spring period
        "entry_price":      1.20,            # approximate ATM call premium at $22 stock
        "contracts":        1,
        "max_risk_usd":     120.0,
        "ml_score":         72.0,            # reconstructed from composite ~75
        "confidence_tier":  "STANDARD",
        "wyckoff_phase":    "C",
        "stop_loss":        21.50,
        "target_1":         24.00,
        "target_2":         26.00,
        "exit_date":        "2026-04-10",    # approximate — ~2 months later
        "exit_price":       3.60,            # 200% return on $1.20 premium → $3.60
        "outcome":          "WIN",
        "notes":            "AT&T Phase C spring. Crabel compression. BUYERS control. "
                            "200% return confirmed. Template trade for ML training.",
    },
]


def reconstruct_historical_trades(tracker: "CompoundingTracker") -> int:
    """
    Log known historical trades into CompoundingTracker.
    Skips trades already present (matched by ticker + entry_date).
    Returns count of newly added trades.
    """
    existing_ids = {t.trade_id for t in tracker.trades}
    added = 0

    for h in HISTORICAL_TRADES:
        # Synthetic trade_id matching open_trade() format
        synthetic_id = f"{h['ticker']}_{h['direction']}_{h['entry_date'].replace('-', '')}_{h['entry_date'].replace('-', '')}_000000"

        # Check if already logged (by ticker + approximate date)
        already = any(
            t.ticker == h['ticker'] and t.entry_date[:10] == h['entry_date'][:10]
            for t in tracker.trades
        )
        if already:
            continue

        from dataclasses import fields as _dc_fields
        trade = Trade(
            trade_id        = synthetic_id,
            ticker          = h["ticker"],
            direction       = h["direction"],
            entry_date      = h["entry_date"] + "T09:45:00",
            entry_price     = h["entry_price"],
            contracts       = h["contracts"],
            max_risk_usd    = h["max_risk_usd"],
            ml_score        = h["ml_score"],
            confidence_tier = h["confidence_tier"],
            wyckoff_phase   = h["wyckoff_phase"],
            stop_loss       = h["stop_loss"],
            target_1        = h["target_1"],
            target_2        = h["target_2"],
            status          = "CLOSED",
            exit_date       = h["exit_date"] + "T16:00:00",
            exit_price      = h["exit_price"],
            pnl_usd         = round(
                (h["exit_price"] - h["entry_price"]) * h["contracts"] * 100, 2
            ),
            outcome         = h["outcome"],
            notes           = h["notes"],
        )
        tracker.trades.append(trade)
        tracker.equity = tracker._calculate_current_equity()
        if tracker.equity > tracker.peak_equity:
            tracker.peak_equity = tracker.equity
        tracker._append_csv(trade)
        print(f"✅ Reconstructed: {trade.ticker} {trade.direction} | "
              f"P&L: ${trade.pnl_usd:+.2f} | Outcome: {trade.outcome}")
        added += 1

    if added > 0:
        tracker._save()
        print(f"\n  {added} historical trade(s) added to CompoundingTracker.")
        print(f"  Current equity: ${tracker.equity:.2f}")
        total_closed = len([t for t in tracker.trades if t.status == "CLOSED"])
        print(f"  Total closed trades: {total_closed}")
        if total_closed >= 10:
            print(f"  ✅ ML training threshold reached — run MLConfidenceEngine.retrain()")
        else:
            print(f"  ⏳ {10 - total_closed} more trade(s) needed before ML auto-retrain")
    else:
        print("  No new historical trades to add (already logged or list empty).")

    return added


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AVSHUNTER Compounding Tracker")
    parser.add_argument("--reconstruct", action="store_true",
                        help="Log known historical trades for ML training")
    parser.add_argument("--summary", action="store_true",
                        help="Print current equity curve summary")
    args = parser.parse_args()

    tracker = CompoundingTracker()

    if args.reconstruct:
        print("\n── Reconstructing historical trades ─────────────────────────")
        reconstruct_historical_trades(tracker)

    if args.summary or not any(vars(args).values()):
        tracker.print_summary()
