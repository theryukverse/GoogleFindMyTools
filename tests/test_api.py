import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from tracker.main import app
from tracker import database as db
from tracker.config import settings


@pytest.fixture
def client(tmp_path):
    test_db_path = str(tmp_path / "test_api.db")
    db.init_db(test_db_path)
    with patch.object(settings, "DATABASE_PATH", test_db_path):
        with TestClient(app) as c:
            yield c, test_db_path


def test_device_sync_endpoint(client):
    test_client, test_db_path = client
    mock_devices = [("Wallet", "canonic_wallet_1")]

    with patch(
        "tracker.device_sync.fetch_devices_from_google",
        return_value=mock_devices,
    ):
        res = test_client.post("/api/devices/sync")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["summary"]["new"] == 1
        assert data["summary"]["total"] == 1

        # Check devices list
        devices_res = test_client.get("/api/devices")
        assert devices_res.status_code == 200
        dev_list = devices_res.json()
        assert len(dev_list) == 1
        assert dev_list[0]["device_id"] == "canonic_wallet_1"
        assert dev_list[0]["name"] == "Wallet"
        assert dev_list[0]["tracking_enabled"] is False
