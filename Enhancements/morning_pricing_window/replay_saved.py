"""Replay saved start clocks through the pure guard; never execute Morning."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from domain.morning_pricing_window import MorningPricingWindowClosed, require_morning_pricing_start


def main():
    records = []
    for run_id in ("20261111_231951", "20261110_231648"):
        path = ROOT / f"data/output/runs/{run_id}/morning_validation/morning_gate_summary_{run_id}.json"
        before = path.read_bytes()
        summary = json.loads(before.decode("utf-8-sig"))
        # Honour the timestamp's explicit UTC offset, not its legacy field name.
        instant = datetime.fromisoformat(summary["postopen_contract_refresh_observed_at_et"].replace("Z", "+00:00"))
        try:
            decision = require_morning_pricing_start(summary["morning_execution_mode"], instant)
            state, reason = decision["state"], ""
        except MorningPricingWindowClosed as error:
            state, reason = "WOULD_STOP_BEFORE_PRICING", str(error)
        assert before == path.read_bytes(), "Saved report changed during replay"
        records.append({"run_id": run_id, "source": str(path), "source_sha256": hashlib.sha256(before).hexdigest(),
                        "saved_window_state": summary["postopen_contract_refresh_window_state"],
                        "saved_start": instant.isoformat(), "result": state, "reason": reason})
    report = {"status": "PASS", "source_reports_unchanged": True, "pipeline_runs": 0,
              "provider_calls": 0, "records": records,
              "limitation": "Two historical late starts replayed; five forward-session acceptance checks remain outstanding."}
    output = Path(__file__).with_name("SAVED_REPLAY_20261113.json")
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
