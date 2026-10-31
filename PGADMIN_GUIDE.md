# The SIS — view PostgreSQL in pgAdmin 4

PostgreSQL stores the data; pgAdmin 4 is its management interface. Open pgAdmin 4
from the Windows Start menu (its interface may open in its own window or a browser).
Do not browse to port 5432: that is PostgreSQL's database protocol, not a web page.

## Connect to the existing database

1. Open pgAdmin 4. If it asks for a master password, this is pgAdmin's own saved-password
   protection, separate from the PostgreSQL role password.
2. If your existing PostgreSQL 18 server is already connected, expand it and continue
   below. Otherwise right-click Servers → Register → Server.
3. General tab: Name = The SIS PostgreSQL.
4. Connection tab:

| Field | Value |
|---|---|
| Host name/address | 127.0.0.1 |
| Port | 5432 |
| Maintenance database | proxmox_monitor |
| Username | proxmox_monitor |
| Password | Your project's PGPASSWORD from .env; do not share it |

5. Save. Use the project role to avoid needing the postgres administrator password.
   If authentication fails, verify the role/password against .env and confirm the
   postgresql-x64-18 Windows service is running. The dashboard and pgAdmin must
   connect to the same host, port and database.
6. Expand: Servers → The SIS PostgreSQL → Databases → proxmox_monitor → Schemas →
   public → Tables.

## What the tables contain

| Table | Contents |
|---|---|
| readings | Timestamped CPU/RAM/Disk samples and each metric's severity |
| alerts | Severity transitions: INITIAL, ALERT, RECOVERED; value and threshold |
| events | Availability changes, first failure, last response and recovery |
| node_state | Latest retained status and failure count for each node/source |
| history_migrations | Marker for original SQLite import, if migrated |
| monitor_upgrades | Schema upgrade version marker |

Right-click a table → View/Edit Data → First 100 Rows. Use this to view the data.
New logger rows appear when you refresh/re-execute the query; pgAdmin does not
necessarily refresh automatically every five seconds like The SIS dashboard.

## Query Tool

Right-click the proxmox_monitor DATABASE → Query Tool. Open database_checks.sql,
or paste one query from it. Select that query and click Execute (F5 in common
pgAdmin layouts). Inspect Data Output. Refresh by executing again while logger runs.

Start with:

```sql
SELECT current_database(), current_user;
SELECT source, node, COUNT(*) AS saved_readings
FROM readings
GROUP BY source, node
ORDER BY source, node;
```

Latest readings:

```sql
SELECT id, checked_at AT TIME ZONE 'Asia/Manila' AS philippine_time,
       node, status, cpu, cpu_severity, ram, ram_severity,
       disk, disk_severity, source
FROM readings ORDER BY id DESC LIMIT 20;
```

Demo inputs create SIMULATED rows; actual agents create LIVE rows. Add
WHERE source = 'SIMULATED' (or 'LIVE') before ORDER BY to filter them.
Thresholds are fixed at the official project defaults in The SIS3.1. They are not
editable PostgreSQL settings. Per-VM demo inputs/mode are in demo_inputs.json;
confirmed samples and events are stored in PostgreSQL with source=SIMULATED.
The alerts table stores the threshold used for each recorded event. Old event
thresholds remain unchanged.

Official references:
- https://www.pgadmin.org/docs/pgadmin4/latest/connect_to_server.html
- https://www.pgadmin.org/docs/pgadmin4/latest/query_tool.html
