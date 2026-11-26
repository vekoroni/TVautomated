"""Offline structural/semantic validator for the macro_narrative_v1 record."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_board.cycle_narrative import validate

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    args = parser.parse_args()
    narrative = json.loads(args.file.read_text(encoding='utf-8-sig'))
    validate(narrative)
    print(json.dumps({'validation': 'PASS', 'narrative_id': narrative['narrative_id'],
                      'authority': narrative['authority'], 'content_status': narrative['status']}))
