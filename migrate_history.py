import hashlib
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv


FOLDER = Path(__file__).resolve().parent
SOURCE = FOLDER / "backup_before_postgresql" / "monitoring.db"

TABLES = {
    "readings": [
        "checked_at", "node", "status",
        "cpu", "ram", "disk", "consecutive_failures",
    ],
    "events": [
        "checked_at", "node", "previous_status", "new_status",
    ],
    "alerts": [
        "checked_at", "node", "resource",
        "state", "value", "threshold",
    ],
}

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS readings (
        id BIGSERIAL PRIMARY KEY,
        checked_at TIMESTAMPTZ NOT NULL,
        node TEXT NOT NULL,
        status TEXT NOT NULL,
        cpu DOUBLE PRECISION,
        ram DOUBLE PRECISION,
        disk DOUBLE PRECISION,
        consecutive_failures INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id BIGSERIAL PRIMARY KEY,
        checked_at TIMESTAMPTZ NOT NULL,
        node TEXT NOT NULL,
        previous_status TEXT NOT NULL,
        new_status TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id BIGSERIAL PRIMARY KEY,
        checked_at TIMESTAMPTZ NOT NULL,
        node TEXT NOT NULL,
        resource TEXT NOT NULL,
        state TEXT NOT NULL,
        value DOUBLE PRECISION NOT NULL,
        threshold DOUBLE PRECISION NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS history_migrations (
        name TEXT PRIMARY KEY,
        source_sha256 TEXT NOT NULL,
        migrated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS readings_node_id_idx
    ON readings (node, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS alerts_node_resource_id_idx
    ON alerts (node, resource, id DESC)
    """,
]


def migrate():
    if not SOURCE.is_file():
        raise RuntimeError(
            f"Backup not found: {SOURCE}\n"
            "Create the SQLite backup first."
        )

    load_dotenv(FOLDER / ".env", override=True)
    fingerprint = hashlib.sha256(SOURCE.read_bytes()).hexdigest()

    rows_by_table = {}

    with closing(sqlite3.connect(
        SOURCE.as_uri() + "?mode=ro",
        uri=True,
    )) as source:
        source.execute("BEGIN")

        available_tables = {
            row[0]
            for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        for table, columns in TABLES.items():
            if table not in available_tables:
                raise RuntimeError(
                    f"Backup is missing the {table} table."
                )

            column_names = ",".join(columns)
            rows = source.execute(
                f"SELECT {column_names} FROM {table} ORDER BY id"
            ).fetchall()

            converted = []

            for row in rows:
                checked_at = datetime.fromisoformat(row[0])

                if checked_at.tzinfo is None:
                    raise RuntimeError(
                        f"Timestamp has no timezone in {table}: {row[0]}"
                    )

                converted.append((checked_at, *row[1:]))

            rows_by_table[table] = converted

    counts = {}

    with psycopg.connect(connect_timeout=5) as target:
        target.execute("SET LOCAL statement_timeout = '60s'")
        target.execute("SELECT pg_advisory_xact_lock(51235124)")

        for statement in SCHEMA:
            target.execute(statement)

        previous = target.execute("""
            SELECT source_sha256
            FROM history_migrations
            WHERE name = 'sqlite_history_v1'
        """).fetchone()

        if previous:
            if previous[0] != fingerprint:
                raise RuntimeError(
                    "A different SQLite backup was already migrated."
                )

            print("This backup was already migrated. No duplicates added.")
            return

        # Refuse to overwrite or mix with existing PostgreSQL readings.
        for table in TABLES:
            count = target.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

            if count:
                raise RuntimeError(
                    f"PostgreSQL {table} is not empty. "
                    "Nothing was imported."
                )

        with target.cursor() as cursor:
            for table, columns in TABLES.items():
                rows = rows_by_table[table]
                column_names = ",".join(columns)
                placeholders = ",".join(["%s"] * len(columns))

                if rows:
                    cursor.executemany(
                        f"INSERT INTO {table} ({column_names}) "
                        f"VALUES ({placeholders})",
                        rows,
                    )

                saved = target.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]

                if saved != len(rows):
                    raise RuntimeError(
                        f"Count mismatch in {table}."
                    )

                counts[table] = saved

        target.execute("""
            INSERT INTO history_migrations (name, source_sha256)
            VALUES (%s, %s)
        """, ("sqlite_history_v1", fingerprint))

    print("MIGRATION SUCCESSFUL")

    for table, count in counts.items():
        print(f"{table}: {count} rows")

    print("Original SQLite backup is unchanged.")


if __name__ == "__main__":
    try:
        migrate()
    except Exception as error:
        print("MIGRATION FAILED:", error)
        raise SystemExit(1)