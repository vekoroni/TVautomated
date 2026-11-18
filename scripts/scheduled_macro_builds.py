"""Exchange-clock macro scheduler. --plan is read-only; --execute belongs to Windows Task Scheduler."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from avshunter.shared.xnys_calendar import is_xnys_session, session_bounds
from contracts.macro_build_budget import reserve, budget_status, build_fingerprint, finish_attempt
ET = ZoneInfo('America/New_York')


def console_creation_options():
    """Suppress Windows child consoles without changing I/O, waits or exits.

    capture_output alone redirects handles but can still create a console.
    Inherited stdout/stderr on build children must remain available to the
    scheduler wrapper's existing append-only log pipeline.
    """
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def decide(now, policy, *, changed_sources=False, moved_etfs=0, cash_observed_at=None):
    if now.tzinfo is None:
        raise ValueError('Aware clock required')
    day = now.astimezone(ET).date()
    if day.isoformat() < policy['effective_from_session'] or not is_xnys_session(day):
        return 'SKIP', 'Not an enabled XNYS session'
    opening, closing = session_bounds(day)
    pre = opening-timedelta(minutes=policy['pre_open_minutes'])
    post = closing+timedelta(minutes=policy['post_close_minutes'])
    if pre <= now < pre+timedelta(minutes=policy['pre_open_window_minutes']):
        return 'PRE_OPEN', 'Scheduled preparation'
    if post <= now < post+timedelta(minutes=policy['post_close_window_minutes']):
        return 'POST_CLOSE', 'Scheduled completed-session record'
    first_cash = opening+timedelta(minutes=policy['opening_observation_minutes'])
    check = first_cash+timedelta(minutes=policy['quote_delay_allowance_minutes'])
    if check <= now < closing:
        observed = cash_observed_at
        fresh = observed is not None and first_cash <= observed <= now and (now-observed).total_seconds()/60 <= policy['quote_max_age_minutes']
        material = moved_etfs >= policy['material_move_min_focus_etfs']
        if changed_sources:
            return 'MATERIAL_CHANGE', 'Validated research sources differ from consumed sources'
        if fresh and material:
            return ('OPEN_CHECK' if now < check+timedelta(minutes=policy['pre_open_window_minutes']) else 'MATERIAL_CHANGE'), 'Observed cash-market change'
        return 'SKIP', 'No confirmed material change; stale quotes never establish current direction'
    return 'SKIP', 'Outside build windows'


def observations(root, policy, now):
    from contracts.macro_feed_delivery import validate_feed
    accepted = json.loads((root/'data/macro/delivery/accepted.json').read_text())
    packet = json.loads((root/'dropbox/macro/macro_intelligence_latest.json').read_text(encoding='utf-8-sig'))
    consumed = packet['extras']['research_source_manifest']
    identities = {}
    changed = False
    for feed in ('usmi','news','events'):
        entry = accepted[feed]
        source = Path(entry['published_path'])
        raw = source.read_bytes()
        validate_feed(feed, json.loads(raw))
        digest = hashlib.sha256(raw).hexdigest()
        receipt = json.loads((root/'data/macro/delivery/transport_receipts'/(entry['sha256']+'.json')).read_text())
        if receipt['delivery']['status'] != 'COMPLETE':
            raise ValueError('Incomplete research receipt')
        identities[feed] = digest
        changed |= digest != consumed[feed]['sha256']
    candidates = sorted((root/'dropbox/market_data').glob('overnight_*.json'), key=lambda p:p.stat().st_mtime)
    rows = json.loads(candidates[-1].read_text()).get('groups',{}).get('us_premarket',[]) if candidates else []
    board = root/'macro_board/output/etf_macro_board.html'
    import re
    text = board.read_text(encoding='utf-8')
    start = re.search(r'(?:const|let|var) BOARD\s*=\s*',text)
    prior,_ = json.JSONDecoder().raw_decode(text[start.end():])
    old = prior.get('overnight',{}).get('groups',{}).get('us_premarket',[])
    previous = {r['symbol']:r.get('change_pct') for r in old}
    quotes, times, moves = {}, [], 0
    for row in rows:
        if row.get('symbol') not in ('SPY','QQQ','IWM','DIA') or row.get('state') != 'OK':
            continue
        stamp = datetime.fromisoformat(row['last_bar_utc'].replace('Z','+00:00'))
        value, base = row.get('change_pct'), previous.get(row['symbol'])
        if type(value) not in (int,float) or not math.isfinite(value):
            continue
        quotes[row['symbol']] = round(value / policy['material_move_percentage_points'])
        times.append(stamp)
        if type(base) in (int,float) and abs(value-base) >= policy['material_move_percentage_points']:
            moves += 1
    observed = min(times) if len(times)==4 else None
    return changed, moves, observed, {'sources':identities,'market_move_buckets':quotes}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--plan',action='store_true')
    args=parser.parse_args()
    policy=json.loads((ROOT/'config/macro_build_schedule_v1.json').read_text())
    now=datetime.now(timezone.utc)
    if json.loads((ROOT/'config/macro_delivery_v1.json').read_text())['publication_mode']!='FULL':
        print('SKIP: publication mode is not FULL');return 0
    changed,moved,observed,identity=observations(ROOT,policy,now)
    reason,note=decide(now,policy,changed_sources=changed,moved_etfs=moved,cash_observed_at=observed)
    print(json.dumps({'reason':reason,'note':note,'observed_at':now.isoformat(),'max_full_builds_per_day':4,'execute':args.execute and not args.plan}))
    if not args.execute or args.plan:
        return 0
    # A five-minute scheduler check never starts providers alongside another writer.
    command="Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='powershell.exe'\" | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match 'Run-MacroInputs.ps1|build_macro_json.py|intelligent_orchestrator.py|backfill|macro_board' } | Select-Object -ExpandProperty ProcessId"
    probe=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,text=True,**console_creation_options())
    if probe.returncode or probe.stdout.strip():
        print('DEFERRED: writer active or process inspection unavailable');return 0
    # One delayed cash snapshot after the first 15 observed minutes; no streaming poll.
    today=now.astimezone(ET).date()
    if today.isoformat() >= policy['effective_from_session'] and is_xnys_session(today):
        opening,_=session_bounds(today)
        check=opening+timedelta(minutes=policy['opening_observation_minutes']+policy['quote_delay_allowance_minutes'])
        marker=ROOT/'data/macro/delivery'/('opening_quote_check_'+today.isoformat()+'.json')
        if check <= now < check+timedelta(minutes=policy['pre_open_window_minutes']) and not marker.exists():
            marker.parent.mkdir(parents=True,exist_ok=True)
            try:
                with marker.open('x') as stream:
                    json.dump({'attempted_at':now.isoformat(),'authority':'ONE_SCHEDULED_CASH_OBSERVATION_NO_AI'},stream)
            except FileExistsError:
                pass
            else:
                subprocess.run([str(ROOT/'venv/Scripts/python.exe'),'-B',str(ROOT/'scripts/refresh_futures_snapshot.py'),'--all-market-data'],cwd=ROOT,timeout=180,**console_creation_options())
                changed,moved,observed,identity=observations(ROOT,policy,now=datetime.now(timezone.utc))
                reason,note=decide(datetime.now(timezone.utc),policy,changed_sources=changed,moved_etfs=moved,cash_observed_at=observed)
    if reason=='SKIP':
        return 0
    day=now.astimezone(ET).date().isoformat()
    state=budget_status(ROOT,day)
    if reason in ('PRE_OPEN','POST_CLOSE') and reason in state['completed_reasons']:
        print('SKIP: scheduled publication already completed');return 0
    if state['last_paid_started'] and (now-datetime.fromisoformat(state['last_paid_started'])).total_seconds()<policy['cooldown_minutes']*60:
        print('STOPPED: paid-build cooldown');return 7
    key=build_fingerprint(ROOT,reason,day)
    try:
        token=reserve(ROOT,reason=reason,key=key,now=now)
    except ValueError as exc:
        print('STOPPED: full-build budget:',exc);return 7
    env=os.environ.copy();env.update(AVSH_FULL_BUILD_ID=token,AVSH_BUILD_REASON=reason,AVSH_BUILD_FINGERPRINT=key,AVSH_BUILD_OWNER='SCHEDULED_CONTROLLER')
    local=now.astimezone(ET)
    command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'Run-MacroInputs.ps1'),'-Session','PreOpen' if reason=='PRE_OPEN' else 'PostClose','-Force']
    if reason in ('OPEN_CHECK','MATERIAL_CHANGE'):
        command+=['-AllowIntraday']
    code=subprocess.run(command,cwd=ROOT,env=env,**console_creation_options()).returncode
    finish_attempt(ROOT,token,code)
    return code

if __name__=='__main__':
    sys.exit(main())
