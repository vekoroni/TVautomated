#!/usr/bin/env python3
"""Collect the day's board rows into one file in one shape (v1, 21 Nov 2026).

AVS-ENH-2026-11-21 Wave 0, F-29 (ACK go-ahead 21 Nov 2026). This reads board_row*.json files and writes one file. It
never writes to the Card Watch Board: that stays a chat step, now from a single file.

Why (verified 21 Nov): deep-dive chats cannot write to the board, so each saved a board_row file for hand pasting. On
20 Nov there were 23 files in 14 shapes (payload under data, row, rows[] or at the top level; extra call or put leg
rows; three file-name patterns), and five rows never reached the board.

Shapes accepted:
    {"doc_id": .., "collection": .., "data": {..}}        {"doc_id": .., "row": {..}}
    {"rows": [{"doc_id": .., "data": {..}}, ..]}          {"rows": {"<doc_id>": {..}, ..}}
    {..the row itself.., "id": ..}                        any of the above plus "<name>_row": {..} leg rows
A file that cannot be read, or holds no row, is listed under "rejected" with the reason. Nothing is dropped silently.

Run from the repo root (PowerShell); ticket_ready.py also runs it:
    venv\\Scripts\\python.exe data\\scratch\\workaround\\collect_board_rows.py --session 2026-11-20
Writes board_rows_<session>.json into the hand-off folder.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

VERSION = "collect_board_rows_v1"
WORK = Path("data") / "scratch" / "workaround"
META_KEYS = {"doc_id", "collection", "board", "note", "status", "rows", "data", "row"}
NAME_ID = re.compile(r"^board_rows?_(?:\d{4}-\d{2}-\d{2}_)?(?P<id>.+?)(?:_\d{4}-\d{2}-\d{2})?$")


def _id_from_name(path: Path) -> str:
    found = NAME_ID.match(path.stem)
    return (found.group("id") if found else path.stem).upper()


def _rows_in(payload, path: Path) -> list[tuple[str, dict]]:
    """Every (doc_id, row) in one file, whatever shape it was saved in."""
    if not isinstance(payload, dict):
        raise ValueError("the file is not a JSON object")
    fallback = str(payload.get("doc_id") or payload.get("id") or _id_from_name(path))
    found: list[tuple[str, dict]] = []
    rows = payload.get("rows")
    if isinstance(rows, list):
        for index, item in enumerate(rows):
            if not isinstance(item, dict):
                continue
            inner = item.get("data") if isinstance(item.get("data"), dict) else item.get("row") if isinstance(item.get("row"), dict) else None
            data = inner if inner is not None else {k: v for k, v in item.items() if k not in ("doc_id", "collection")}
            found.append((str(item.get("doc_id") or data.get("id") or f"{fallback}_{index + 1}"), data))
    elif isinstance(rows, dict):
        found += [(str(doc_id), data) for doc_id, data in rows.items() if isinstance(data, dict)]
    for key in ("data", "row"):
        if isinstance(payload.get(key), dict):
            found.append((fallback, payload[key]))
    for key, value in payload.items():                        # extra leg rows: call_leg_row, put_leg_row_when_triggered ...
        if key not in ("row",) and "_row" in key and isinstance(value, dict):
            found.append((str(value.get("id") or value.get("doc_id") or f"{fallback}_{key}"), value))
    if not found and not any(k in payload for k in ("rows", "data", "row")):
        found.append((fallback, {k: v for k, v in payload.items() if k not in ("collection", "board", "note", "status")}))
    return found


def collect(folders, session: str) -> dict:
    """Read every board_row*.json in the folders (and their decisions sub-folder). Later files replace earlier ids."""
    rows: dict[str, dict] = {}
    rejected, duplicates, files_read = [], [], 0
    for folder in folders:
        folder = Path(folder)
        files = sorted(set(folder.glob("board_row*.json")) | set((folder / "decisions").glob("*board_row*.json")),
                       key=lambda p: (p.stat().st_mtime, p.name))
        for path in files:
            if path.name == f"board_rows_{session}.json":      # this collector's own output
                continue
            files_read += 1
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                found = _rows_in(payload, path)
            except (OSError, ValueError) as error:
                rejected.append({"file": path.name, "folder": folder.name, "reason": f"{type(error).__name__}: {error}"[:200]})
                continue
            usable = [(doc_id, data) for doc_id, data in found if isinstance(data, dict) and data]
            if not usable:
                rejected.append({"file": path.name, "folder": folder.name, "reason": "no row with any field in the file"})
                continue
            collection = str(payload.get("collection") or "cards") if isinstance(payload, dict) else "cards"
            for doc_id, data in usable:
                if doc_id in rows:
                    duplicates.append({"doc_id": doc_id, "kept": path.name, "replaced": rows[doc_id]["source_file"]})
                rows[doc_id] = {"doc_id": doc_id, "collection": collection, "data": data, "source_file": path.name}
    ordered = [rows[k] for k in sorted(rows)]
    return {"version": VERSION, "session": session, "files_read": files_read, "row_count": len(ordered),
            "rows": ordered, "rejected": rejected, "duplicates": duplicates}


def write(result: dict, folder: Path, session: str) -> Path:
    out = Path(folder) / f"board_rows_{session}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({**result, "written_local": datetime.now().strftime("%Y-%m-%d %H:%M"),
                               "written_to_board": False,
                               "next_step": "a chat with access to the Card Watch Board inserts these rows; this file never writes to the board"},
                              indent=1), encoding="utf-8")
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--session", required=True, help="session date YYYY-MM-DD")
    parser.add_argument("--handoff-root", default=str(WORK / "handoff"))
    parser.add_argument("--out-folder", help="default: the session's lab_<session> hand-off folder")
    args = parser.parse_args(argv)
    root = Path(args.handoff_root)
    folders = [f for f in root.iterdir() if f.is_dir() and args.session in f.name] if root.is_dir() else []
    result = collect(folders, args.session)
    out = write(result, Path(args.out_folder) if args.out_folder else root / f"lab_{args.session}", args.session)
    print(f"{VERSION}: {result['row_count']} row(s) from {result['files_read']} file(s), {len(result['rejected'])} rejected -> {out}")
    for item in result["rejected"]:
        print(f"  REJECTED {item['file']}: {item['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
