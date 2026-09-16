"""Bounded real-provider integration probe; all writes go to a new scratch root."""
from datetime import date
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from canonical_data.marketdata_option_chain import MarketDataOptionChainAdapter
from orchestrator.completed_session_gex import refresh_completed_session_gex


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--session", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT) or output.exists():
        raise ValueError("Use a new scratch directory outside the production repository")
    load_dotenv(ROOT / ".env")
    macro = output / "dropbox" / "macro" / "macro_intelligence_latest.json"
    macro.parent.mkdir(parents=True)
    macro.write_text(json.dumps({"contract_version": "macro_contract_v1_0", "extras": {}, "conflict_flags": []}), encoding="utf-8")
    adapter = MarketDataOptionChainAdapter()
    acquisitions = []

    def fetch(ticker):
        payload = adapter.fetch(ticker, session_date=args.session, dte_max=60)
        acquisitions.append({"ticker": ticker, "contracts": len(payload["optionSymbol"]), "provider_gamma_count": sum(value is not None for value in payload.get("gamma", []))})
        (output / f"{ticker}_provider.json").write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
        print(json.dumps(acquisitions[-1]), flush=True)
        return payload

    first = refresh_completed_session_gex(repository_root=output, run_id="ISOLATED-GEX-1", session_date=args.session, fetch_chain=fetch)
    def no_fetch(ticker):
        raise AssertionError("Cache replay attempted another provider acquisition")
    second = refresh_completed_session_gex(repository_root=output, run_id="ISOLATED-GEX-2", session_date=args.session, fetch_chain=no_fetch) if first["status"] == "COMPLETE" else None
    report = {"production_modified": False, "acquisitions": acquisitions, "first": first, "cache_replay": second}
    (output / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if first["status"] == "COMPLETE" and second and second["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
