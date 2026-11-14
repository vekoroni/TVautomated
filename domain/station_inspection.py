"""Station inspections: isolate bounded bad observations; stop systemic corruption.

ACK amendment 13 Nov 2026: prepare_station isolates the configured market-data
checks only; inspect_station remains the strict, replayable invariant checker.

Design: Enhancements/phase7/ITEM10_CALIBRATION_AND_STATIONS_DESIGN_20261010.md. ACK's assembly line: each stage's part
is inspected right after the stage and an integrity defect is repaired there, not discovered in the Lab.

STOP checks (integrity invariants; each was zero on the healthy 8 Oct run before it was made STOP): unique and
non-blank tickers ("NAN" is a ticker), no ticker invented by a later stage, every lost ticker accounted for by the
drop-off audit, positive prices, sane quotes, a directed side equal to its governed direction, target and invalidation
on the correct sides, no timestamp in the future. REPORT checks (fill rates) never stop. Integrity only: a row-level
trade judgement is never a station defect. Enforcement is governed config (`station_inspection.enforce`).
"""
from __future__ import annotations

import json
import csv
import hashlib
import io
import math
import os
import re
from uuid import uuid4
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import pandas as pd

PRICE_COLUMNS = ("signal_price", "underlying_price", "entry_price", "stock_price")
SIDE_COLUMNS = ("direction", "options_direction", "final_direction")
FILL_RATE_COLUMNS = ("direction", "signal_price", "contract_symbol", "contract_bid", "contract_ask", "target_price",
                     "invalidation_price", "thesis__readiness", "trade_lane")


class StationDefect(RuntimeError):
    """An integrity defect at a station: the line stops here with the station, check and rows."""


def station_policy() -> Dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "config" / "governed_constants_v1.json"
    return dict(json.loads(path.read_text(encoding="utf-8-sig"))["station_inspection"])


