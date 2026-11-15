"""Lane B Fix B (12 Nov 2026): the hand-off is the Lab's publication, copied, flagged and ordered. Never recomputed.

Synthetic Lab publication in a temp folder: no live data, no network.
Run (PowerShell, repo root):
    venv\\Scripts\\python.exe -m pytest data\\scratch\\workaround\\test_laneb_lab_handoff.py -q -p no:cacheprovider --basetemp=%TEMP%\\avs_lb
"""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_lab_handoff as blh   # noqa: E402
import lab_reader                  # noqa: E402

RUN = "20261111_231951"
FIELDS = ["ticker", "sector_etf", "direction", "lab_rank", "lab_verdict", "final_action", "trade_lane_setup",
          "thesis__trigger_age_sessions", "anticipated_level", "anticipated_level_basis", "anticipated_level_q50",
          "anticipated_sessions_q50", "anticipated_time_fit", "contract_symbol", "contract_bid", "contract_ask",
          "contract_oi", "selected_quote_timestamp_utc", "scenario_invalidation_return_on_premium", "bar_data_asof"]


def row(ticker, verdict, rank, **kw):
    base = {"ticker": ticker, "sector_etf": "XLF", "direction": "CALL", "lab_rank": rank, "lab_verdict": verdict,
            "final_action": verdict, "trade_lane_setup": "1d|Spring|ACTIVATED", "thesis__trigger_age_sessions": "5.0",
            "anticipated_level": 107.9199, "anticipated_level_basis": "STRUCTURAL", "anticipated_level_q50": 103.674,
            "anticipated_sessions_q50": 12, "anticipated_time_fit": "CONTRACT_OUTLASTS_Q80",
            "contract_symbol": f"{ticker}270115C00090000", "contract_bid": 3.8, "contract_ask": 4.0, "contract_oi": 817.0,
            "selected_quote_timestamp_utc": "2026-11-12T14:50:16Z", "scenario_invalidation_return_on_premium": -0.8,
            "bar_data_asof": "2026-11-11"}
    base.update(kw)
    return base


ROWS = [
    row("AAA", "MANUAL_REVIEW", 1),
    row("GOO", "GO_LIMIT", 50, sector_etf="XLI"),
    row("NAN", "MANUAL_REVIEW", 2, direction="PUT", scenario_invalidation_return_on_premium=0, contract_oi=None,
        thesis__trigger_age_sessions="115.0", anticipated_sessions_q50=42, trade_lane_setup="1mo|SOW|ACTIVATED"),
    row("BBB", "MANUAL_REVIEW", 3, contract_symbol="", contract_bid="", contract_ask="", contract_oi=""),
    row("BLK", "BLOCKED", 4),
    row("REP", "CONTRACT_REPAIR", 5),
]


def publish(tmp_path, rows=ROWS, state="COMPLETE", revision="a" * 32, fields=FIELDS):
    folder = tmp_path / "runs" / RUN / "intelligence_lab" / "review_projection"
    folder.mkdir(parents=True, exist_ok=True)
    db = folder / f"review-{revision}.sqlite"
    con = sqlite3.connect(db)
    con.executescript("""CREATE TABLE rows(row_key TEXT PRIMARY KEY, ordinal INTEGER UNIQUE NOT NULL, sector TEXT NOT NULL,
        home_json TEXT NOT NULL, card_json TEXT NOT NULL);
        CREATE TABLE evidence(row_key TEXT NOT NULL, family TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(row_key, family));
        CREATE TABLE publication(schema TEXT, run_id TEXT, revision TEXT, row_count INTEGER);""")
    for i, r in enumerate(rows):
        key = hashlib.sha256(r["ticker"].encode()).hexdigest()
        values = [r.get(f) for f in fields]
        card = {"values": values, "missing_fields": [j for j, v in enumerate(values) if v in (None, "")]}
        con.execute("INSERT INTO rows VALUES(?,?,?,?,?)", (key, i, "Financials", "{}", json.dumps(card)))
        for fam in ("structure", "option_risk", "context", "morning", "audit"):
            f = {"family_marker": fam}
            if fam == "option_risk":
                f.update({"contract_repair_status": "CONTRACT_REPAIR_REQUIRED" if r["ticker"] == "AAA" else "CONTRACT_OK",
                          "contract_repair_action": "NOT_REQUIRED"})
            con.execute("INSERT INTO evidence VALUES(?,?,?)", (key, fam, zlib.compress(json.dumps({"fields": f}).encode())))
    con.execute("INSERT INTO publication VALUES(?,?,?,?)", ("lab_review_projection_v1", RUN, revision, len(rows)))
    con.commit(); con.close()
    manifest = {"schema": "lab_review_projection_v1", "run_id": RUN, "revision": revision, "publication_state": state,
                "card_fields": fields, "database_file": db.name, "database_sha256": hashlib.sha256(db.read_bytes()).hexdigest(),
                "row_count": len(rows), "created_at_utc": "2026-11-12T20:19:00+00:00",
                "source_receipt": {"issues": [], "watch_inputs": []}}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path / "runs"


