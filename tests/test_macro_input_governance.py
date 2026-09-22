from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from canonical_data.macro_input_manifest import publish_macro_input_manifest
from domain.macro_input_governance import (
    MacroInputContractError,
    REQUIRED_CAPTURE_COHORT_MAX_SECONDS,
    build_macro_input_manifest,
    build_macro_prompt_context,
    validate_manifest_lineage,
)


def _required_capture_files(root: Path, *, report_batch: str, fred_batch: str) -> tuple[dict[str, str], dict[str, object]]:
    files = {
        "report_json": str(_write(root / f"report_{report_batch}.json", json.dumps({"timestamp": "2026-09-20T19:33:03"}))),
        "macro_csv": str(_write(root / f"macro_{fred_batch}.csv", "indicator,value,date\nDGS10,4.25,2026-09-18\n")),
        "forward_bias_csv": str(_write(root / f"forward_bias_{fred_batch}.csv", "horizon,direction,run_id\nshort_1_5d,NEUTRAL," + fred_batch + "\n")),
    }
    data = {
        key: (json.loads(Path(path).read_text()) if path.endswith(".json") else Path(path).read_text())
        for key, path in files.items()
    }
    return files, data


def test_independent_required_collectors_form_bounded_capture_cohort(tmp_path: Path) -> None:
    files, data = _required_capture_files(
        tmp_path, report_batch="20260920_193227", fred_batch="20260920_192739",
    )
    manifest = build_macro_input_manifest(files, [], data=data)
    coherence = manifest["capture_coherence"]
    assert coherence["status"] == "COHERENT_MULTI_RUNTIME"
    assert coherence["span_seconds"] == 288
    assert coherence["max_span_seconds"] == REQUIRED_CAPTURE_COHORT_MAX_SECONDS
    assert coherence["runtime_identity_policy"] == "IGNORED_NON_EVIDENTIARY"
    assert validate_manifest_lineage(manifest)["valid"] is True


def test_separate_colab_outputs_need_time_coherence_not_matching_ids(tmp_path: Path) -> None:
    files, data = _required_capture_files(
        tmp_path, report_batch="20260920_193227", fred_batch="20260920_192739",
    )
    replacement = _write(
        tmp_path / "forward_bias_20260920_192800.csv",
        "horizon,direction,run_id\nshort_1_5d,NEUTRAL,20260920_192800\n",
    )
    files["forward_bias_csv"] = str(replacement)
    data["forward_bias_csv"] = replacement.read_text()
    manifest = build_macro_input_manifest(files, [], data=data)
    coherence = manifest["capture_coherence"]
    assert coherence["status"] == "COHERENT_MULTI_RUNTIME"
    assert coherence["required_batches"] == {
        "report_json": "20260920_193227",
        "macro_csv": "20260920_192739",
        "forward_bias_csv": "20260920_192800",
    }
    assert validate_manifest_lineage(manifest)["valid"] is True


def test_required_collectors_outside_cohort_window_fail_closed(tmp_path: Path) -> None:
    files, data = _required_capture_files(
        tmp_path, report_batch="20260920_200000", fred_batch="20260920_192739",
    )
    with pytest.raises(MacroInputContractError, match="exceed capture cohort window"):
        build_macro_input_manifest(files, [], data=data)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _gex_files(root: Path) -> tuple[dict[str, str], dict[str, object]]:
    proxy = _write(
        root / "avshunter_gex_proxy.csv",
        "Ticker,Date,As_Of,Data_Mode,Net_GEX_Bn,Regime,Gamma_Flip,Call_Wall,Put_Wall,Data_Status,Run_Id,Dataset_Id\n"
        "SPY,2026-09-18,2026-09-18T20:00:00Z,HISTORICAL,-5.2,NEGATIVE,768,772,745,OK,RUN,D1\n"
        "QQQ,2026-09-18,2026-09-18T20:00:00Z,HISTORICAL,0.4,POSITIVE,719,720,700,OK,RUN,D2\n",
    )
    strike = _write(
        root / "avshunter_gex_by_strike.csv",
        "Ticker,Date,strike,net_gex_usd_1pct,Run_Id,Dataset_Id\n"
        "SPY,2026-09-18,700,-10,RUN,D1\n"
        "SPY,2026-09-18,760,500,RUN,D1\n"
        "SPY,2026-09-18,780,-900,RUN,D1\n"
        "QQQ,2026-09-18,720,300,RUN,D2\n",
    )
    manifest = {
        "contract_version": "avshunter_local_gex_manifest_v1",
        "status": "COMPLETE",
        "session_date": "2026-09-18",
        "run_id": "RUN",
        "dataset_ids": ["D1", "D2"],
        "proxy_sha256": hashlib.sha256(proxy.read_bytes()).hexdigest(),
        "by_strike_sha256": hashlib.sha256(strike.read_bytes()).hexdigest(),
    }
    manifest_path = root / "avshunter_gex_run_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return {
        "gex_proxy_csv": str(proxy),
        "gex_by_strike_csv": str(strike),
        "gex_manifest_json": str(manifest_path),
    }, manifest


