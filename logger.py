"""PostgreSQL logger. Live VM measurements with saved alarm thresholds."""
import argparse
import csv
import socket
import time
from concurrent.futures import ThreadPoolExecutor
import requests
from psycopg.rows import dict_row
import psycopg
from monitor_common import (FOLDER, NODES, RESOURCES, LIMITS, LEVELS, INTERVAL,
                            TIMEOUT, FAILURE_LIMIT, classify, availability_severity,
                            connect, utcnow, refresh_limits)
from upgrade_db import upgrade

FIELDS = ['checked_at','node','status','cpu','ram','disk','consecutive_failures',
          'cpu_severity','ram_severity','disk_severity','source']

def fetch_metrics(node, ip):
    try:
        with requests.Session() as session:
            session.trust_env = False
            # Independent host checker validates health before collecting measurements.
            health = session.get(f'http://{ip}:5123/health', timeout=TIMEOUT)
            health.raise_for_status()
            healthy = health.json()
            if not isinstance(healthy, dict) or healthy.get('node') != node or healthy.get('status') not in ('ok', 'online'):
                raise ValueError(f'Invalid health response from {node}')
            response = session.get(f'http://{ip}:5123/api/metrics', timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict) or data.get('node') != node:
            raise ValueError(f'Expected metrics from {node}')
        if any(isinstance(data[r], bool) for r in RESOURCES):
            raise ValueError('Metric percentages cannot be booleans')
        metrics = {r: float(data[r]) for r in RESOURCES}
        for r, value in metrics.items():
            classify(r, value)
        return utcnow(), metrics, None
    except (requests.RequestException, ValueError, KeyError, TypeError, OverflowError) as e:
        return utcnow(), None, str(e)

def restore_state(db, source):
    states = {}
    for node in NODES:
        saved = db.execute('SELECT * FROM node_state WHERE node=%s AND source=%s', (node,source)).fetchone()
        latest = db.execute('SELECT * FROM readings WHERE node=%s AND source=%s ORDER BY id DESC LIMIT 1', (node,source)).fetchone()
        if saved and (not latest or saved['checked_at'] >= latest['checked_at']):
            states[node] = dict(saved)
            continue
        success = db.execute("SELECT checked_at FROM readings WHERE node=%s AND source=%s AND status='REACHABLE' ORDER BY id DESC LIMIT 1", (node,source)).fetchone()
        state = dict(node=node,source=source,status=latest['status'] if latest else 'UNKNOWN',
                     consecutive_failures=latest['consecutive_failures'] if latest else 0,
                     checked_at=latest['checked_at'] if latest else None,
                     last_seen=success['checked_at'] if success else None,
                     first_failure_at=None,recovery_at=None,last_outage_at=None,error=None)
        for r in RESOURCES:
            # A failed reading has no metric. Restore last known level instead.
            m = db.execute(f'SELECT {r} FROM readings WHERE node=%s AND source=%s AND {r} IS NOT NULL ORDER BY id DESC LIMIT 1',(node,source)).fetchone()
            state[r+'_severity'] = classify(r,m[r]) if m else None
        states[node] = state
    return states

def transition(state, checked_at, metrics, error):
    """Pure state calculation; callers apply it only after a successful commit."""
    next_state = dict(state)
    if error is None:
        status, failures = 'REACHABLE', 0
        if state['consecutive_failures']:
            next_state['recovery_at'] = checked_at
        next_state['last_seen'] = checked_at
        next_state['first_failure_at'] = None
    else:
        failures = state['consecutive_failures'] + 1
        status = 'UNAVAILABLE' if failures >= FAILURE_LIMIT else 'RETRYING'
        if not state['first_failure_at']:
            # On upgrade, the beginning of an existing outage is unknown.
            # This is the first observed failure under the new logger.
            next_state['first_failure_at'] = checked_at
        if status == 'UNAVAILABLE' and state['status'] != 'UNAVAILABLE':
            next_state['last_outage_at'] = next_state['first_failure_at']
    changes=[]
    if metrics is not None:
        for r in RESOURCES:
            level=classify(r,metrics[r]); old=state[r+'_severity']
            if level != old:
                event = 'INITIAL' if old is None and level=='NORMAL' else 'RECOVERED' if old and LEVELS.index(level)<LEVELS.index(old) else 'ALERT'
                # A descending transition's boundary is the level being left.
                threshold_level = old if event == 'RECOVERED' else level
                rank=LEVELS.index(threshold_level) if threshold_level else 0
                boundary = LIMITS[r][rank-1] if rank else 0
                changes.append((r,event,metrics[r],boundary,old,level))
            next_state[r+'_severity']=level
    next_state.update(status=status,consecutive_failures=failures,checked_at=checked_at,error=error)
    return next_state, changes

