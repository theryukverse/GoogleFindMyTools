import sqlite3
import pytest
from unittest.mock import patch

from tracker import database as db
from tracker.device_sync import sync_devices, fetch_devices_from_google


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_tracker.db"
    db.init_db(str(db_file))
    conn = db.get_db_connection(str(db_file))
    yield conn
    conn.close()


def test_sync_devices_with_return_list(temp_db):
    # Simulated output from list_devices_with_return()
    mock_api_devices = [
        ("Keys Tracker", "canonic_id_101"),
        ("Backpack", "canonic_id_202"),
    ]

    summary = sync_devices(temp_db, devices_list=mock_api_devices)

    assert summary["new"] == 2
    assert summary["updated"] == 0
    assert summary["unavailable"] == 0
    assert summary["total"] == 2

    devices = db.get_devices(temp_db, available_only=True)
    assert len(devices) == 2
    dev1 = db.get_device(temp_db, "canonic_id_101")
    assert dev1["name"] == "Keys Tracker"
    assert dev1["tracking_enabled"] == 0
    assert dev1["is_available"] == 1

    dev2 = db.get_device(temp_db, "canonic_id_202")
    assert dev2["name"] == "Backpack"
    assert dev2["tracking_enabled"] == 0


def test_sync_devices_preserves_tracking_setting_and_marks_removed(temp_db):
    initial_devices = [
        ("Keys Tracker", "canonic_id_101"),
        ("Backpack", "canonic_id_202"),
    ]
    sync_devices(temp_db, devices_list=initial_devices)

    # Enable tracking for Keys Tracker
    db.update_device_tracking(temp_db, "canonic_id_101", True)
    dev1 = db.get_device(temp_db, "canonic_id_101")
    assert dev1["tracking_enabled"] == 1

    # Next sync from Google: Backpack is gone, Keys Tracker has a renamed label, Bike is added
    updated_api_devices = [
        ("Keys Tracker Renamed", "canonic_id_101"),
        ("Bike Tag", "canonic_id_303"),
    ]
    summary2 = sync_devices(temp_db, devices_list=updated_api_devices)

    assert summary2["new"] == 1
    assert summary2["updated"] == 1
    assert summary2["unavailable"] == 1
    assert summary2["total"] == 2

    # Keys tracking state remains 1, name updated
    dev1_updated = db.get_device(temp_db, "canonic_id_101")
    assert dev1_updated["name"] == "Keys Tracker Renamed"
    assert dev1_updated["tracking_enabled"] == 1
    assert dev1_updated["is_available"] == 1

    # Backpack is now marked unavailable but still exists in DB
    backpack = db.get_device(temp_db, "canonic_id_202")
    assert backpack["is_available"] == 0

    # Only available devices returned by default
    available_devices = db.get_devices(temp_db, available_only=True)
    assert len(available_devices) == 2
    available_ids = [d["device_id"] for d in available_devices]
    assert "canonic_id_101" in available_ids
    assert "canonic_id_303" in available_ids
    assert "canonic_id_202" not in available_ids


def test_fetch_devices_from_google_calls_list_devices_with_return():
    mock_returns = [("Car Keys", "id_999")]
    with patch(
        "NovaApi.ListDevices.nbe_list_devices.list_devices_with_return",
        return_value=mock_returns,
    ) as mock_func:
        result = fetch_devices_from_google()
        assert result == mock_returns
        mock_func.assert_called_once()