def build(tmp_path, runs, *extra):
    out = tmp_path / "handoff"
    code = blh.main(["--run", RUN, "--runs-dir", str(runs), "--out-root", str(out), "--price-db", str(tmp_path / "none.sqlite"),
                     "--settings", str(tmp_path / "no_settings.json"), "--day-settings", str(tmp_path / "no_day.json"),
                     "--legacy-root", str(tmp_path / "no_legacy"), *extra])
    folder = out / "lab_2026-11-12"
    rows = list(csv.DictReader((folder / "handoff.csv").open(encoding="utf-8", newline=""))) if (folder / "handoff.csv").exists() else []
    return code, folder, rows


# ---------------------------------------------------------------- B1: the Lab publication is the input

def test_refuses_to_build_when_the_lab_publication_is_not_complete(tmp_path, capsys):
    runs = publish(tmp_path, state="BUILDING")
    code, folder, _ = build(tmp_path, runs)
    assert code != 0 and not (folder / "handoff.csv").exists()
    assert "COMPLETE" in capsys.readouterr().out


def test_refuses_to_build_when_the_manifest_is_missing(tmp_path, capsys):
    (tmp_path / "runs" / RUN).mkdir(parents=True)
    code, folder, _ = build(tmp_path, tmp_path / "runs")
    assert code != 0 and "manifest" in capsys.readouterr().out.lower()


def test_refuses_when_the_database_is_not_the_one_the_manifest_published(tmp_path):
    runs = publish(tmp_path)
    m = runs / RUN / "intelligence_lab" / "review_projection" / "manifest.json"
    j = json.loads(m.read_text()); j["database_sha256"] = "0" * 64; m.write_text(json.dumps(j))
    with pytest.raises(lab_reader.LabUnavailable):
        lab_reader.open_lab(RUN, runs)


def test_hand_off_holds_go_limit_and_manual_review_rows_and_counts_every_excluded_verdict(tmp_path):
    code, folder, rows = build(tmp_path, publish(tmp_path))
    assert code == 0
    assert {r["ticker"] for r in rows} == {"AAA", "GOO", "NAN", "BBB"}
    receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["counts"]["lab_rows_in"] == 6 and receipt["counts"]["handoff_rows"] == 4
    assert receipt["counts"]["excluded_by_verdict"] == {"BLOCKED": 1, "CONTRACT_REPAIR": 1}


def test_lab_fields_are_copied_as_stored_under_their_lab_names(tmp_path):
    _, _, rows = build(tmp_path, publish(tmp_path))
    by = {r["ticker"]: r for r in rows}
    assert by["AAA"]["anticipated_level"] == "107.9199" and by["AAA"]["anticipated_level_q50"] == "103.674"
    assert by["AAA"]["contract_symbol"] == "AAA270115C00090000"
    assert "NAN" in by, "the ticker NAN is a real ticker and must survive"
    assert by["NAN"]["scenario_invalidation_return_on_premium"] == "0", "a real zero stays a zero"
    assert by["NAN"]["contract_oi"] == "", "not available is blank, never 0"
    assert "contract_oi" in by["NAN"]["lb_lab_missing_fields"]


def test_a_field_missing_from_the_manifest_is_blank_and_recorded_not_a_failure(tmp_path):
    fields = [f for f in FIELDS if f != "anticipated_time_fit"]
    code, folder, rows = build(tmp_path, publish(tmp_path, fields=fields))
    assert code == 0 and rows[0]["lb_time_fit"] == ""
    assert "anticipated_time_fit" in json.loads((folder / "receipt.json").read_text(encoding="utf-8"))["lab_fields_missing"]


