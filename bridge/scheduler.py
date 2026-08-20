from __future__ import annotations

from pathlib import Path

from .avshunter_reader import write_would_have_ordered


def phase1_read_and_record(run_dir: Path, output_dir: Path) -> Path:
    """Phase 1 bridge mode: zero capital, read-only AVSHUNTER input."""
    run_dir = Path(run_dir)
    date_part = run_dir.name
    return write_would_have_ordered(
        run_dir,
        Path(output_dir) / f"what_would_have_been_ordered_{date_part}.csv",
    )

