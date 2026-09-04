"""Evaluate AVS-SD-002 release evidence and guard feature promotion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestrator.dynamic_release import (
    PromotionStage,
    assess_release,
    load_evidence,
    promotion_environment,
    write_assessment_atomic,
)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--promotion-stage", choices=[item.value for item in PromotionStage])
    args = parser.parse_args(argv)

    assessment = assess_release(load_evidence(args.evidence), repo_root=args.repo)
    write_assessment_atomic(assessment, args.output)
    result: dict[str, object] = {"assessment": assessment.to_dict()}
    if args.promotion_stage:
        result["promotion_environment"] = promotion_environment(
            assessment, args.promotion_stage
        )
    print(json.dumps(result, indent=2))
    return 0 if assessment.promotable else 2


if __name__ == "__main__":
    raise SystemExit(main())
