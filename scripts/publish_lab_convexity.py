"""Publish additive convexity comparisons from an existing saved review. No pipeline/network."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contracts.lab_convexity_watchlist import publish_saved_convexity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--runs-dir', type=Path, default=ROOT/'data/output/runs')
    args = parser.parse_args()
    # Provider calls are mechanically forbidden, including accidental dependencies.
    import socket
    def forbid(*a, **kw):
        raise RuntimeError('Convexity publication is saved-data only: network forbidden')
    socket.socket.connect = forbid
    print(json.dumps(publish_saved_convexity(args.runs_dir, args.run), indent=2))


if __name__ == '__main__':
    main()
