"""Read-only installation and connectivity check. Never changes database history."""
from pathlib import Path
from urllib.request import urlopen
import json
from monitor_common import connect, NODES, refresh_limits

passed=failed=0

def check(name, action):
    global passed, failed
    try:
        result=action()
        print(f'OK   {name}: {result}')
        passed+=1
    except Exception as error:
        print(f'FAIL {name}: {error}')
        failed+=1

def database():
    with connect(readonly=True) as db:
        name=db.execute('SELECT current_database()').fetchone()[0]
        for table in ('readings','events','alerts','node_state'):
            db.execute(f'SELECT 1 FROM {table} LIMIT 1')
        return name+'; history tables readable'

def get_json(url):
    with urlopen(url,timeout=6) as response:return json.load(response)

def guest(node, ip):
    health=get_json(f'http://{ip}:5123/health')
    if health.get('node')!=node or health.get('status') not in ('ok','online'):
        raise ValueError('Health identity/status mismatch')
    data=get_json(f'http://{ip}:5123/api/metrics')
    if data.get('node')!=node:raise ValueError('Metrics node mismatch')
    from monitor_common import classify
    for r in ('cpu','ram','disk'):classify(r,data[r])
    return str({r:data[r] for r in ('cpu','ram','disk')})

if __name__=='__main__':
    print('The SIS 3.1 — read-only check. Start viewer and PostgreSQL first.')
    print('Stopped guests will fail health checks; this is expected during sequential testing.')
    check('PostgreSQL',database)
    check('Saved alarm thresholds',refresh_limits)
    check('Dashboard',lambda:get_json('http://127.0.0.1:5124/api/settings'))
    for node,ip in NODES.items():check(node,lambda n=node,p=ip:guest(n,p))
    print(f'{passed} passed; {failed} failed. Review failures before demonstrating LIVE mode.')
