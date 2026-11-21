"""Read-only local macro API usage, reservations and daily cap. No provider calls."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contracts.macro_api_cost import usage_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day', default=datetime.now(timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat())
    args = parser.parse_args()
    print(json.dumps(usage_status(ROOT, args.day), indent=2))


if __name__ == '__main__':
    main()
