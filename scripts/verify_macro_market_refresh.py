"""Verify current-run market evidence before FULL analysis; no providers or writes."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contracts.macro_market_refresh_gate import verify_refresh


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=ROOT/'dropbox/market_data')
    parser.add_argument('--not-before-utc', required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_refresh(args.input_dir, not_before=datetime.fromisoformat(args.not_before_utc.replace('Z', '+00:00')))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('STOPPED: FULL_MARKET_REFRESH_REQUIRED: ' + str(error))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
