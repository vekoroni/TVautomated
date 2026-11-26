"""Publish a verified saved macro cycle to ETF board and Lab, without a macro build."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_board.cycle_publication import publish_saved_cycle

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycle-folder', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(publish_saved_cycle(args.cycle_folder, args.output), indent=2))
