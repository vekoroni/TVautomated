#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run_dir", required=True)
    parser.add_argument("--universe_in", required=False)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    manifest = {
        "run_id": run_dir.name,
        "created_utc": utc_now(),
        "macro_snapshot_exists": (run_dir / "macro_snapshot.json").exists(),
        "packages_count": len(list((run_dir / "packages").glob("*.json"))) if (run_dir / "packages").exists() else 0,
        "vanguard_signals_exists": (run_dir / "vanguard" / "vanguard_signals.csv").exists()
    }

    out_path = run_dir / "manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest written to {out_path}")

if __name__ == "__main__":
    main()
