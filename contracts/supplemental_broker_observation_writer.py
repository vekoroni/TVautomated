"""Atomic, provenance-checked filesystem persistence for a supplemental
broker observation.

Gap 1 follow-up (ACK, 25 Sep 2026, post-acceptance review): the domain layer
(domain.exact_contract_quote_join.build_supplemental_broker_observation_record)
only builds the record; it performs no I/O by design (the domain has no
filesystem dependency, matching every other module in this package). This
adapter is where the actual write happens.

It never overwrites an existing file at the target path: a path collision —
whether from the historical exact_option_quote snapshot or from a prior
supplemental read — is a hard error, not a silent replace. The write itself
is temp-file-then-rename, so a concurrent reader never observes a partially
written file, and a concurrent writer racing for the same path always loses
to whichever completed the rename first.
"""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile

from domain.exact_contract_quote_join import SupplementalBrokerObservationRecord


class SupplementalObservationAlreadyExistsError(FileExistsError):
    """Raised when persistence would overwrite an existing supplemental observation."""


def persist_supplemental_broker_observation_atomically(
    record: SupplementalBrokerObservationRecord,
    *,
    root_dir: Path | str,
) -> Path:
    """Write ``record`` to ``root_dir / record.persisted_as`` atomically.

    Refuses to overwrite an existing file at that path — including one written
    by a concurrent call that wins the race between this function's existence
    check and its rename.
    """
    root = Path(root_dir)
    target = root / record.persisted_as
    if target.exists():
        raise SupplementalObservationAlreadyExistsError(str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=".tmp_supplemental_", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(asdict(record), handle, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            raise SupplementalObservationAlreadyExistsError(str(target))
        os.replace(tmp_name, target)
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise
    return target


def read_persisted_supplemental_broker_observation(path: Path | str) -> dict:
    """Read back a persisted supplemental observation. No network/provider call."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


__all__ = [
    "SupplementalObservationAlreadyExistsError",
    "persist_supplemental_broker_observation_atomically",
    "read_persisted_supplemental_broker_observation",
]
