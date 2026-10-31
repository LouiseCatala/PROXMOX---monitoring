-- Read-only queries. Run one selected query at a time in pgAdmin Query Tool.
SELECT current_database(), current_user;

SELECT source, node, COUNT(*) AS saved_readings
FROM readings GROUP BY source, node ORDER BY source, node;

SELECT id AS event_id,
       checked_at AT TIME ZONE 'Asia/Manila' AS event_timestamp_ph,
       node AS node_name, status, cpu, cpu_severity,
       ram, ram_severity, disk, disk_severity, source
FROM readings ORDER BY id DESC LIMIT 20;

-- The required normalized metric fields, including all three resources.
SELECT r.id AS event_id, r.node AS node_name, m.metric_name,
       m.metric_value, m.severity, r.status,
       r.checked_at AS event_timestamp, r.source
FROM readings r CROSS JOIN LATERAL (VALUES
  ('CPU',r.cpu,r.cpu_severity),('RAM',r.ram,r.ram_severity),
  ('DISK',r.disk,r.disk_severity)
) AS m(metric_name,metric_value,severity)
ORDER BY r.id DESC, m.metric_name LIMIT 60;

SELECT id AS event_id, node AS node_name, resource AS metric_name,
       value AS metric_value, previous_severity, severity,
       state AS status, threshold,
       checked_at AT TIME ZONE 'Asia/Manila' AS event_timestamp_ph, source
FROM alerts ORDER BY id DESC LIMIT 30;

SELECT id AS event_id, node, previous_status, new_status, severity,
       checked_at AT TIME ZONE 'Asia/Manila' AS event_timestamp_ph,
       last_seen AT TIME ZONE 'Asia/Manila' AS last_seen_ph,
       first_failure_at AT TIME ZONE 'Asia/Manila' AS first_failure_ph,
       recovery_at AT TIME ZONE 'Asia/Manila' AS recovery_timestamp_ph, source
FROM events ORDER BY id DESC LIMIT 30;

SELECT node, source, status, consecutive_failures, last_seen,
       first_failure_at, last_outage_at, recovery_at
FROM node_state ORDER BY source, node;

SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name IN ('readings','events','alerts','node_state')
ORDER BY table_name, ordinal_position;
