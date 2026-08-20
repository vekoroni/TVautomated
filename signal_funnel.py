"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AVSHUNTER · SIGNAL FUNNEL TRACKER                                         ║
║  Enhancement: E2 — Signal Discard Discipline                               ║
║                                                                             ║
║  Deploy to: C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/                  ║
║  Imports in: morning_validation.py, intelligent_orchestrator.py            ║
║  Output to:  data/output/runs/{run_id}/signal_funnel_{run_id}.json         ║
║              data\funnel_log.csv  (rolling history)                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import csv
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("avshunter.signal_funnel")

# ─── CONSTANTS ────────────────────────────────────────────────────────────────

# Pipeline stages in order — must match your actual filter sequence
PIPELINE_STAGES = [
    "universe_loaded",
    "after_liquidity_gate",
    "after_regime_filter",
    "after_wbs_threshold",
    "after_superbrain_veto",
    "after_eil_filter",
    "traded",
]

# Alert thresholds
DISCARD_RATE_WARN  = 0.85   # Warn if discard rate drops below this
DISCARD_RATE_IDEAL = 0.95   # Ideal target ceiling


# ─── SIGNAL FUNNEL ────────────────────────────────────────────────────────────

class SignalFunnel:
    """
    Records ticker counts at every filter stage of the AVSHUNTER pipeline.

    Usage (wrap around your existing filter logic):

        funnel = SignalFunnel(run_id="20260418_143000", base_dir=BASE_DIR)
        funnel.record("universe_loaded",      all_tickers)
        funnel.record("after_liquidity_gate", liq_passed)
        funnel.record("after_regime_filter",  regime_passed)
        funnel.record("after_wbs_threshold",  wbs_passed)
        funnel.record("after_superbrain_veto", sb_passed)
        funnel.record("after_eil_filter",     eil_passed)
        funnel.record("traded",               traded_today)
        funnel.save()
        report = funnel.report()
        print(report["summary"])
    """

    def __init__(
        self,
        run_id:    str,
        base_dir:  Optional[Path] = None,
        log_path:  Optional[Path] = None,
    ):
        self.run_id     = run_id
        self.base_dir   = Path(base_dir) if base_dir else Path(__file__).parent
        self.log_path   = log_path or (self.base_dir / "data" / "funnel_log.csv")
        self.run_dir    = self.base_dir / "data" / "output" / "runs" / run_id / "superbrain"
        self.stages: dict[str, int]        = {}
        self.tickers: dict[str, list[str]] = {}   # optional: store actual tickers per stage
        self._ts = datetime.utcnow().isoformat()

    def record(self, stage: str, tickers: list | set | int) -> None:
        """
        Record how many tickers survive a filter stage.

        tickers can be:
          - a list/set of ticker strings
          - an int (count only — no ticker names stored)
        """
        if isinstance(tickers, int):
            self.stages[stage]  = tickers
        else:
            ticker_list = list(tickers)
            self.stages[stage]  = len(ticker_list)
            self.tickers[stage] = ticker_list

        log.debug(f"Funnel stage [{stage}]: {self.stages[stage]} tickers")

    def _universe_count(self) -> int:
        """First stage count = universe size."""
        if not self.stages:
            return 1
        return list(self.stages.values())[0] or 1

    def discard_rate(self) -> float:
        """Overall discard rate: 1 - (traded / universe)."""
        universe = self._universe_count()
        traded   = self.stages.get("traded", 0)
        return round(1.0 - (traded / universe), 4)

    def stage_survival_rates(self) -> dict[str, float]:
        """Survival rate at each stage vs universe."""
        universe = self._universe_count()
        return {
            stage: round(count / universe, 4)
            for stage, count in self.stages.items()
        }

    def report(self) -> dict:
        """Generate full funnel report dict."""
        universe      = self._universe_count()
        traded        = self.stages.get("traded", 0)
        discard       = self.discard_rate()
        survival      = self.stage_survival_rates()

        # Per-stage drop-off
        stage_names   = list(self.stages.keys())
        stage_counts  = list(self.stages.values())
        stage_drops   = {}
        for i in range(1, len(stage_counts)):
            prev = stage_counts[i-1] or 1
            curr = stage_counts[i]
            stage_drops[stage_names[i]] = round(1 - curr/prev, 4)

        # Health assessment
        if discard < DISCARD_RATE_WARN:
            health = "WARN"
            health_msg = (
                f"Discard rate {discard*100:.1f}% is BELOW minimum target "
                f"({DISCARD_RATE_WARN*100:.0f}%). Filters may be too loose — "
                f"investigate SuperBrain veto or WBS threshold."
            )
        elif discard > DISCARD_RATE_IDEAL:
            health = "INFO"
            health_msg = f"Discard rate {discard*100:.1f}% at ideal ceiling. Good filter discipline."
        else:
            health = "OK"
            health_msg = f"Discard rate {discard*100:.1f}% within target range."

        # Summary text
        lines = [
            f"{'─'*55}",
            f"  SIGNAL FUNNEL REPORT  ·  {self.run_id}",
            f"{'─'*55}",
        ]
        for stage, count in self.stages.items():
            pct = survival.get(stage, 0) * 100
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            lines.append(f"  {stage:<28} {count:>4}  [{bar}] {pct:.1f}%")
        lines += [
            f"{'─'*55}",
            f"  DISCARD RATE: {discard*100:.1f}%   TARGET: "
            f"{DISCARD_RATE_WARN*100:.0f}–{DISCARD_RATE_IDEAL*100:.0f}%",
            f"  [{health}] {health_msg}",
            f"{'─'*55}",
        ]
        summary = "\n".join(lines)

        return {
            "run_id":        self.run_id,
            "timestamp":     self._ts,
            "universe":      universe,
            "traded":        traded,
            "discard_rate":  discard,
            "health":        health,
            "health_msg":    health_msg,
            "stages":        self.stages,
            "survival_rates":survival,
            "stage_drops":   stage_drops,
            "summary":       summary,
        }

    def save(self) -> None:
        """
        Save:
          1. Run-level JSON: data/output/runs/{run_id}/superbrain/signal_funnel_{run_id}.json
          2. Rolling CSV log: data/funnel_log.csv
        """
        report = self.report()

        # ── Run-level JSON ────────────────────────────────────────────────────
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            json_path = self.run_dir / f"signal_funnel_{self.run_id}.json"
            with open(json_path, "w") as f:
                # Exclude verbose summary text from JSON
                save_dict = {k: v for k, v in report.items() if k != "summary"}
                json.dump(save_dict, f, indent=2)
            log.info(f"Signal funnel JSON saved: {json_path}")
        except Exception as e:
            log.error(f"Failed to save funnel JSON: {e}")

        # ── Rolling CSV log ───────────────────────────────────────────────────
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            file_exists = self.log_path.exists()
            row = {
                "run_id":       self.run_id,
                "timestamp":    self._ts,
                "universe":     report["universe"],
                "traded":       report["traded"],
                "discard_rate": report["discard_rate"],
                "health":       report["health"],
            }
            # Add per-stage counts as flat columns
            for stage, count in self.stages.items():
                row[f"stage_{stage}"] = count

            with open(self.log_path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)
            log.info(f"Signal funnel appended to log: {self.log_path}")
        except Exception as e:
            log.error(f"Failed to append funnel CSV: {e}")

        # Print summary to console
        print(report["summary"])


