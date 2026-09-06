"""Versioned deterministic Market Structure Evidence calculation/persistence."""

from __future__ import annotations
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
import pandas as pd

from canonical_data.contracts import CompletenessStatus, DataScope, DatasetRecord, DatasetType
from canonical_data.registry import CanonicalRegistry
from canonical_data.storage import AtomicPayloadStore
from domain.market_structure_evidence import pin_market_structure_authority
from .lifecycle import direction_relationship, transition_lifecycle
from .params import MSParams, MS_PARAMS_V1
from .profile import build_market_profile, detect_double_distribution


ALGORITHM_VERSION = "market_structure_evidence_v1"


def _metrics(bars: pd.DataFrame, structure: Mapping[str, Any], profile, params: MSParams) -> dict[str, Any]:
    if not structure.get("detected"):
        return {"acceptance_minutes":0,"acceptance_closes":0,"volume_share":0.0,"vwap_hold_minutes":0,"repair_pct":0.0,"retest_count":0,"retest_result":"NOT_APPLICABLE","invalidated":False,"accepted":False}
    frame=bars.copy(); frame["timestamp_utc"]=pd.to_datetime(frame["timestamp_utc"],utc=True); frame=frame.sort_values("timestamp_utc")
    direction=structure["second_direction"]; second_low,second_high=structure["second_low"],structure["second_high"]
    inside=frame["close"].between(second_low,second_high)
    entry=frame.loc[inside,"timestamp_utc"].min() if inside.any() else pd.NaT
    minutes=0 if pd.isna(entry) else max(0,int((frame["timestamp_utc"].max()-entry).total_seconds()//60)+1)
    closes=frame.set_index("timestamp_utc")["close"].resample("5min").last().dropna()
    acceptance_closes=int((closes>structure["separation_high"]).sum() if direction=="ABOVE" else (closes<structure["separation_low"]).sum())
    total_volume=float(frame["volume"].sum()); volume_share=float(frame.loc[inside,"volume"].sum()/total_volume) if total_volume>0 else 0.0
    if "vwap_canonical" in frame:
        hold=(frame["close"]>=frame["vwap_canonical"]) if direction=="ABOVE" else (frame["close"]<=frame["vwap_canonical"])
        vwap_hold=int(hold.fillna(False).sum())
    else: vwap_hold=0
    sep=profile.bins.iloc[list(structure["separation_indexes"])]
    repaired=sep["tpo_count"] >= structure["weaker_peak"]*0.50
    repair_pct=float(repaired.mean()) if len(repaired) else 0.0
    boundary=structure["separation_high"] if direction=="ABOVE" else structure["separation_low"]
    beyond=(frame["close"]>boundary) if direction=="ABOVE" else (frame["close"]<boundary)
    retests=int(((beyond.shift(1)==True)&(beyond==False)).sum())
    invalidated=bool((frame["close"]<structure["first_low"]).iloc[-1] if direction=="ABOVE" else (frame["close"]>structure["first_high"]).iloc[-1])
    accepted=minutes>=params.acceptance_minutes and acceptance_closes>=params.acceptance_five_minute_closes and volume_share>=params.acceptance_volume_share and repair_pct<=params.intact_repair and not invalidated
    return {"acceptance_minutes":minutes,"acceptance_closes":acceptance_closes,"volume_share":round(volume_share,6),"vwap_hold_minutes":vwap_hold,"repair_pct":round(repair_pct,6),"retest_count":retests,"retest_result":"HELD" if beyond.iloc[-1] else "REPAIRED","invalidated":invalidated,"accepted":accepted}


def calculate_market_structure_evidence(*, ticker: str, session_date: date, run_id: str, bars: pd.DataFrame,
    exchange_tick: float, atr14: float, regular_open_utc: datetime, governed_direction: str,
    input_dataset_ids: tuple[str,...], input_hashes: tuple[str,...], prior_lifecycle: str|None=None,
    corporate_action_on_session: bool=False, params: MSParams=MS_PARAMS_V1) -> dict[str,Any]:
    profile=build_market_profile(bars,exchange_tick=exchange_tick,atr14=atr14,regular_open_utc=regular_open_utc,params=params)
    structure=detect_double_distribution(profile,atr14=atr14,params=params); metrics=_metrics(bars,structure,profile,params)
    quality="COARSE_DATA_LOW_CONFIDENCE" if corporate_action_on_session else profile.data_quality
    lifecycle=transition_lifecycle(prior=prior_lifecycle,detected=bool(structure.get("detected")),accepted=metrics["accepted"],repair_pct=metrics["repair_pct"],invalidated=metrics["invalidated"],params=params)
    relationship=direction_relationship(governed_direction=governed_direction,structure_direction=structure.get("second_direction"),lifecycle=lifecycle,quality=quality)
    # The evidence identity is stable across runs that consume the same
    # ordered canonical inputs.  run_id and duplicated input hashes are
    # provenance fields, not content-identity fields.
    lineage="|".join([ticker.upper(),session_date.isoformat(),ALGORITHM_VERSION,params.version,*input_dataset_ids])
    evidence_id=hashlib.sha256(lineage.encode("utf-8")).hexdigest()
    reason=("MS_INSUFFICIENT_DATA" if quality=="INSUFFICIENT_DATA" else structure.get("reason","MS_NO_STRUCTURE"))
    return pin_market_structure_authority({"ms_evidence_id":evidence_id,"ms_algorithm_version":ALGORITHM_VERSION,"ms_parameter_set_version":params.version,
        "ms_parameter_calibration_status":params.calibration_status,"ticker":ticker.upper(),"session_date":session_date.isoformat(),"run_id":run_id,
        "ms_calculated_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
        "ms_input_dataset_ids":list(input_dataset_ids),"ms_input_hashes":list(input_hashes),"ms_bin_width":profile.bin_width,
        "ms_adjustment_convention":"UNADJUSTED","ms_quality_class":quality,"ms_profile_type":"DOUBLE_DISTRIBUTION" if structure.get("detected") else "SINGLE_DISTRIBUTION",
        "ms_lifecycle":lifecycle,"ms_direction_relationship":relationship,"ms_first_distribution_low":structure.get("first_low"),
        "ms_first_distribution_high":structure.get("first_high"),"ms_second_distribution_low":structure.get("second_low"),
        "ms_second_distribution_high":structure.get("second_high"),"ms_developing_poc":profile.poc,"ms_final_poc":profile.poc,
        "ms_value_area_low":profile.value_area_low,"ms_value_area_high":profile.value_area_high,"ms_separation_low":structure.get("separation_low"),
        "ms_separation_high":structure.get("separation_high"),"ms_repair_pct":metrics["repair_pct"],"ms_acceptance_minutes":metrics["acceptance_minutes"],
        "ms_acceptance_closes":metrics["acceptance_closes"],"ms_acceptance_volume_share":metrics["volume_share"],"ms_vwap_hold_minutes":metrics["vwap_hold_minutes"],
        "ms_retest_count":metrics["retest_count"],"ms_retest_result":metrics["retest_result"],"ms_reason_code":reason})


class CanonicalMarketStructureService:
    """Persist derived evidence immutably; it never invokes a provider."""
    def __init__(self,*,registry_path:Path,payload_root:Path):
        self.registry=CanonicalRegistry(registry_path); self.registry.initialise(); self.store=AtomicPayloadStore(payload_root)
    def persist(self,evidence:Mapping[str,Any])->DatasetRecord:
        payload=json.dumps(dict(evidence),sort_keys=True,separators=(",",":"),allow_nan=False).encode(); content_hash=hashlib.sha256(payload).hexdigest()
        ticker=str(evidence["ticker"]).upper(); session=date.fromisoformat(str(evidence["session_date"])); run_id=str(evidence["run_id"])
        stored=self.store.write_bytes(Path("market_structure")/session.isoformat()/ticker/f"{content_hash}.json",payload)
        scope=DataScope(extra=(("evidence_id",str(evidence["ms_evidence_id"])),))
        dataset_id=hashlib.sha256(f"MARKET_STRUCTURE|{ticker}|{session}|{content_hash}".encode()).hexdigest()
        as_of=pd.Timestamp(evidence["ms_calculated_utc"]).to_pydatetime()
        record=DatasetRecord(dataset_id,DatasetType.MARKET_STRUCTURE,ticker,session,scope,"DERIVED",content_hash,CompletenessStatus.COMPLETE,str(stored.path),as_of,as_of,
            adjustment_convention="UNADJUSTED",schema_version=ALGORITHM_VERSION,parent_dataset_ids=tuple(evidence.get("ms_input_dataset_ids",())),source_run_id=run_id)
        self.registry.register_dataset(record); return record
