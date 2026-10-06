import sqlite3
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    tracking_enabled INTEGER NOT NULL DEFAULT 0,
    is_available INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    last_seen_at INTEGER
);

CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    recorded_at INTEGER NOT NULL,
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_locations_device_time ON locations(device_id, recorded_at);
"""


def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Creates a new SQLite connection with WAL mode and foreign key enforcement."""
    conn = sqlite3.connect(db_path, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def init_db(db_path: str) -> None:
    """Initializes the SQLite database schema idempotently."""
    logger.info("Initializing database schema at: %s", db_path)
    with get_db_connection(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    logger.info("Database schema initialized successfully.")


def get_devices(
    conn: sqlite3.Connection, tracked_only: bool = False, available_only: bool = True
) -> List[sqlite3.Row]:
    """Fetches devices based on filtering criteria."""
    query = "SELECT device_id, name, tracking_enabled, is_available, created_at, last_seen_at FROM devices WHERE 1=1"
    params = []

    if available_only:
        query += " AND is_available = 1"
    if tracked_only:
        query += " AND tracking_enabled = 1"

    query += " ORDER BY name ASC, device_id ASC"
    cursor = conn.execute(query, params)
    return cursor.fetchall()


def get_device(conn: sqlite3.Connection, device_id: str) -> Optional[sqlite3.Row]:
    """Fetches a single device by ID."""
    cursor = conn.execute(
        "SELECT device_id, name, tracking_enabled, is_available, created_at, last_seen_at FROM devices WHERE device_id = ?",
        (device_id,),
    )
    return cursor.fetchone()


def update_device_tracking(
    conn: sqlite3.Connection, device_id: str, tracking_enabled: bool
) -> Optional[sqlite3.Row]:
    """Updates tracking flag for a device. Returns updated device row or None if not found."""
    flag_val = 1 if tracking_enabled else 0
    with conn:
        cursor = conn.execute(
            "UPDATE devices SET tracking_enabled = ? WHERE device_id = ?",
            (flag_val, device_id),
        )
        if cursor.rowcount == 0:
            return None
    return get_device(conn, device_id)


def record_location(
    conn: sqlite3.Connection,
    device_id: str,
    latitude: float,
    longitude: float,
    recorded_at: int,
) -> int:
    """Inserts a new location reading and updates the device's last_seen_at timestamp."""
    with conn:
        cursor = conn.execute(
            "INSERT INTO locations (device_id, latitude, longitude, recorded_at) VALUES (?, ?, ?, ?)",
            (device_id, latitude, longitude, recorded_at),
        )
        conn.execute(
            "UPDATE devices SET last_seen_at = ? WHERE device_id = ?",
            (recorded_at, device_id),
        )
        return cursor.lastrowid


def get_location_history(
    conn: sqlite3.Connection, device_id: str, start_time: int, end_time: int
) -> List[sqlite3.Row]:
    """Retrieves location readings for a device ordered from oldest to newest."""
    cursor = conn.execute(
        """
        SELECT id, device_id, latitude, longitude, recorded_at
        FROM locations
        WHERE device_id = ? AND recorded_at >= ? AND recorded_at <= ?
        ORDER BY recorded_at ASC, id ASC
        """,
        (device_id, start_time, end_time),
    )
    return cursor.fetchall()


def sync_device_insert(
    conn: sqlite3.Connection, device_id: str, name: str, created_at: int
) -> None:
    """Inserts a new device with tracking off and available=1."""
    with conn:
        conn.execute(
            """
            INSERT INTO devices (device_id, name, tracking_enabled, is_available, created_at, last_seen_at)
            VALUES (?, ?, 0, 1, ?, NULL)
            """,
            (device_id, name, created_at),
        )


def sync_device_update(conn: sqlite3.Connection, device_id: str, name: str) -> None:
    """Updates device display name and marks it available. Does NOT touch tracking_enabled."""
    with conn:
        conn.execute(
            "UPDATE devices SET name = ?, is_available = 1 WHERE device_id = ?",
            (name, device_id),
        )


def sync_device_mark_unavailable(conn: sqlite3.Connection, device_id: str) -> None:
    """Marks a device as unavailable. Preserves its tracking setting and history."""
    with conn:
        conn.execute(
            "UPDATE devices SET is_available = 0 WHERE device_id = ?", (device_id,)
        )