def test_evidence_file_carries_the_card_and_the_four_families(tmp_path):
    _, folder, _ = build(tmp_path, publish(tmp_path))
    first = json.loads((folder / "handoff_evidence.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert set(first["evidence"]) == {"structure", "option_risk", "context", "morning"}
    assert first["card"]["ticker"] == first["ticker"]


def test_a_changed_lab_revision_is_refused_unless_refresh_which_keeps_the_old_set(tmp_path, capsys):
    build(tmp_path, publish(tmp_path))
    runs = publish(tmp_path, revision="b" * 32)
    code, folder, _ = build(tmp_path, runs)
    assert code != 0 and "--refresh" in capsys.readouterr().out
    assert json.loads((folder / "receipt.json").read_text(encoding="utf-8"))["lab_revision"] == "a" * 32
    code, folder, _ = build(tmp_path, runs, "--refresh")
    assert code == 0
    assert json.loads((folder / "receipt.json").read_text(encoding="utf-8"))["lab_revision"] == "b" * 32
    assert (folder / "_rev_aaaaaaaa" / "handoff.csv").exists()


# ---------------------------------------------------------------- B2: one target, one contract

def test_hand_off_has_one_target_set_and_one_contract_set_and_no_lane_b_substitutes(tmp_path):
    _, _, rows = build(tmp_path, publish(tmp_path))
    cols = list(rows[0])
    assert cols.count("anticipated_level") == 1 and cols.count("contract_symbol") == 1
    banned = ("half_target", "best_contract", "level_capped", "lb_target", "lb_contract")
    assert not [c for c in cols if any(b in c for b in banned)]


def test_legacy_compare_shows_where_the_old_hand_off_differed(tmp_path):
    legacy = tmp_path / "legacy" / "split_2026-11-12_cap5"
    legacy.mkdir(parents=True)
    (legacy / "handoff.csv").write_text("ticker,side,level,half_target,best_contract_checked,best_contract\n"
                                        "AAA,CALL,107.9199,98.75,AAA270319C00095000,AAA270319C00095000\n"
                                        "NAN,PUT,107.9199,103.674,NAN270115C00090000,\n", encoding="utf-8")
    out = tmp_path / "handoff"
    blh.main(["--run", RUN, "--runs-dir", str(publish(tmp_path)), "--out-root", str(out), "--legacy-root", str(tmp_path / "legacy"),
              "--price-db", str(tmp_path / "none.sqlite"), "--settings", str(tmp_path / "x.json"), "--day-settings", str(tmp_path / "y.json")])
    rows = {r["ticker"]: r for r in csv.DictReader((out / "lab_2026-11-12" / "legacy_compare.csv").open(encoding="utf-8", newline=""))}
    assert rows["AAA"]["differs"] == "True" and rows["AAA"]["contract_differs"] == "True" and rows["AAA"]["first_profit_differs"] == "True"
    assert rows["NAN"]["differs"] == "False"


# ---------------------------------------------------------------- B3: flags, order, groups, batches

def test_order_is_go_limit_first_then_lab_rank_and_nothing_else(tmp_path):
    _, _, rows = build(tmp_path, publish(tmp_path))
    assert [r["ticker"] for r in rows] == ["GOO", "AAA", "NAN", "BBB"]
    assert [r["lb_order"] for r in rows] == ["1", "2", "3", "4"]
    rebuilt = sorted(rows, key=lambda r: (r["lab_verdict"] != "GO_LIMIT", float(r["lab_rank"])))
    assert [r["ticker"] for r in rebuilt] == [r["ticker"] for r in rows]


def test_batches_follow_the_order_and_each_gets_a_pack_command(tmp_path):
    (tmp_path / "s.json").write_text(json.dumps({"batch_size": 3}), encoding="utf-8")
    out = tmp_path / "handoff"
    blh.main(["--run", RUN, "--runs-dir", str(publish(tmp_path)), "--out-root", str(out), "--settings", str(tmp_path / "s.json"),
              "--price-db", str(tmp_path / "none.sqlite"), "--day-settings", str(tmp_path / "y.json"), "--legacy-root", str(tmp_path / "nl")])
    folder = out / "lab_2026-11-12"
    rows = list(csv.DictReader((folder / "handoff.csv").open(encoding="utf-8", newline="")))
    assert [r["lb_batch"] for r in rows] == ["1", "1", "1", "2"]
    assert "ticker_pack.py GOO AAA NAN" in (folder / "pack_commands" / "ticker_pack_command_1.txt").read_text(encoding="utf-8")
    assert (folder / "pack_commands" / "ticker_pack_command_2.txt").exists()


def test_group_is_sector_etf_and_direction_with_the_first_row_primary(tmp_path):
    _, _, rows = build(tmp_path, publish(tmp_path))
    by = {r["ticker"]: r for r in rows}
    assert by["AAA"]["lb_group"] == "XLF_CALL" and by["AAA"]["lb_group_role"] == "PRIMARY"
    assert by["BBB"]["lb_group"] == "XLF_CALL" and by["BBB"]["lb_group_role"] == "ALTERNATE"
    assert by["GOO"]["lb_group_role"] == "PRIMARY"


def test_window_is_a_flag_on_the_proxy_q50_clock_until_the_lab_publishes_n(tmp_path):
    _, _, rows = build(tmp_path, publish(tmp_path))
    by = {r["ticker"]: r for r in rows}
    assert by["AAA"]["lb_window_flag"] == "IN_WINDOW" and by["AAA"]["lb_window_basis"] == "PROXY_Q50"
    assert by["NAN"]["lb_window_flag"] == "OUTSIDE_WINDOW", "a monthly setup is flagged, never dropped"
    assert by["AAA"]["monetisation_state"] == "NOT_PUBLISHED" and by["AAA"]["monetisation_n_q50"] == ""


def test_window_filter_mode_drops_outside_rows_and_counts_them(tmp_path):
    (tmp_path / "s.json").write_text(json.dumps({"window_mode": "filter"}), encoding="utf-8")
    out = tmp_path / "handoff"
    blh.main(["--run", RUN, "--runs-dir", str(publish(tmp_path)), "--out-root", str(out), "--settings", str(tmp_path / "s.json"),
              "--price-db", str(tmp_path / "none.sqlite"), "--day-settings", str(tmp_path / "y.json"), "--legacy-root", str(tmp_path / "nl")])
    receipt = json.loads((out / "lab_2026-11-12" / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["counts"]["excluded_by_window_filter"] == 1 and receipt["counts"]["handoff_rows"] == 3


@pytest.mark.parametrize("bid,ask,oi,tier", [
    (3.8, 4.0, 817, "A"),       # 5.1% of mid, OI fine
    (3.5, 4.0, 817, "B"),       # 13.3%
    (3.0, 4.0, 817, "C"),       # 28.6%
    (3.8, 4.0, 50, "C"),        # OI under 100
    (None, 4.0, 817, "C"),      # no bid
    (0.0, 0.5, 817, "C"),       # zero bid is no bid
    (1.00, 1.10, 817, "A"),     # under 1.50, 9.5%, 0.10 wide
    (1.36, 1.50, 817, "B"),     # under 1.50, 9.8% but 0.14 wide: not A
    (3.8, 4.0, None, "C"),      # OI not recorded is not a pass
])
def test_saved_quote_liquidity_tiers_of_11_nov(bid, ask, oi, tier):
    assert blh.liquidity_tier(bid, ask, oi)[0] == tier


def test_flags_never_drop_a_row_cap_gate_trigger_age_and_repair_conflict(tmp_path):
    (tmp_path / "d.json").write_text(json.dumps({"cap": 3}), encoding="utf-8")
    out = tmp_path / "handoff"
    blh.main(["--run", RUN, "--runs-dir", str(publish(tmp_path)), "--out-root", str(out), "--settings", str(tmp_path / "x.json"),
              "--price-db", str(tmp_path / "none.sqlite"), "--day-settings", str(tmp_path / "d.json"), "--legacy-root", str(tmp_path / "nl")])
    by = {r["ticker"]: r for r in csv.DictReader((out / "lab_2026-11-12" / "handoff.csv").open(encoding="utf-8", newline=""))}
    assert len(by) == 4
    assert by["AAA"]["lb_over_cap"] == "OVER_CAP" and by["BBB"]["lb_over_cap"] == "NO_QUOTE"
    assert by["AAA"]["lb_saved_gate"] == "A" and by["AAA"]["lb_saved_gate_basis"].startswith("SAVED_QUOTE")
    assert by["BBB"]["lb_saved_gate"] == "NO_CONTRACT"
    assert by["NAN"]["lb_runway_note"].startswith("TRIGGER_AGE") and by["AAA"]["lb_runway_note"] == ""
    assert by["AAA"]["lb_repair_conflict"] == "True" and by["GOO"]["lb_repair_conflict"] == "False"
    assert by["AAA"]["lb_stock_tier"] == "NO_PRICE_HISTORY"


def test_stock_tier_from_twenty_day_dollar_volume(tmp_path):
    db = tmp_path / "p.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE ohlcv_daily(ticker TEXT, trading_date TEXT, adjustment_convention TEXT, close REAL, volume REAL, bar_status TEXT)")
    for i in range(25):
        d = f"2026-10-{i + 1:02d}"
        con.execute("INSERT INTO ohlcv_daily VALUES('AAA',?, 'X', 100.0, 600000.0, 'COMPLETE')", (d,))   # $60M
        con.execute("INSERT INTO ohlcv_daily VALUES('GOO',?, 'X', 10.0, 3000000.0, 'COMPLETE')", (d,))    # $30M
        con.execute("INSERT INTO ohlcv_daily VALUES('BBB',?, 'X', 10.0, 100000.0, 'COMPLETE')", (d,))     # $1M
    con.commit(); con.close()
    tiers = blh.stock_tiers(["AAA", "GOO", "BBB", "NAN"], db, {"stock_tier_a_usd": 50e6, "stock_tier_b_usd": 20e6, "stock_tier_bars": 20})
    assert tiers["AAA"][0] == "A" and tiers["GOO"][0] == "B" and tiers["BBB"][0] == "C" and tiers["NAN"][0] == "NO_PRICE_HISTORY"


# ---------------------------------------------------------------- focus list (ACK 15 Nov 2026)

def focus_build(tmp_path, names):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "s.json").write_text(json.dumps({"batch_size": 2, "focus_tickers": names}), encoding="utf-8")
    out = tmp_path / "handoff"
    blh.main(["--run", RUN, "--runs-dir", str(publish(tmp_path)), "--out-root", str(out), "--settings", str(tmp_path / "s.json"),
              "--price-db", str(tmp_path / "none.sqlite"), "--day-settings", str(tmp_path / "y.json"), "--legacy-root", str(tmp_path / "nl")])
    folder = out / "lab_2026-11-12"
    return folder, list(csv.DictReader((folder / "handoff.csv").open(encoding="utf-8", newline="")))


def test_focus_names_fill_the_first_batches_in_the_order_given_and_no_row_is_dropped(tmp_path):
    folder, rows = focus_build(tmp_path, ["bbb", "AAA"])
    assert [r["ticker"] for r in rows] == ["BBB", "AAA", "GOO", "NAN"]     # focus first as listed, then the Lab order
    assert [r["lb_batch"] for r in rows] == ["1", "1", "2", "2"]
    assert [r["lb_focus"] for r in rows] == ["FOCUS", "FOCUS", "", ""]
    assert "ticker_pack.py BBB AAA" in (folder / "pack_commands" / "ticker_pack_command_1.txt").read_text(encoding="utf-8")


def test_a_focus_list_changes_the_order_only_never_a_lab_value(tmp_path):
    _, plain = focus_build(tmp_path / "a", [])
    _, focus = focus_build(tmp_path / "b", ["BBB"])
    moved = ("lb_order", "lb_batch", "lb_focus", "lb_group_role")
    strip = lambda rows: {r["ticker"]: {k: v for k, v in r.items() if k not in moved} for r in rows}   # noqa: E731
    assert strip(plain) == strip(focus)
    assert all(r["lb_focus"] == "" for r in plain)


def test_a_focus_name_that_is_not_on_the_hand_off_is_recorded_not_invented(tmp_path):
    folder, rows = focus_build(tmp_path, ["ZZZ", "BBB"])
    receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
    assert rows[0]["ticker"] == "BBB" and len(rows) == 4
    assert receipt["counts"]["focus_rows"] == 1 and receipt["focus_not_on_handoff"] == ["ZZZ"]
    assert "Focus list" in (folder / "handoff.md").read_text(encoding="utf-8")