def append_csv(row, source):
    # Versioned path avoids mixing a new header with the old readings.csv.
    path=FOLDER / 'readings_v2.csv'
    header=not path.exists() or path.stat().st_size==0
    with path.open('a',newline='',encoding='utf-8') as f:
        w=csv.writer(f)
        if header: w.writerow(FIELDS)
        w.writerow([v.isoformat() if hasattr(v,'isoformat') else v for v in row])

def save_check(db,node,state,checked_at,metrics,error):
    next_state, changes=transition(state,checked_at,metrics,error)
    source=state['source']; status=next_state['status']
    levels=[classify(r,metrics[r]) if metrics else None for r in RESOURCES]
    row=(checked_at,node,status,*[metrics[r] if metrics else None for r in RESOURCES],
         next_state['consecutive_failures'],*levels,source)
    with db.transaction():
        db.execute('''INSERT INTO readings (checked_at,node,status,cpu,ram,disk,
            consecutive_failures,cpu_severity,ram_severity,disk_severity,source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', row)
        if status != state['status']:
            db.execute('''INSERT INTO events (checked_at,node,previous_status,new_status,
                severity,last_seen,first_failure_at,recovery_at,source)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (checked_at,node,state['status'],status,availability_severity(status),
                 next_state['last_seen'] if error else state['last_seen'],
                 next_state['first_failure_at'] if error else state['first_failure_at'],
                 next_state['recovery_at'],source))
        for r,event,value,boundary,old,level in changes:
            db.execute('''INSERT INTO alerts (checked_at,node,resource,state,value,
                threshold,previous_severity,severity,source)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (checked_at,node,r,event,value,boundary,old,level,source))
        cols=['node','source','status','consecutive_failures','checked_at','last_seen',
              'first_failure_at','recovery_at','last_outage_at','error',
              'cpu_severity','ram_severity','disk_severity']
        db.execute('INSERT INTO node_state ('+','.join(cols)+') VALUES ('+
                   ','.join(['%s']*len(cols))+') ON CONFLICT(node,source) DO UPDATE SET '+
                   ','.join(c+'=EXCLUDED.'+c for c in cols[2:]),tuple(next_state[c] for c in cols))
    state.update(next_state)
    try:
        append_csv(row,source)
    except (OSError,csv.Error) as e:
        print(f'CSV warning: {e}; reading retained in PostgreSQL.',flush=True)
    detail=' '.join(f'{r.upper()}={metrics[r]:.1f}%/{classify(r,metrics[r])}' for r in RESOURCES) if metrics else error
    print(f'{source} | {node} | {status} | {detail} | SAVED',flush=True)
    for r,event,value,boundary,old,level in changes:
        print(f'  {r.upper()}: {old or "UNKNOWN"} -> {level} | {event}',flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    args=parser.parse_args()
    lock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
        lock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    try:
        lock.bind(('127.0.0.1',5125));lock.listen(1)
    except OSError:
        lock.close();print('Port 5125 occupied. Stop the other logger first.');return 1
    source='LIVE'
    try:
        with connect(rows=dict_row) as db:
            upgrade(db)
            refresh_limits()
            states=restore_state(db,source)
            print(f'PostgreSQL connected | mode={source} | Ctrl+C to stop',flush=True)
            print('The SIS 3.3: live VM measurements. Adjust alarm boundaries through Settings.', flush=True)
            with ThreadPoolExecutor(max_workers=len(NODES)) as pool:
                while True:
                    started=time.monotonic()
                    refresh_limits()
                    futures={n:pool.submit(fetch_metrics,n,ip) for n,ip in NODES.items()}
                    for n,f in futures.items(): save_check(db,n,states[n],*f.result())
                    time.sleep(max(0,INTERVAL-(time.monotonic()-started)))
    except KeyboardInterrupt:
        print('Logger stopped. Committed history retained.')
    except (psycopg.Error, OSError, ValueError) as e:
        print(f'Logger error: {e}\nLogger stopped; check PostgreSQL, threshold_settings.json and restart.');return 1
    finally:
        lock.close()
    return 0

if __name__=='__main__':
    raise SystemExit(main())
