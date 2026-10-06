import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from tracker import database as db
from tracker.config import settings
from tracker.device_sync import sync_devices
from tracker.models import (
    ConfigResponse,
    DeviceResponse,
    DeviceTrackingUpdate,
    HealthResponse,
    LocationHistoryResponse,
    LocationPointResponse,
    PushLocationRequest,
    format_timestamp_iso,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Tracker API"])


def _parse_time_param(val: Optional[str], default_func) -> int:
    """Parses a timestamp parameter that can be either epoch seconds or an ISO 8601 string."""
    if not val:
        return default_func()

    val_str = str(val).strip()

    # Try numeric epoch
    try:
        numeric_val = float(val_str)
        return int(numeric_val)
    except ValueError:
        pass

    # Try ISO 8601 string
    try:
        cleaned = val_str.replace("Z", "+00:00")
        # In HTTP query strings, '+' is often decoded as a space: '2026-10-05T12:00:00 00:00'
        if " " in cleaned:
            parts = cleaned.rsplit(" ", 1)
            if len(parts) == 2 and ":" in parts[1]:
                cleaned = f"{parts[0]}+{parts[1]}"
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timestamp format: '{val}'. Expected epoch seconds or ISO 8601 format.",
        )


def _row_to_device_response(row) -> DeviceResponse:
    created_at = row["created_at"]
    last_seen_at = row["last_seen_at"]
    return DeviceResponse(
        device_id=row["device_id"],
        name=row["name"],
        tracking_enabled=bool(row["tracking_enabled"]),
        is_available=bool(row["is_available"]),
        created_at=created_at,
        created_at_iso=format_timestamp_iso(created_at),
        last_seen_at=last_seen_at,
        last_seen_at_iso=format_timestamp_iso(last_seen_at),
    )


@router.get("/devices", response_model=List[DeviceResponse])
def list_devices(
    tracked_only: bool = Query(
        False, description="Filter to return only devices with tracking turned on"
    ),
):
    """
    Returns all available devices with ID, display name, tracking flag,
    and last-seen timestamp.
    """
    db_path = settings.get_database_path()
    with db.get_db_connection(db_path) as conn:
        rows = db.get_devices(conn, tracked_only=tracked_only, available_only=True)
        return [_row_to_device_response(r) for r in rows]


@router.post("/devices/sync")
async def trigger_device_sync():
    """
    Syncs devices from Google Find My network using list_devices_with_return().
    """
    db_path = settings.get_database_path()
    try:
        with db.get_db_connection(db_path) as conn:
            summary = await asyncio.to_thread(sync_devices, conn)
        return {"status": "success", "summary": summary}
    except Exception as e:
        logger.error("Device sync failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Device sync failed: {str(e)}",
        )


@router.patch("/devices/{device_id}/tracking", response_model=DeviceResponse)
@router.put("/devices/{device_id}/tracking", response_model=DeviceResponse)
def update_tracking(device_id: str, update: DeviceTrackingUpdate):
    """
    Sets a device's tracking flag on or off.
    Returns clear errors for unknown or unavailable devices.
    """
    db_path = settings.get_database_path()
    with db.get_db_connection(db_path) as conn:
        device = db.get_device(conn, device_id)
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device '{device_id}' not found.",
            )

        if not bool(device["is_available"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Device '{device_id}' is unavailable (not returned by Google Find My).",
            )

        updated_row = db.update_device_tracking(
            conn, device_id, update.tracking_enabled
        )
        if not updated_row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update tracking for device '{device_id}'.",
            )

        logger.info(
            "Updated tracking for device '%s' (%s) -> %s",
            device_id,
            device["name"],
            update.tracking_enabled,
        )
        return _row_to_device_response(updated_row)


@router.get("/devices/{device_id}/history", response_model=LocationHistoryResponse)
def get_location_history(
    device_id: str,
    start: Optional[str] = Query(
        None,
        description="Start time (ISO 8601 or epoch seconds). Defaults to 24 hours ago.",
    ),
    end: Optional[str] = Query(
        None,
        description="End time (ISO 8601 or epoch seconds). Defaults to current time.",
    ),
):
    """
    Returns location points for the given device ID ordered from oldest to newest.
    Defaults to the last 24 hours when no range is provided.
    """
    db_path = settings.get_database_path()
    with db.get_db_connection(db_path) as conn:
        device = db.get_device(conn, device_id)
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device '{device_id}' not found.",
            )

        now = int(time.time())
        start_ts = _parse_time_param(start, lambda: now - 86400)
        end_ts = _parse_time_param(end, lambda: now)

        if start_ts > end_ts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start timestamp cannot be greater than end timestamp.",
            )

        rows = db.get_location_history(conn, device_id, start_ts, end_ts)
        points = [
            LocationPointResponse(
                id=r["id"],
                device_id=r["device_id"],
                latitude=r["latitude"],
                longitude=r["longitude"],
                recorded_at=r["recorded_at"],
                recorded_at_iso=format_timestamp_iso(r["recorded_at"]),
            )
            for r in rows
        ]

        return LocationHistoryResponse(
            device_id=device["device_id"],
            device_name=device["name"],
            start_time=start_ts,
            end_time=end_ts,
            start_time_iso=format_timestamp_iso(start_ts),
            end_time_iso=format_timestamp_iso(end_ts),
            count=len(points),
            points=points,
        )


@router.get("/health", response_model=HealthResponse)
def health_check():
    """
    Health check endpoint that confirms server and database are reachable.
    """
    db_path = settings.get_database_path()
    try:
        with db.get_db_connection(db_path) as conn:
            cursor = conn.execute("SELECT 1")
            cursor.fetchone()
        db_status = "connected"
    except Exception as e:
        logger.error("Health check database probe failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unreachable: {e}",
        )

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return HealthResponse(
        status="ok",
        database=db_status,
        poller="running",
        provider=settings.LOCATION_PROVIDER,
        timestamp_utc=now_iso,
    )


@router.get("/config", response_model=ConfigResponse)
def get_client_config():
    """Returns runtime client configuration for map UI rendering."""
    return ConfigResponse(
        tile_url=settings.TILE_URL,
        tile_attribution=settings.TILE_ATTRIBUTION,
        poll_interval_seconds=settings.POLL_INTERVAL_SECONDS,
        location_provider=settings.LOCATION_PROVIDER,
    )


@router.post("/devices/{device_id}/locations", status_code=status.HTTP_201_CREATED)
def push_device_location(device_id: str, payload: PushLocationRequest):
    """
    Endpoint for future push-based devices to directly upload their current location.
    """
    db_path = settings.get_database_path()
    with db.get_db_connection(db_path) as conn:
        device = db.get_device(conn, device_id)
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device '{device_id}' not found.",
            )

        recorded_at = payload.recorded_at or int(time.time())
        loc_id = db.record_location(
            conn, device_id, payload.latitude, payload.longitude, recorded_at
        )

        return {
            "status": "success",
            "location_id": loc_id,
            "device_id": device_id,
            "recorded_at": recorded_at,
            "recorded_at_iso": format_timestamp_iso(recorded_at),
        }
