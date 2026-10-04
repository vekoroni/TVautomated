"""Scanner daily tier (ACK 4 Oct 2026: "scan the whole list daily").

The daily tier was TIER2_UNIVERSE[:75] - the first 75 names by list position, not by logic. The whole list
(235 names, 226 with cached IV history) completed in about 16 minutes on 1 Oct 2026.
Business rules:
- The daily tier is the whole list by default.
- The count lives in versioned configuration; lowering it there is the credit safeguard, never a code edit.
"""
import json

from scripts import avshunter_universe_scanner as scanner


def test_daily_tier_is_the_whole_list():
    assert scanner.build_tier1_universe() == list(scanner.TIER2_UNIVERSE)


def test_daily_tier_size_comes_from_configuration(tmp_path, monkeypatch):
    cfg = tmp_path / "scanner_v1.json"
    cfg.write_text(json.dumps({"version": "scanner_v1", "daily_tier_size": 10}), encoding="utf-8")
    monkeypatch.setattr(scanner, "SCANNER_CONFIG_PATH", cfg)
    assert scanner.build_tier1_universe() == list(scanner.TIER2_UNIVERSE)[:10]


def test_weekly_tier_never_rescans_what_the_daily_tier_scanned():
    daily = scanner.build_tier1_universe()
    assert scanner.tier2_remaining(daily) == []
    assert scanner.tier2_remaining(daily[:10]) == list(scanner.TIER2_UNIVERSE)[10:]