def test_manifest_is_immutable_and_rejects_changed_gex_projection(tmp_path: Path) -> None:
    files, gex_manifest = _gex_files(tmp_path)
    data = {
        "gex_proxy_csv": Path(files["gex_proxy_csv"]).read_text(encoding="utf-8"),
        "gex_by_strike_csv": Path(files["gex_by_strike_csv"]).read_text(encoding="utf-8"),
        "gex_manifest_json": gex_manifest,
    }
    manifest = build_macro_input_manifest(files, [], data=data)
    assert manifest["authority"] == "ADVISORY_ONLY"
    assert manifest["gex_validation"]["status"] == "VALIDATED"
    assert validate_manifest_lineage(manifest)["valid"] is True

    Path(files["gex_proxy_csv"]).write_text("changed", encoding="utf-8")
    result = validate_manifest_lineage(manifest)
    assert result["valid"] is False
    assert any("gex_proxy_csv:SHA256_MISMATCH" in item for item in result["errors"])


def test_manifest_allows_only_explicit_runtime_gex_supersession(tmp_path: Path) -> None:
    files, gex_manifest = _gex_files(tmp_path)
    macro_source = _write(tmp_path / "macro_20260918_120000.csv", "Date,value\n2026-09-18,1\n")
    files["macro_csv"] = str(macro_source)
    data = {
        key: (json.loads(Path(path).read_text()) if path.endswith(".json") else Path(path).read_text())
        for key, path in files.items()
    }
    data["gex_manifest_json"] = gex_manifest
    manifest = build_macro_input_manifest(files, [], data=data, required_keys=("macro_csv",))
    Path(files["gex_proxy_csv"]).write_text("runtime replacement", encoding="utf-8")
    allowed = validate_manifest_lineage(
        manifest,
        allow_changed_keys=("gex_proxy_csv",),
    )
    assert allowed["valid"] is True
    assert allowed["superseded_keys"] == ["gex_proxy_csv"]

    macro_source.write_text("Date,value\n2026-09-18,2\n", encoding="utf-8")
    rejected = validate_manifest_lineage(
        manifest,
        allow_changed_keys=("gex_proxy_csv",),
    )
    assert rejected["valid"] is False
    assert "macro_csv:SHA256_MISMATCH" in rejected["errors"]


def test_gex_manifest_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    files, gex_manifest = _gex_files(tmp_path)
    gex_manifest["proxy_sha256"] = "0" * 64
    data = {
        "gex_proxy_csv": Path(files["gex_proxy_csv"]).read_text(encoding="utf-8"),
        "gex_by_strike_csv": Path(files["gex_by_strike_csv"]).read_text(encoding="utf-8"),
        "gex_manifest_json": gex_manifest,
    }
    with pytest.raises(MacroInputContractError, match="GEX proxy hash"):
        build_macro_input_manifest(files, [], data=data)


def test_failed_gex_publication_is_recorded_but_cannot_supply_numbers(tmp_path: Path) -> None:
    """A source outage must not abort unrelated advisory macro evidence."""
    files, data = _required_capture_files(
        tmp_path, report_batch="20260921_193227", fred_batch="20260921_192739",
    )
    gex_files, _ = _gex_files(tmp_path)
    files.update(gex_files)
    failed = {
        "run_id": "FAILED_RUN",
        "run_date": "2026-09-21",
        "ticker_status": {
            "SPY_HISTORICAL": "MISSING", "SPY_LIVE": "MISSING",
            "QQQ_HISTORICAL": "MISSING", "QQQ_LIVE": "MISSING",
        },
        "outputs": {
            "avshunter_gex_proxy.csv": {
                "sha256": hashlib.sha256(Path(files["gex_proxy_csv"]).read_bytes()).hexdigest(),
            },
            "avshunter_gex_by_strike.csv": {
                "sha256": hashlib.sha256(Path(files["gex_by_strike_csv"]).read_bytes()).hexdigest(),
            },
        },
    }
    Path(files["gex_manifest_json"]).write_text(json.dumps(failed), encoding="utf-8")
    data.update({
        "gex_proxy_csv": Path(files["gex_proxy_csv"]).read_text(),
        "gex_by_strike_csv": Path(files["gex_by_strike_csv"]).read_text(),
        "gex_manifest_json": failed,
    })
    manifest = build_macro_input_manifest(files, [], data=data)
    assert manifest["gex_validation"]["status"] == "SOURCE_UNAVAILABLE"
    assert validate_manifest_lineage(manifest)["valid"] is True
    context = build_macro_prompt_context({"data": data, "input_manifest": manifest})
    assert context["domain_coverage"]["gex"] == "SOURCE_UNAVAILABLE"
    assert "tickers" not in context["gex"]
    assert "-5.2" not in json.dumps(context["gex"])

    failed["outputs"]["avshunter_gex_proxy.csv"]["sha256"] = "0" * 64
    Path(files["gex_manifest_json"]).write_text(json.dumps(failed), encoding="utf-8")
    with pytest.raises(MacroInputContractError, match="GEX gex_proxy_csv hash"):
        build_macro_input_manifest(files, [], data={**data, "gex_manifest_json": failed})


