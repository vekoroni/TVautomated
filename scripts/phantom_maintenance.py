"""Incremental local Greek completion and durable IV-work receipts.

No provider calls. Raw ingestion and these receipts share the caller transaction.
IV work is drained only after that transaction commits. Failed IV work remains
pending and visible rather than being mistaken for completed maintenance.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sqlite3

try:
    from .options_db_writer import ensure_computed_greeks_schema, upsert_greek_records, hydrate_chain_snapshots
    from .phantom_compute_historical_greeks import compute_record
except ImportError:
    from options_db_writer import ensure_computed_greeks_schema, upsert_greek_records, hydrate_chain_snapshots
    from phantom_compute_historical_greeks import compute_record

GREEKS = ('iv','delta','gamma','theta','vega')
KEY = ('ticker','quote_date','option_symbol')
MODEL_RATE = 0.045
RATE_POLICY = 'FIXED_MODEL_ASSUMPTION_NOT_HISTORICAL_RATE_OBSERVATION'

def now():
    return datetime.now(timezone.utc).isoformat()

def finite(value):
    try:
        return value is not None and math.isfinite(float(value))
    except (ValueError,TypeError):
        return False

def ensure_schema(c):
    ensure_computed_greeks_schema(c)
    c.execute('''CREATE TABLE IF NOT EXISTS phantom_row_lineage(
       ticker TEXT NOT NULL,quote_date TEXT NOT NULL,option_symbol TEXT NOT NULL,
       input_hash TEXT NOT NULL,field_sources_json TEXT NOT NULL,
       underlying_quality TEXT NOT NULL,rate_policy TEXT,updated_at_utc TEXT NOT NULL,
       PRIMARY KEY(ticker,quote_date,option_symbol))''')
    c.execute('''CREATE TABLE IF NOT EXISTS phantom_maintenance_pairs(
       ticker TEXT NOT NULL,quote_date TEXT NOT NULL,status TEXT NOT NULL,
       updated_at_utc TEXT NOT NULL,last_error TEXT,attempts INTEGER NOT NULL DEFAULT 0,
       PRIMARY KEY(ticker,quote_date))''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_phantom_maintenance_status ON phantom_maintenance_pairs(status,quote_date,ticker)')
    c.execute('''CREATE TABLE IF NOT EXISTS phantom_pair_health(ticker TEXT,quote_date TEXT,
       chain_rows INTEGER,needs_greeks INTEGER,incomplete_greeks INTEGER,missing_underlying INTEGER,
       updated_at_utc TEXT,PRIMARY KEY(ticker,quote_date))''')

def _row(c, key):
    cur=c.execute('SELECT * FROM chain_snapshots WHERE ticker=? AND quote_date=? AND option_symbol=?',key)
    row=cur.fetchone()
    return dict(zip([d[0] for d in cur.description],row)) if row is not None else None

def input_field_sources(incoming):
    try:
        raw=json.loads(incoming.get('raw_json') or '{}')
    except (TypeError,ValueError):
        raw={}
    if not isinstance(raw,dict): raw={}
    provider=str(incoming.get('source') or '').upper()
    vendor=provider in {'MARKETDATA','MARKETDATA.APP','MARKETDATA_OPTIONS_QUOTES','MARKETDATA_CACHED'}
    result={}
    for name in GREEKS:
        hint=str(incoming.get(name+'_source') or raw.get(name+'_source') or
           (raw.get('implied_vol_source') if name=='iv' else '') or
           incoming.get('greeks_source') or raw.get('greeks_source') or '').upper()
        if any(token in hint for token in ('COMPUTED','BSM','SOLVED','BLACK_SCHOLES')):
            result[name]='COMPUTED_BS'
        elif hint and 'VENDOR' not in hint and not hint.startswith('MARKETDATA'):
            result[name]=hint
        else:
            result[name]='MARKETDATA_VENDOR' if vendor else 'PROVIDER_UNVERIFIED'
    return result

def complete_greeks_and_queue_iv(c, rows):
    """Complete only exact written contracts; preserve existing measured values."""
    if not rows:
        return {'changed':0,'computed':0}
    ensure_schema(c)
    changed=computed=0
    touched=set()
    for incoming in rows:
        key=tuple(incoming[k] for k in KEY)
        row=_row(c,key)
        if row is None:
            raise ValueError('Maintenance cannot invent a missing chain identity')
        signature={k:incoming.get(k) for k in (*KEY,'underlying_price','strike','dte','side','bid','ask','mid','last','source',*GREEKS)}
        incoming_sources=input_field_sources(incoming)
        signature['field_sources']=incoming_sources
        digest=hashlib.sha256(json.dumps(signature,sort_keys=True,default=str,allow_nan=True).encode()).hexdigest()
        prior=c.execute('SELECT input_hash,field_sources_json FROM phantom_row_lineage WHERE ticker=? AND quote_date=? AND option_symbol=?',key).fetchone()
        if prior and prior[0]==digest:
            continue
        vendor=str(incoming.get('source') or '').upper() in {'MARKETDATA','MARKETDATA.APP','MARKETDATA_OPTIONS_QUOTES','MARKETDATA_CACHED'}
        sources=json.loads(prior[1]) if prior else {}
        for name in GREEKS:
            if finite(incoming.get(name)):
                sources[name]=incoming_sources[name]
            elif finite(row.get(name)):
                sources.setdefault(name,str(row.get('greeks_source') or 'EXISTING_UNVERIFIED'))
        missing=[name for name in GREEKS if not finite(row.get(name))]
        if missing:
            record=compute_record(row,MODEL_RATE)
            record['quality_flags']=';'.join(filter(None,[record.get('quality_flags'),RATE_POLICY]))
            upsert_greek_records(c,[record])
            hydrate_chain_snapshots(c,[record])
            computed+=1
            if str(record.get('quality_status','')).startswith('OK'):
                for name in missing:
                    if finite(record.get(name)):
                        sources[name]='COMPUTED_BS'
        values=set(sources.values())
        label=next(iter(values)) if len(values)==1 else 'MIXED_FIELD_SOURCES' if values else None
        if label:
            c.execute('UPDATE chain_snapshots SET greeks_source=? WHERE ticker=? AND quote_date=? AND option_symbol=?',(label,*key))
        if all(finite(incoming.get(g)) and incoming_sources[g]=='MARKETDATA_VENDOR' for g in GREEKS):
            c.execute("UPDATE chain_snapshots SET greeks_quality='VENDOR_COMPLETE',greeks_updated_at_utc=? WHERE ticker=? AND quote_date=? AND option_symbol=?",(now(),*key))
        underlying='PRESENT' if finite(row.get('underlying_price')) and float(row['underlying_price'])>0 else 'MISSING_OR_INVALID_NOT_FILLED'
        c.execute('''INSERT INTO phantom_row_lineage VALUES(?,?,?,?,?,?,?,?)
          ON CONFLICT(ticker,quote_date,option_symbol) DO UPDATE SET input_hash=excluded.input_hash,
          field_sources_json=excluded.field_sources_json,underlying_quality=excluded.underlying_quality,
          rate_policy=excluded.rate_policy,updated_at_utc=excluded.updated_at_utc''',
          (*key,digest,json.dumps(sources,sort_keys=True),underlying,RATE_POLICY if missing else None,now()))
        c.execute('''INSERT INTO phantom_maintenance_pairs(ticker,quote_date,status,updated_at_utc)
          VALUES(?,?,'PENDING_IV',?) ON CONFLICT(ticker,quote_date) DO UPDATE SET
          status='PENDING_IV',updated_at_utc=excluded.updated_at_utc,last_error=NULL''',(*key[:2],now()))
        changed+=1
        touched.add(key[:2])
    for ticker,day in touched:
        refresh_pair_health(c,ticker,day)
    return {'changed':changed,'computed':computed}

def refresh_pair_health(c,ticker,day):
    counts=c.execute('''SELECT COUNT(*),
      COALESCE(SUM((c.iv IS NULL OR c.delta IS NULL OR c.gamma IS NULL OR c.theta IS NULL OR c.vega IS NULL)
                    AND g.contract_symbol IS NULL),0),
      COALESCE(SUM(c.iv IS NULL OR c.delta IS NULL OR c.gamma IS NULL OR c.theta IS NULL OR c.vega IS NULL),0),
      COALESCE(SUM(c.underlying_price IS NULL OR c.underlying_price<=0),0)
      FROM chain_snapshots c LEFT JOIN options_greeks_history g
       ON g.ticker=c.ticker AND g.snapshot_date=c.quote_date AND g.contract_symbol=c.option_symbol
      WHERE c.ticker=? AND c.quote_date=?''',(ticker,day)).fetchone()
    c.execute('''INSERT INTO phantom_pair_health VALUES(?,?,?,?,?,?,?)
      ON CONFLICT(ticker,quote_date) DO UPDATE SET chain_rows=excluded.chain_rows,
      needs_greeks=excluded.needs_greeks,incomplete_greeks=excluded.incomplete_greeks,
      missing_underlying=excluded.missing_underlying,updated_at_utc=excluded.updated_at_utc''',
      (ticker,day,*counts,now()))

def session_health(db_path,day,tickers):
    """Indexed coverage plus persisted per-pair Greek counts; never scan history."""
    path=Path(db_path)
    if not path.is_file():
        return {'state':'MISSING','latest':None,'lag_sessions':None}
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=30) as c:
        has_health=c.execute("SELECT 1 FROM sqlite_master WHERE name='phantom_pair_health'").fetchone()
        has_queue=c.execute("SELECT 1 FROM sqlite_master WHERE name='phantom_maintenance_pairs'").fetchone()
        has_audit=c.execute("SELECT 1 FROM sqlite_master WHERE name='backfill_audit'").fetchone()
        no_data={r[0] for r in c.execute("SELECT ticker FROM backfill_audit WHERE quote_date=? AND status='NO_DATA'",(day,))} if has_audit else set()
        present=missing=unassessed=needs=incomplete=resolved_no_data=0
        for ticker in sorted(set(tickers)):
            exists=c.execute('SELECT 1 FROM chain_snapshots WHERE ticker=? AND quote_date=? LIMIT 1',(ticker,day)).fetchone()
            if not exists:
                if ticker in no_data: resolved_no_data+=1
                else: missing+=1
                continue
            present+=1
            h=c.execute('SELECT needs_greeks,incomplete_greeks FROM phantom_pair_health WHERE ticker=? AND quote_date=?',(ticker,day)).fetchone() if has_health else None
            if h is None:
                unassessed+=1
            else:
                needs+=h[0]; incomplete+=h[1]
        pending=c.execute("SELECT COUNT(*) FROM phantom_maintenance_pairs WHERE status='PENDING_IV'").fetchone()[0] if has_queue else 0
        unavailable=c.execute("SELECT COUNT(*) FROM phantom_maintenance_pairs WHERE status='IV_UNAVAILABLE' AND quote_date=?",(day,)).fetchone()[0] if has_queue else 0
    state='NEEDS_GREEKS' if needs else 'NEEDS_AUDIT' if unassessed else 'PENDING_IV' if pending else 'INCOMPLETE_COVERAGE' if missing else 'FRESH'
    return {'state':state,'latest':day,'lag_sessions':0,'expected_tickers':len(set(tickers)),
      'tickers_with_chains':present,'tickers_without_chains':missing,'audited_no_data_tickers':resolved_no_data,
      'no_data_scope':'Request-scoped result, not proof that a ticker has no listed options',
      'unassessed_ticker_sessions':unassessed,
      'needs_greeks_rows':needs if not unassessed else None,'known_needs_greeks_rows':needs,
      'known_incomplete_greek_rows':incomplete,'pending_iv_pairs':pending,'iv_unavailable_pairs':unavailable}

def cache_path_for(db_path):
    path=Path(db_path)
    return path.parent.parent/'cache/iv_history_cache.db' if path.parent.name=='phantom' else path.parent/'iv_history_cache.db'

def drain_pending(db_path, iv_cache_path=None, *, max_pairs=500, min_free_gib=15):
    """Finish committed IV work in bounded batches. No whole-history scan."""
    try:
        from .finalize_phantom_weekly_snapshot import derive_iv_history
    except ImportError:
        from finalize_phantom_weekly_snapshot import derive_iv_history
    db_path=Path(db_path)
    cache=Path(iv_cache_path) if iv_cache_path else cache_path_for(db_path)
    cache.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(db_path,timeout=60) as c:
        exists=c.execute("SELECT 1 FROM sqlite_master WHERE name='phantom_maintenance_pairs'").fetchone()
        if not exists:
            return {'status':'NO_PENDING_WORK','pairs':0}
        pairs=c.execute("SELECT ticker,quote_date FROM phantom_maintenance_pairs WHERE status='PENDING_IV' ORDER BY quote_date,ticker LIMIT ?",(max_pairs,)).fetchall()
        if not pairs:
            return {'status':'NO_PENDING_WORK','pairs':0}
        c.execute('''CREATE TABLE IF NOT EXISTS iv_surface_history(ticker TEXT NOT NULL,quote_date TEXT NOT NULL,
          dte_bucket TEXT NOT NULL,side TEXT NOT NULL,contract_count INTEGER,atm_iv REAL,median_iv REAL,iv_entropy REAL,
          skew_25d REAL,put_call_iv_spread REAL,median_spread_pct REAL,total_open_interest INTEGER,total_volume INTEGER,
          created_at_utc TEXT,PRIMARY KEY(ticker,quote_date,dte_bucket,side))''')
    with sqlite3.connect(cache,timeout=60) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS iv_history(ticker TEXT,sample_date TEXT,atm_iv REAL,source TEXT,updated_at TEXT,
          PRIMARY KEY(ticker,sample_date))''')
        c.execute('CREATE TABLE IF NOT EXISTS iv_cache_meta(ticker TEXT PRIMARY KEY,last_full_build TEXT,last_refresh TEXT)')
    groups=defaultdict(list)
    for ticker,day in pairs:
        groups[day].append(ticker)
    reports=[]
    for day,tickers in sorted(groups.items()):
        for start in range(0,len(tickers),50):
            selected=tickers[start:start+50]
            if shutil.disk_usage(db_path.parent).free < min_free_gib*1024**3:
                raise RuntimeError('IV maintenance stopped at disk reserve; pending receipts retained')
            report=derive_iv_history(db_path,cache,day,selected,execute=True)
            # PASS requires actual chain rows; invalid-IV populations are an
            # explicit terminal quality state, not silently pending forever.
            with sqlite3.connect(db_path,timeout=60) as c:
                updates=[]
                for ticker in selected:
                    valid=c.execute('''SELECT 1 FROM chain_snapshots WHERE ticker=? AND quote_date=?
                        AND iv BETWEEN 0.01 AND 5.0 AND underlying_price>0 AND strike>0 LIMIT 1''',(ticker,day)).fetchone()
                    status='COMPLETE' if valid else 'IV_UNAVAILABLE'
                    updates.append((status,now(),None if valid else 'NO_VALID_ATM_INPUT',ticker,day))
                c.executemany('''UPDATE phantom_maintenance_pairs SET status=?,updated_at_utc=?,last_error=?,attempts=attempts+1
                   WHERE ticker=? AND quote_date=?''',updates)
            reports.append(report)
    return {'status':'FINISHED_BOUNDED_BATCH','pairs':len(pairs),'reports':reports}