# ─── INTEL LAB READER ─────────────────────────────────────────────────────────

def load_funnel_for_run(run_id: str, base_dir: Path) -> Optional[dict]:
    """
    Load funnel report for a given run_id.
    Called by Intelligence Lab Flask backend to populate Pipeline Health tab.
    """
    json_path = (
        base_dir / "data" / "output" / "runs" / run_id
        / "superbrain" / f"signal_funnel_{run_id}.json"
    )
    if not json_path.exists():
        return None
    try:
        with open(json_path) as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Failed to load funnel for {run_id}: {e}")
        return None


def get_funnel_trend(log_path: Path, n_runs: int = 30) -> list[dict]:
    """
    Return last n_runs of funnel history from CSV.
    Used to render discard rate trend chart in Intel Lab.
    """
    if not log_path.exists():
        return []
    rows = []
    try:
        with open(log_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({
                    "run_id":       row.get("run_id"),
                    "timestamp":    row.get("timestamp"),
                    "discard_rate": float(row.get("discard_rate", 0)),
                    "universe":     int(row.get("universe", 0)),
                    "traded":       int(row.get("traded", 0)),
                    "health":       row.get("health", "UNKNOWN"),
                })
    except Exception as e:
        log.error(f"Failed to read funnel log: {e}")
    return rows[-n_runs:]


# ─── CLI ENTRY ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Signal Funnel Tracker — demo")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--run_id", type=str, default="DEMO_" + datetime.utcnow().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    if args.demo:
        funnel = SignalFunnel(run_id=args.run_id)

        # Simulate realistic pipeline counts
        funnel.record("universe_loaded",       75)
        funnel.record("after_liquidity_gate",  58)
        funnel.record("after_regime_filter",   34)
        funnel.record("after_wbs_threshold",   18)
        funnel.record("after_superbrain_veto",  9)
        funnel.record("after_eil_filter",       6)
        funnel.record("traded",                 4)

        report = funnel.report()
        print(report["summary"])
        print(f"\nDiscard rate: {report['discard_rate']*100:.1f}%")
