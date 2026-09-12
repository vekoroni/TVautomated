from __future__ import annotations

from datetime import timezone
from pathlib import Path
import symtable

import intelligent_orchestrator


ROOT = Path(__file__).resolve().parents[1]


def test_discovery_main_resolves_os_from_module_scope() -> None:
    source_path = ROOT / "avshunter_discovery_ULTIMATE.py"
    table = symtable.symtable(
        source_path.read_text(encoding="utf-8"),
        str(source_path),
        "exec",
    )
    main_table = next(
        child
        for child in table.get_children()
        if child.get_name() == "main" and child.get_type() == "function"
    )

    os_symbol = main_table.lookup("os")
    assert os_symbol.is_global()
    assert not os_symbol.is_local()


def test_macro_utc_parser_accepts_timezone_less_utc_contract_value() -> None:
    parsed = intelligent_orchestrator._parse_utc_timestamp(
        "2026-09-06T16:38:28.937702"
    )

    assert parsed.tzinfo == timezone.utc
    assert parsed.isoformat() == "2026-09-06T16:38:28.937702+00:00"


def test_macro_utc_parser_normalises_explicit_offset() -> None:
    parsed = intelligent_orchestrator._parse_utc_timestamp(
        "2026-09-06T17:38:28+01:00"
    )

    assert parsed.tzinfo == timezone.utc
    assert parsed.isoformat() == "2026-09-06T16:38:28+00:00"
