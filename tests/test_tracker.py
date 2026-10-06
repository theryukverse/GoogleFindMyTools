import pytest
import sqlite3
from unittest.mock import patch, MagicMock

from tracker import database as db
from tracker.providers import get_provider
from tracker.providers.google_find_my import GoogleFindMyProvider


def test_get_provider_default():
    provider = get_provider()
    assert isinstance(provider, GoogleFindMyProvider)


def test_get_provider_invalid():
    with pytest.raises(ValueError, match="Unknown location provider"):
        get_provider("non_existent_provider")


def test_database_operations(tmp_path):
    db_file = tmp_path / "test_db.db"
    db.init_db(str(db_file))
    conn = db.get_db_connection(str(db_file))

    # Insert device
    db.sync_device_insert(conn, "dev_1", "Test Device", 1000)
    dev = db.get_device(conn, "dev_1")
    assert dev["device_id"] == "dev_1"
    assert dev["name"] == "Test Device"
    assert dev["tracking_enabled"] == 0

    # Toggle tracking
    updated = db.update_device_tracking(conn, "dev_1", True)
    assert updated["tracking_enabled"] == 1

    # Record location
    loc_id = db.record_location(conn, "dev_1", 37.7749, -122.4194, 1050)
    assert loc_id > 0

    # Retrieve history
    history = db.get_location_history(conn, "dev_1", 1000, 1100)
    assert len(history) == 1
    assert history[0]["latitude"] == pytest.approx(37.7749)
    assert history[0]["longitude"] == pytest.approx(-122.4194)

    conn.close()