def test_failed_gex_can_omit_by_strike_but_complete_claim_cannot(tmp_path: Path) -> None:
    files, _ = _gex_files(tmp_path)
    files.pop("gex_by_strike_csv")
    proxy = Path(files["gex_proxy_csv"])
    failed = {
        "run_id": "FAILED_RUN",
        "ticker_status": {"SPY_HISTORICAL": "MISSING", "QQQ_HISTORICAL": "MISSING"},
        "outputs": {proxy.name: {"sha256": hashlib.sha256(proxy.read_bytes()).hexdigest()}},
    }
    manifest_path = Path(files["gex_manifest_json"])
    manifest_path.write_text(json.dumps(failed), encoding="utf-8")
    data = {"gex_proxy_csv": proxy.read_text(), "gex_manifest_json": failed}
    result = build_macro_input_manifest(files, ["avshunter_gex_by_strike.csv"], data=data)
    assert result["gex_validation"]["status"] == "SOURCE_UNAVAILABLE"
    assert result["gex_validation"]["missing_components"] == ["gex_by_strike_csv"]

    failed["status"] = "COMPLETE"
    manifest_path.write_text(json.dumps(failed), encoding="utf-8")
    with pytest.raises(MacroInputContractError, match="one atomic unit"):
        build_macro_input_manifest(files, [], data={**data, "gex_manifest_json": failed})


def test_prompt_context_preserves_complete_records_and_semantic_gex(tmp_path: Path) -> None:
    files, gex_manifest = _gex_files(tmp_path)
    flags = "series,flag,source,as_of\n" + "".join(
        f"S{i},GREEN,SRC,2026-09-18\n" for i in range(23)
    )
    sectors = "ticker,name,weekly_pct,obs_date\n" + "".join(
        f"X{i},Sector {i},{i},2026-09-18\n" for i in range(11)
    )
    fred = ",DGS10,USSLIND\n2020-02-01,,1.72\n2026-09-17,4.25,\n"
    breadth = "mode,state,as_of\nEOD,NARROWING,2026-09-18\n"
    for key, name, text in (
        ("threshold_flags_csv", "macro_series_threshold_flags.csv", flags),
        ("sectors_csv", "sectors_20260918_120000.csv", sectors),
        ("fred_master_csv", "avshunter_fred_master.csv", fred),
        ("breadth_csv", "breadth_rsp_spy.csv", breadth),
    ):
        files[key] = str(_write(tmp_path / name, text))
    data: dict[str, object] = {
        key: (json.loads(Path(path).read_text()) if path.endswith(".json") else Path(path).read_text())
        for key, path in files.items()
    }
    data["gex_manifest_json"] = gex_manifest
    payload = {"data": data, "files_found_by_key": files, "files_missing": []}
    payload["input_manifest"] = build_macro_input_manifest(files, [], data=data)

    context = build_macro_prompt_context(payload)
    assert len(context["sources"]["threshold_flags_csv"]["records"]) == 23
    assert len(context["sources"]["sectors_csv"]["records"]) == 11
    assert context["sources"]["breadth_csv"]["records"][0]["state"] == "NARROWING"
    assert context["fred_latest_observations"]["DGS10"]["observation_date"] == "2026-09-17"
    assert context["fred_latest_observations"]["USSLIND"]["status"] == "STALE_BY_CADENCE"
    spy = context["gex"]["tickers"]["SPY"]
    assert spy["net_gex_bn"] == -5.2
    assert spy["top_absolute_strikes"][0]["strike"] == 780.0
    assert context["input_consumption_status"] == "COMPLETE"
    assert all(
        item["status"] == "CONSUMED"
        for item in context["input_consumption_ledger"].values()
    )

    encoded = json.dumps(context)
    assert "S22" in encoded
    assert "Sector 10" in encoded
    assert "TRUNCATED" not in encoded


def test_manifest_repository_is_idempotent_and_atomic(tmp_path: Path) -> None:
    source = _write(tmp_path / "input.csv", "Date,value\n2026-09-18,1\n")
    manifest = build_macro_input_manifest(
        {"macro_csv": str(source)}, [], data={"macro_csv": source.read_text()}
    )
    first = publish_macro_input_manifest(
        manifest, tmp_path / "archive", tmp_path / "macro_input_manifest_latest.json",
        evidence_root=tmp_path / "evidence",
    )
    second = publish_macro_input_manifest(
        manifest, tmp_path / "archive", tmp_path / "macro_input_manifest_latest.json",
        evidence_root=tmp_path / "evidence",
    )
    assert first == second
    latest = json.loads((tmp_path / "macro_input_manifest_latest.json").read_text())
    assert latest["manifest_sha256"] == manifest["manifest_sha256"]
    assert first["evidence_file_count"] == "1"
    assert len(list((tmp_path / "evidence").rglob("*.csv"))) == 1
