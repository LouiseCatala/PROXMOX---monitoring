"""Add columns and tables atomically; retain all existing samples/events."""
from monitor_common import connect

VERSION = 'severity_dashboard_v2'

def upgrade(db):
    with db.transaction():
        db.execute('SELECT pg_advisory_xact_lock(51235124)')
        db.execute('''CREATE TABLE IF NOT EXISTS monitor_upgrades (
            name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
        if db.execute('SELECT 1 FROM monitor_upgrades WHERE name=%s', (VERSION,)).fetchone():
            return False
        # Core tables normally already exist from the previous migration.
        db.execute('''CREATE TABLE IF NOT EXISTS readings (
            id BIGSERIAL PRIMARY KEY, checked_at TIMESTAMPTZ NOT NULL,
            node TEXT NOT NULL, status TEXT NOT NULL, cpu DOUBLE PRECISION,
            ram DOUBLE PRECISION, disk DOUBLE PRECISION,
            consecutive_failures INTEGER NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS events (
            id BIGSERIAL PRIMARY KEY, checked_at TIMESTAMPTZ NOT NULL,
            node TEXT NOT NULL, previous_status TEXT NOT NULL, new_status TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS alerts (
            id BIGSERIAL PRIMARY KEY, checked_at TIMESTAMPTZ NOT NULL,
            node TEXT NOT NULL, resource TEXT NOT NULL, state TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL, threshold DOUBLE PRECISION NOT NULL)''')
        for table in ('readings', 'events', 'alerts'):
            # Table names are internal constants, not user input.
            db.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'LIVE'")
        for resource in ('cpu', 'ram', 'disk'):
            db.execute(f'ALTER TABLE readings ADD COLUMN IF NOT EXISTS {resource}_severity TEXT')
            yellow, orange, red = (60, 75, 90) if resource == 'disk' else (60, 70, 85)
            db.execute(f'''UPDATE readings SET {resource}_severity = CASE
                WHEN {resource} IS NULL THEN NULL WHEN {resource}>=%s THEN 'CRITICAL'
                WHEN {resource}>=%s THEN 'WARNING' WHEN {resource}>=%s THEN 'LOW PRIORITY'
                ELSE 'NORMAL' END WHERE {resource}_severity IS NULL''', (red, orange, yellow))
        db.execute('ALTER TABLE alerts ADD COLUMN IF NOT EXISTS severity TEXT')
        db.execute('ALTER TABLE alerts ADD COLUMN IF NOT EXISTS previous_severity TEXT')
        db.execute('''UPDATE alerts SET severity=CASE
            WHEN resource='disk' AND value>=90 THEN 'CRITICAL'
            WHEN resource<>'disk' AND value>=85 THEN 'CRITICAL'
            WHEN resource='disk' AND value>=75 THEN 'WARNING'
            WHEN resource<>'disk' AND value>=70 THEN 'WARNING'
            WHEN value>=60 THEN 'LOW PRIORITY' ELSE 'NORMAL' END
            WHERE severity IS NULL''')
        # Severity is classification of recorded value, not a fabricated past event.
        # Existing threshold and state columns remain unchanged.
        for col, typ in [('severity','TEXT'), ('last_seen','TIMESTAMPTZ'),
                         ('first_failure_at','TIMESTAMPTZ'), ('recovery_at','TIMESTAMPTZ')]:
            db.execute(f'ALTER TABLE events ADD COLUMN IF NOT EXISTS {col} {typ}')
        db.execute('''UPDATE events SET severity=CASE new_status
            WHEN 'REACHABLE' THEN 'NORMAL' WHEN 'RETRYING' THEN 'LOW PRIORITY'
            WHEN 'UNAVAILABLE' THEN 'CRITICAL' ELSE 'UNKNOWN' END WHERE severity IS NULL''')
        db.execute('''CREATE TABLE IF NOT EXISTS node_state (
            node TEXT NOT NULL, source TEXT NOT NULL,
            status TEXT NOT NULL, consecutive_failures INTEGER NOT NULL,
            checked_at TIMESTAMPTZ NOT NULL, last_seen TIMESTAMPTZ,
            first_failure_at TIMESTAMPTZ, recovery_at TIMESTAMPTZ,
            last_outage_at TIMESTAMPTZ, error TEXT,
            cpu_severity TEXT, ram_severity TEXT, disk_severity TEXT,
            PRIMARY KEY (node, source))''')
        db.execute('CREATE INDEX IF NOT EXISTS readings_source_node_id_idx ON readings(source,node,id DESC)')
        db.execute('CREATE INDEX IF NOT EXISTS alerts_source_node_resource_id_idx ON alerts(source,node,resource,id DESC)')
        db.execute('INSERT INTO monitor_upgrades(name) VALUES (%s)', (VERSION,))
        return True

if __name__ == '__main__':
    with connect() as db:
        changed = upgrade(db)
        print('UPGRADE SUCCESSFUL' if changed else 'Already upgraded; no changes needed.')
        print('Existing readings, events, alerts and migration history retained.')
