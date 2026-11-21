"""Rolling clean-up of macro JSON archives: keep the last N completed US sessions (ACK 20 Nov 2026: "yes add the
10-session clean-up"; config/macro_retention_v1.json).

A raw copy older than the window is removed unless something still uses it:
- board_inputs: a board build whose session is inside the window used it (its snapshot's inputs manifest);
- feed_blobs: it is a currently accepted feed file (accepted.json) or a source the events ledger cites
  (events.json), matched by the "<sha256>.json" file name;
- age: nothing protects it beyond the window except the file names the target lists under "keep".
When the in-use list for a folder cannot be read, that folder is left alone. Only regular files directly inside a
configured folder are ever removed, and every removal is logged. The macro packet archive is not a target:
pipeline replays bind to it.

    venv\\Scripts\\python.exe scripts\\macro_retention.py            # dry run: what would be removed
    venv\\Scripts\\python.exe scripts\\macro_retention.py --apply    # remove and log
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "macro_retention_v1.json"
NEW_YORK = ZoneInfo("America/New_York")


def keep_from(completed_sessions: Sequence[date], sessions: int) -> datetime:
    """Start (00:00 New York) of the Nth most recent completed session; files at or after it are kept."""
    ordered = sorted(set(completed_sessions))
    if len(ordered) < sessions:
        raise ValueError(f"need {sessions} completed sessions, have {len(ordered)}")
    return datetime.combine(ordered[-sessions], time(0), NEW_YORK)


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and not p.is_symlink()) if folder.is_dir() else []


def _board_inputs_in_use(snapshots_dir: Path, start: datetime) -> set[str]:
    if not snapshots_dir.is_dir():
        raise OSError(f"no snapshots folder {snapshots_dir}")
    first = start.astimezone(NEW_YORK).date().isoformat()
    used = set()
    for snap in snapshots_dir.glob("board_*.json"):
        doc = json.loads(snap.read_text(encoding="utf-8"))
        if str(doc.get("as_of_session") or "") < first:
            continue
        for item in (doc.get("inputs") or {}).values():
            if isinstance(item, Mapping) and item.get("archived_as"):
                used.add(str(item["archived_as"]))
    return used


def _feed_blobs_in_use(root: Path, target: Mapping) -> set[str]:
    accepted = json.loads((root / target["accepted"]).read_text(encoding="utf-8"))
    ledger_path = root / target["events_ledger"]
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {}
    shas = {str(v["sha256"]) for v in accepted.values() if isinstance(v, Mapping) and v.get("sha256")}
    shas |= {str(v["source_sha256"]) for v in ledger.values() if isinstance(v, Mapping) and v.get("source_sha256")}
    return {f"{sha}.json" for sha in shas}


def plan(config: Mapping, root: Path, start: datetime) -> dict:
    """What would be removed. Nothing is deleted here."""
    out = {"keep_from": start.isoformat(), "delete": [], "kept": {}, "skipped": {}}
    for target in config["targets"]:
        folder = root / target["dir"]
        try:
            if target["rule"] == "board_inputs":
                in_use = _board_inputs_in_use(root / target["snapshots_dir"], start)
            elif target["rule"] == "feed_blobs":
                in_use = _feed_blobs_in_use(root, target)
            elif target["rule"] == "age":
                in_use = {str(name) for name in target.get("keep") or []}
            else:
                raise ValueError(f"unknown rule {target['rule']}")
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            out["skipped"][target["name"]] = f"cannot read what is in use ({type(exc).__name__}: {exc}); folder left alone"
            continue
        kept = 0
        for path in _files(folder):
            if path.name in in_use or _mtime(path) >= start:
                kept += 1
                continue
            out["delete"].append({"target": target["name"], "path": str(path), "bytes": path.stat().st_size})
        out["kept"][target["name"]] = kept
    return out


def apply(planned: Mapping, config: Mapping, root: Path, log_path: Path) -> dict:
    """Remove the planned files, refusing anything not directly inside its configured folder; log each one."""
    folders = {t["name"]: (root / t["dir"]).resolve() for t in config["targets"]}
    log_path.parent.mkdir(parents=True, exist_ok=True)
    deleted = refused = freed = 0
    with log_path.open("a", encoding="utf-8") as log:
        for item in planned["delete"]:
            path = Path(item["path"])
            folder = folders.get(item.get("target"))
            ok = (folder is not None and path.resolve().parent == folder and path.is_file() and not path.is_symlink())
            record = {"at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "target": item.get("target"),
                      "path": str(path), "bytes": item.get("bytes")}
            if not ok:
                refused += 1
                log.write(json.dumps({**record, "action": "REFUSED", "reason": "not a file directly inside its folder"}) + "\n")
                continue
            path.unlink()
            deleted += 1
            freed += int(item.get("bytes") or 0)
            log.write(json.dumps({**record, "action": "DELETED"}) + "\n")
    return {"deleted": deleted, "refused": refused, "freed_bytes": freed}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rolling clean-up of macro JSON archives (last N completed sessions).")
    parser.add_argument("--apply", action="store_true", help="remove the files (default: dry run)")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    from avshunter.shared.xnys_calendar import is_xnys_session, session_state

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    last = session_state(now)[2]
    sessions, day = [], last
    while len(sessions) < int(config["sessions"]):
        if is_xnys_session(day):
            sessions.append(day)
        day = date.fromordinal(day.toordinal() - 1)
    start = keep_from(sessions, int(config["sessions"]))
    planned = plan(config, ROOT, start)
    total = sum(int(p["bytes"]) for p in planned["delete"])
    print(f"[retention] keep the last {config['sessions']} sessions: files from {start:%Y-%m-%d} (New York) are kept")
    for name, kept in planned["kept"].items():
        n = sum(1 for p in planned["delete"] if p["target"] == name)
        print(f"[retention] {name}: remove {n}, keep {kept}")
    for name, why in planned["skipped"].items():
        print(f"[retention] {name}: SKIPPED - {why}")
    if not args.apply:
        print(f"[retention] DRY RUN: would remove {len(planned['delete'])} files ({total / 1e6:.1f} MB); pass --apply to remove")
        return 0
    log = ROOT / "logs" / "retention" / f"macro_retention_{now:%Y%m%d_%H%M%S}.jsonl"
    summary = apply(planned, config, ROOT, log)
    print(f"[retention] removed {summary['deleted']} files ({summary['freed_bytes'] / 1e6:.1f} MB), "
          f"refused {summary['refused']}; log {log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
