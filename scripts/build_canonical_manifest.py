"""Write ``runs/<run_id>/canonical_manifest.json`` for one run (AVS-PKG-002 P1).

Runs beside the package build; consumers still read packages. Read-only on every store,
no provider call, no authority. Exit 0 on success, 1 on a typed failure (message on stderr).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from avshunter.c0_run.canonical_manifest import (  # noqa: E402
    build_canonical_manifest, collect_canonical_inputs, validate_canonical_manifest,
    write_canonical_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-dir", default=str(REPO / "data" / "output" / "runs"))
    parser.add_argument("--macro-path", default=None,
                        help="Runtime macro the injector wrote into the packages (default: the run's GEX-synced copy)")
    args = parser.parse_args()
    run_dir = Path(args.runs_dir) / args.run_id
    try:
        inputs = collect_canonical_inputs(run_dir=run_dir, repo_root=REPO, macro_runtime_path=args.macro_path)
        manifest = build_canonical_manifest(inputs, created_at_utc=datetime.now(timezone.utc))
        path = write_canonical_manifest(run_dir, manifest)
        check = validate_canonical_manifest(path)
    except (OSError, ValueError) as error:
        print(f"CANONICAL_MANIFEST_FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    coverage = manifest["coverage"]
    print(
        f"canonical_manifest: run={manifest['run_id']} session={manifest['evidence_session']} "
        f"tickers={coverage['tickers']} valid={coverage['valid']} rejected={coverage['rejected']} "
        f"by_reason={coverage['rejected_by_reason']} sha256={manifest['manifest_sha256'][:12]} "
        f"validated={check['valid']} -> {path}"
    )
    return 0 if check["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
