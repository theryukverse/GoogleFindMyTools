import logging
import sqlite3
import time
from typing import Dict, List, Optional, Tuple

from tracker import database as db

logger = logging.getLogger(__name__)


def fetch_devices_from_google() -> List[Tuple[str, str]]:
    """
    Calls NovaApi's list_devices_with_return() to retrieve devices
    from the Google Find My network.
    Returns a list of tuples: (device_name, canonic_id).
    """
    from NovaApi.ListDevices.nbe_list_devices import list_devices_with_return

    logger.info("Calling list_devices_with_return() from Google Find My network...")
    devices = list_devices_with_return()
    logger.info(
        "Successfully retrieved %d device(s) from list_devices_with_return().",
        len(devices) if devices else 0,
    )
    return devices or []


def sync_devices(
    conn: sqlite3.Connection,
    devices_list: Optional[List[Tuple[str, str]]] = None,
) -> Dict[str, int]:
    """
    Syncs devices returned by list_devices_with_return() with the SQLite database.
    - If devices_list is not provided, fetch_devices_from_google() is called.
    - New devices: inserted with tracking_enabled = 0, is_available = 1.
    - Existing devices: display name updated, is_available = 1, tracking setting unchanged.
    - Removed devices (not returned by Google): marked is_available = 0 (history preserved).
    - Re-appearing devices: marked is_available = 1.
    """
    if devices_list is None:
        devices_list = fetch_devices_from_google()

    # Map device_id -> device_name
    device_map: Dict[str, str] = {}
    for item in devices_list:
        if not item or len(item) < 2:
            continue
        dev_name, dev_id = item[0], item[1]
        dev_id = str(dev_id).strip()
        if not dev_id:
            continue
        name = str(dev_name or "").strip() or dev_id
        device_map[dev_id] = name

    now_ts = int(time.time())

    # Get all known devices in the database
    cursor = conn.execute(
        "SELECT device_id, name, tracking_enabled, is_available FROM devices"
    )
    db_devices = {row["device_id"]: row for row in cursor.fetchall()}

    new_count = 0
    updated_count = 0
    unavailable_count = 0

    # 1. Process devices returned from list_devices_with_return
    for dev_id, name in device_map.items():
        if dev_id not in db_devices:
            # New device: insert with tracking off
            db.sync_device_insert(conn, dev_id, name, now_ts)
            new_count += 1
            logger.info(
                "Added new device from Google Find My: ID=%s, Name=%s (tracking disabled by default)",
                dev_id,
                name,
            )
        else:
            # Existing device: update display name and ensure available, keep tracking_enabled intact
            db.sync_device_update(conn, dev_id, name)
            updated_count += 1

    # 2. Process devices in database that are NOT in current list
    for dev_id, row in db_devices.items():
        if dev_id not in device_map:
            if row["is_available"] != 0:
                db.sync_device_mark_unavailable(conn, dev_id)
                unavailable_count += 1
                logger.info(
                    "Device ID=%s is no longer returned by Google Find My; marked as unavailable (history preserved)",
                    dev_id,
                )

    summary = {
        "new": new_count,
        "updated": updated_count,
        "unavailable": unavailable_count,
        "total": len(device_map),
    }
    logger.info("Device sync complete: %s", summary)
    return summary
