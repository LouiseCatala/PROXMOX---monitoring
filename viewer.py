"""Local dashboard with smooth polling, severity history and source-aware exports."""
import csv
import io
from datetime import datetime, timezone
import psycopg
from psycopg.rows import dict_row
from flask import Flask, Response, jsonify, render_template, request
from waitress import serve
from monitor_common import NODES, RESOURCES, classify, connect, utcnow, DEFAULT_LIMITS, refresh_limits, save_limits

app=Flask(__name__)

def source_arg():
    source=request.args.get('source','LIVE')
    if source != 'LIVE':
        raise ValueError('Invalid source')
    return source

def jsonify_dates(value):
    if isinstance(value,datetime): return value.astimezone(timezone.utc).isoformat()
    if isinstance(value,dict): return {k:jsonify_dates(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [jsonify_dates(v) for v in value]
    return value

def load_dashboard(source):
    now=utcnow();cards=[]
    with connect(readonly=True,rows=dict_row) as db:
        # Consistent read snapshot across cards, history and counts.
        with db.transaction():
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            count=db.execute('SELECT count(*) AS total FROM readings WHERE source=%s',(source,)).fetchone()['total']
            for node,ip in NODES.items():
                recent=db.execute('SELECT * FROM readings WHERE node=%s AND source=%s ORDER BY id DESC LIMIT 60',(node,source)).fetchall()
                latest=recent[0] if recent else None
                state=db.execute('SELECT * FROM node_state WHERE node=%s AND source=%s',(node,source)).fetchone()
                age=(now-latest['checked_at']).total_seconds() if latest else None
                status='NO DATA' if not latest else 'LOGGER STALE' if age>15 or age < -5 else latest['status']
                metrics={r:dict(value=latest[r] if latest else None,
                    severity=latest[r+'_severity'] if latest else None) for r in RESOURCES}
                cards.append(dict(node=node,ip=ip,status=status,age=age,
                    checked_at=latest['checked_at'] if latest else None,
                    failures=latest['consecutive_failures'] if latest else 0,
                    last_seen=state['last_seen'] if state else None,
                    first_failure_at=state['first_failure_at'] if state else None,
                    recovery_at=state['recovery_at'] if state else None,
                    last_outage_at=state['last_outage_at'] if state else None,
                    metrics=metrics,history=list(reversed(recent))))
            readings=db.execute('SELECT * FROM readings WHERE source=%s ORDER BY id DESC LIMIT 30',(source,)).fetchall()
            events=db.execute('SELECT * FROM events WHERE source=%s ORDER BY id DESC LIMIT 30',(source,)).fetchall()
            alerts=db.execute('SELECT * FROM alerts WHERE source=%s ORDER BY id DESC LIMIT 30',(source,)).fetchall()
    return dict(source=source,count=count,cards=cards,readings=readings,
                events=events,alerts=alerts,server_time=now)

def require_dashboard_write():
    origin = request.headers.get('Origin')
    if request.headers.get('X-Monitor-Settings') != '1' or (origin and origin != request.host_url.rstrip('/')):
        return jsonify(error='Use the controls in The SIS dashboard.'), 403
    if not request.is_json:
        return jsonify(error='Expected JSON.'), 400
    return None

@app.route('/api/settings', methods=['GET', 'POST'])
def get_settings():
    try:
        if request.method == 'POST':
            blocked = require_dashboard_write()
            if blocked: return blocked
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict): raise ValueError('Provide thresholds.')
            current = save_limits(payload.get('thresholds'))
        else:
            current = refresh_limits()
        response = jsonify(thresholds=current, defaults=DEFAULT_LIMITS,
            message='Saved permanently. New checks use these rules; historical records remain unchanged.')
        response.headers['Cache-Control'] = 'no-store'
        return response
    except (ValueError, TypeError) as error:
        return jsonify(error=str(error)), 400
    except OSError:
        return jsonify(error='Cannot save threshold_settings.json. Check folder permissions.'), 503

@app.get('/')
def dashboard():
    return render_template('dashboard.html')

@app.get('/api/dashboard')
def api_dashboard():
    try:
        data=load_dashboard(source_arg())
        response=jsonify(jsonify_dates(data));response.headers['Cache-Control']='no-store'
        return response
    except ValueError:
        return jsonify(error='Only LIVE monitoring is available.'),400
    except (psycopg.Error,TypeError):
        return jsonify(error='Cannot load history. Check PostgreSQL and .env, and run python upgrade_db.py.'),503

EXPORTS={
 'readings':'''SELECT id AS event_id,checked_at,node,status,cpu,cpu_severity,
    ram,ram_severity,disk,disk_severity,consecutive_failures,source FROM readings
    WHERE source=%s ORDER BY id''',
 'metrics':'''SELECT r.id AS event_id,r.checked_at AS event_timestamp,r.node AS node_name,m.metric_name,
    m.metric_value,m.severity,r.status,r.source
    FROM readings r CROSS JOIN LATERAL (VALUES
    ('CPU',r.cpu,r.cpu_severity),('RAM',r.ram,r.ram_severity),
    ('DISK',r.disk,r.disk_severity)) AS m(metric_name,metric_value,severity)
    WHERE r.source=%s ORDER BY r.id,m.metric_name''',
 'events':'''SELECT id AS event_id,checked_at,node,previous_status,new_status,
    severity,last_seen,first_failure_at,recovery_at,source FROM events
    WHERE source=%s ORDER BY id''',
 'alerts':'''SELECT id AS event_id,checked_at,node,resource AS metric_name,
    value AS metric_value,previous_severity,severity,state,state AS status,threshold,source
    FROM alerts WHERE source=%s ORDER BY id'''
}

def csv_value(value):
    if isinstance(value,datetime):return value.astimezone(timezone.utc).isoformat()
    if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r','\n')):return "'"+value
    return value

@app.get('/export/<kind>')
def export(kind):
    if kind not in EXPORTS:return 'Unknown export',404
    db=None
    try:
        source=source_arg()
        db=connect(readonly=True,rows=dict_row)
        # Named server-side cursor keeps large exports bounded in memory.
        db.autocommit=False
        cursor=db.cursor(name='monitor_export')
        cursor.execute(EXPORTS[kind],(source,))
        columns=[c.name for c in cursor.description]
    except ValueError:
        return 'Invalid source',400
    except psycopg.Error:
        if db:db.close()
        return 'Cannot export history. Check PostgreSQL and run the upgrade.',503
    def generate():
        buffer=io.StringIO(newline='');writer=csv.writer(buffer)
        try:
            writer.writerow(columns);yield buffer.getvalue()
            while True:
                rows=cursor.fetchmany(500)
                if not rows:break
                buffer.seek(0);buffer.truncate(0)
                for row in rows:writer.writerow([csv_value(row[c]) for c in columns])
                yield buffer.getvalue()
        finally:
            cursor.close();db.close()
    response=Response(generate(),mimetype='text/csv',headers={
        'Content-Disposition':f'attachment; filename="{kind}-{source.lower()}.csv"'})
    response.call_on_close(db.close)
    return response

if __name__=='__main__':
    print('Open http://127.0.0.1:5124 | keep logger.py running.',flush=True)
    serve(app,host='127.0.0.1',port=5124)