def _text(series: pd.Series) -> pd.Series:
    return series.astype(object).where(series.notna(), "").astype(str).str.strip()


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def inspect_station(station: str, frame: pd.DataFrame, *, run_id: str, previous_tickers: Optional[Iterable[str]],
                    accounted_tickers: Optional[Iterable[str]], now_utc: Any = None,
                    policy: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    pol = dict(station_policy() if policy is None else policy)
    d = frame.loc[:, ~frame.columns.duplicated()].reset_index(drop=True)
    tickers = _text(d["ticker"]).str.upper() if "ticker" in d else pd.Series([""] * len(d))
    defects: List[Dict[str, Any]] = []

    def stop(check: str, mask: pd.Series, note: str) -> None:
        if bool(mask.any()):
            defects.append({"check": check, "count": int(mask.sum()), "note": note,
                            "tickers": sorted(set(tickers[mask].tolist()))[:50],
                            "row_indices": [int(i) for i in d.index[mask]]})

    stop("unique_tickers", tickers.duplicated(keep=False) & tickers.ne(""), "the same ticker appears more than once")
    stop("nonblank_tickers", tickers.eq(""), "a row without a ticker")
    if previous_tickers is not None:
        prev = {str(t).strip().upper() for t in previous_tickers}
        stop("no_invented_tickers", ~tickers.isin(prev) & tickers.ne(""), "a ticker the previous station never had")
        if accounted_tickers is not None:
            lost = sorted(prev - set(tickers) - {str(t).strip().upper() for t in accounted_tickers})
            if lost:
                defects.append({"check": "losses_accounted", "count": len(lost), "tickers": lost[:50],
                                "note": "tickers lost since the previous station with no drop-off record"})
    price_col = next((c for c in PRICE_COLUMNS if c in d), None)
    for reference_col in (c for c in PRICE_COLUMNS if c in d):
        px = _num(d[reference_col])
        stop("positive_prices", _text(d[reference_col]).ne("") &
             (px.isna() | px.isin([float('inf'),float('-inf')]) | (px <= 0)),
             f"{reference_col} not finite and positive")
    if "contract_bid" in d and "contract_ask" in d:
        bid, ask = _num(d["contract_bid"]), _num(d["contract_ask"])
        invalid = (_text(d['contract_bid']).ne('') & (bid.isna() | bid.isin([float('inf'),float('-inf')]))) | \
                  (_text(d['contract_ask']).ne('') & (ask.isna() | ask.isin([float('inf'),float('-inf')])))
        stop("sane_quotes", invalid | (bid < 0) | (ask < 0) | (bid.notna() & ask.notna() & (bid > ask)),
             "nonfinite, negative or crossed quote")
    side_col = next((c for c in SIDE_COLUMNS if c in d), None)
    if side_col:
        side = _text(d[side_col]).str.upper()
        if "governed_direction" in d:
            gov = _text(d["governed_direction"]).str.upper()
            stop("side_matches_governed_direction", side.isin(["CALL", "PUT"]) & gov.isin(["CALL", "PUT"]) & side.ne(gov),
                 f"{side_col} differs from the governed direction record")
        if price_col and "target_price" in d and "invalidation_price" in d:
            px, tg, iv = _num(d[price_col]), _num(d["target_price"]), _num(d["invalidation_price"])
            both = px.notna() & tg.notna() & iv.notna()
            bad = (side.eq("CALL") & both & ~((iv < px) & (px < tg))) | (side.eq("PUT") & both & ~((tg < px) & (px < iv)))
            stop("levels_on_correct_sides", bad, "target or invalidation on the wrong side of the reference price")
    now = pd.Timestamp(now_utc) if now_utc is not None else pd.Timestamp.now(tz="UTC")
    now = now.tz_localize("UTC") if now.tzinfo is None else now
    horizon = now + pd.Timedelta(minutes=float(pol.get("future_tolerance_minutes", 15)))
    for col in [c for c in d.columns if str(c).endswith(("_timestamp_utc", "_at_utc"))]:
        ts = pd.to_datetime(d[col], errors="coerce", utc=True)
        stop("no_future_timestamps", ts > horizon, f"{col} later than the inspection time")
    stop_checks = set(pol.get("stop_checks") or [])
    stop_defects = [x for x in defects if x["check"] in stop_checks]
    return {"station": station, "run_id": run_id, "rows": int(len(d)), "inspected_at_utc": now.isoformat(),
            "stop_defects": stop_defects, "other_defects": [x for x in defects if x["check"] not in stop_checks],
            "report": {"fill_rates": {c: round(float(_text(d[c]).ne("").mean()), 4) if len(d) else None
                                      for c in FILL_RATE_COLUMNS if c in d}},
            "enforce": bool(pol.get("enforce", True))}


def enforce(report: Mapping[str, Any], policy: Optional[Mapping[str, Any]] = None) -> None:
    pol = dict(station_policy() if policy is None else policy)
    if not pol.get("enforce", True) or not report.get("stop_defects"):
        return
    detail = "; ".join(f"{d['check']} x{d['count']} ({', '.join(d['tickers'][:5])})" for d in report["stop_defects"])
    raise StationDefect(f"STATION_INTEGRITY_DEFECT at {report['station']} (run {report['run_id']}): {detail}")


def write_station_report(report: Mapping[str, Any], run_dir: Path | str) -> Path:
    path = Path(run_dir) / "diagnostics" / f"station_{report['station']}_{report['run_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return path


def prepare_station(station, frame, *, run_id, previous_tickers, accounted_tickers,
                    now_utc=None, policy=None, prior_quarantined=()):
    """Isolate bounded market-data defects; every other invariant stays STOP.

    Pure: no file, database, provider or policy/valuation writes. The original
    strict inspection is retained as input_report. The producer must commit the
    preimage/receipt and filtered delivery before passing it to another stage.
    """
    pol=station_policy() if policy is None else dict(policy)
    data=frame.reset_index(drop=True)
    prior={str(t).strip().upper() for t in prior_quarantined}
    # Prior verified exclusions are known identities, not newly invented names.
    inspection_previous=None if previous_tickers is None else set(previous_tickers)|prior
    raw=inspect_station(station,data,run_id=run_id,previous_tickers=inspection_previous,
        accounted_tickers=accounted_tickers,now_utc=now_utc,policy=pol)
    q=pol.get('quarantine') or {}
    raw.update(input_rows=len(data),quarantine={'state':'NONE','tickers':[],'records':[],'row_indices':[]})
    if not q.get('enabled') or not pol.get('enforce',True):return data.copy(),raw
    allowed=set(q['checks']);bad=set()
    for defect in raw['stop_defects']:
        if defect['check'] in allowed:bad.update(defect.get('row_indices',[]))
    tickers=_text(data['ticker']).str.upper() if 'ticker' in data else pd.Series(['']*len(data))
    # Once quarantined in this run, a later producer cannot resurrect a ticker.
    bad.update(int(i) for i in data.index[tickers.isin(prior)])
    if not bad:return data.copy(),raw
    # Only wrong-side geometry on the already invalid-price row may be secondary.
    for defect in raw['stop_defects']:
        if defect['check'] not in allowed:
            if not (defect['check']=='levels_on_correct_sides' and
                    set(defect.get('row_indices',[])) and set(defect['row_indices'])<=bad):
                return data.copy(),raw
    affected=set(tickers.iloc[sorted(bad)])
    limit=min(int(q['max_tickers_per_station']),max(1,math.floor(len(data)*float(q['max_fraction_per_station']))))
    if (len(affected)>limit or len(affected|prior)>int(q['max_tickers_per_run']) or len(bad)>=len(data)):
        raw['stop_defects'].append({'check':'systemic_market_data_failure','count':len(affected),
            'tickers':sorted(affected),'note':f'Quarantine limit exceeded or no valid rows; station limit={limit}'})
        raw['quarantine']['state']='STOPPED_SYSTEMIC'
        return data.copy(),raw
    # Never choose one copy of a duplicate identity: strict inspection above stops it.
    records=[]
    for i in sorted(bad):
        checks=sorted({x['check'] for x in raw['stop_defects'] if i in x.get('row_indices',[])})
        if tickers.iloc[i] in prior:checks.append('PREVIOUSLY_QUARANTINED_IN_RUN')
        records.append({'ticker':tickers.iloc[i],'source_row_ordinal':i,'checks':checks})
    clean=data.drop(index=sorted(bad)).reset_index(drop=True)
    report=inspect_station(station,clean,run_id=run_id,previous_tickers=previous_tickers,
        accounted_tickers=set(accounted_tickers or ())|affected|prior,now_utc=now_utc,policy=pol)
    report.update(input_rows=len(data),input_report=raw,
        quarantine={'state':'PREPARED_NOT_COMMITTED','tickers':sorted(affected),'records':records,'row_indices':sorted(bad)})
    return clean,report


def station_quarantines(run_dir):
    """Verified, complete unique ticker/station/reason list; fail on uncertain receipts."""
    folder=Path(run_dir)/'diagnostics';records=[]
    for path in sorted(folder.glob('station_quarantine_*.json')):
        receipt=json.loads(path.read_text(encoding='utf-8'))
        preimage=(folder/receipt['preimage_file']).resolve()
        if (receipt.get('state')!='COMMITTED' or not preimage.is_relative_to(folder.resolve())
                or hashlib.sha256(preimage.read_bytes()).hexdigest()!=receipt['preimage_sha256']):
            raise ValueError('QUARANTINE_RECEIPT_OR_PREIMAGE_INVALID')
        for record in receipt['records']:
            records.append({**record,'station':receipt['station'],'run_id':receipt['run_id']})
    return records


def quarantine_lifecycle_rows(rows, records):
    """One disposition per input remains; quarantines never enter Packages worklists."""
    excluded={r['ticker']:r for r in records if r['station']=='discovery'}
    present={str(r.get('ticker','')).strip().upper() for r in rows}
    if set(excluded)-present:raise ValueError('QUARANTINE_MISSING_FROM_DISCOVERY_LIFECYCLE')
    output=[]
    for row in rows:
        out=dict(row);ticker=str(row.get('ticker','')).strip().upper()
        if ticker in excluded:
            out.update(outcome='DROP',lifecycle_state='DROPPED_TERMINAL_DATA',
                reason_code='STATION_QUARANTINE:'+','.join(excluded[ticker]['checks']),next_stage='')
        output.append(out)
    return output


def commit_station_quarantine(output_path, frame, report, run_dir):
    """Commit a just-produced, not-yet-accepted delivery, retaining exact raw bytes.

    No canonical DB, historical bar or earlier run is edited. A durable preimage
    and receipt are required before returning success. Any I/O failure propagates
    and stops the caller. This is not a general-purpose historical repair tool.
    """
    q=report['quarantine']
    if not q['records']:return
    enforce(report)
    path=Path(output_path);folder=Path(run_dir)/'diagnostics'
    for token in (report['station'],report['run_id']):
        if not re.fullmatch(r'[A-Za-z0-9_-]+',token):raise ValueError('Invalid quarantine identity')
    raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    bad=set(q['row_indices']);text=raw.decode('utf-8-sig')
    if path.suffix.lower()=='.json':
        payload=json.loads(text);rows=payload if isinstance(payload,list) else payload['rows']
        if len(rows)!=len(frame):raise ValueError('QUARANTINE_SOURCE_ROW_COUNT_CHANGED')
        if not pd.DataFrame(rows).reset_index(drop=True).equals(frame.reset_index(drop=True)):
            raise ValueError('QUARANTINE_SOURCE_VALUES_CHANGED_SINCE_INSPECTION')
        kept=[r for i,r in enumerate(rows) if i not in bad]
        if isinstance(payload,list):payload=kept
        else:
            payload['rows']=kept;payload['candidate_count']=len(kept)
            payload['station_quarantine']={'excluded_tickers':q['tickers'],'source_sha256':digest}
            if isinstance(payload.get('verdict_counts'),dict):
                payload['verdict_counts']={v:sum(r.get('lab_verdict')==v for r in kept)
                    for v in payload['verdict_counts']}
            if isinstance(payload.get('reconciliation'),dict):
                source_reconciliation=dict(payload['reconciliation'])
                payload['pre_quarantine_source_reconciliation']=source_reconciliation
                payload['reconciliation']={**source_reconciliation,'input_rows':len(rows),
                    'output_rows':len(kept),'quarantined_rows':len(bad),
                    'population_reconciled_with_quarantine':len(rows)==len(kept)+len(bad),
                    'evidence_coverage_counts_basis':'SOURCE_BEFORE_STATION_QUARANTINE'}
        delivered=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode('utf-8')
    else:
        old=csv.field_size_limit();csv.field_size_limit(max(old,64*1024*1024))
        try:
            source=csv.reader(io.StringIO(text,newline=''));header=next(source);rows=list(source)
            if len(rows)!=len(frame):raise ValueError('QUARANTINE_SOURCE_ROW_COUNT_CHANGED')
            reread=pd.read_csv(io.StringIO(text),dtype=str,keep_default_na=False,na_values=[''],low_memory=False)
            # Accept equivalent empty-cell representations, never changed facts.
            if (list(reread.columns)!=list(frame.columns) or
                    not reread.fillna('').astype(str).equals(frame.reset_index(drop=True).fillna('').astype(str))):
                raise ValueError('QUARANTINE_SOURCE_VALUES_CHANGED_SINCE_INSPECTION')
            out=io.StringIO(newline='');writer=csv.writer(out);writer.writerow(header)
            writer.writerows(r for i,r in enumerate(rows) if i not in bad)
            delivered=out.getvalue().encode('utf-8')
        finally:csv.field_size_limit(old)
    folder.mkdir(parents=True,exist_ok=True)
    preimage=folder/f'quarantine_preimage_{report["station"]}_{digest}{path.suffix}'
    if preimage.exists():
        if preimage.read_bytes()!=raw:raise ValueError('QUARANTINE_PREIMAGE_CONFLICT')
    else:
        with preimage.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    receipt={**q,'state':'PREPARED','run_id':report['run_id'],'station':report['station'],
        'source_path':str(path.resolve()),'input_rows':len(frame),'accepted_rows':len(frame)-len(bad),
        'preimage_file':preimage.name,'preimage_sha256':digest,
        'delivery_sha256':hashlib.sha256(delivered).hexdigest()}
    receipt_path=folder/f'station_quarantine_{report["station"]}_{report["run_id"]}.json'
    if receipt_path.exists():raise ValueError('QUARANTINE_RECEIPT_ALREADY_EXISTS_DO_NOT_RETRY')
    # Durable intent exists before replacement. A crash leaves a receipt + exact
    # preimage, never an unexplained loss. Re-entry requires a clean inspection.
    with receipt_path.open('x',encoding='utf-8') as stream:
        json.dump(receipt,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    temp=path.with_name(path.name+'.quarantine-'+uuid4().hex+'.tmp')
    with temp.open('xb') as stream:stream.write(delivered);stream.flush();os.fsync(stream.fileno())
    if path.read_bytes()!=raw:raise ValueError('QUARANTINE_SOURCE_CHANGED_DURING_COMMIT')
    os.replace(temp,path)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=receipt['delivery_sha256']:
        raise ValueError('QUARANTINE_DELIVERY_VERIFICATION_FAILED')
    receipt['state']='COMMITTED'
    receipt_temp=receipt_path.with_name(receipt_path.name+'.'+uuid4().hex+'.tmp')
    with receipt_temp.open('x',encoding='utf-8') as stream:
        json.dump(receipt,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    os.replace(receipt_temp,receipt_path)
    q.update(state='COMMITTED',preimage_file=preimage.name,receipt_file=receipt_path.name,
        source_sha256=digest,delivery_sha256=receipt['delivery_sha256'])
