from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


def format_timestamp_iso(ts: Optional[int]) -> Optional[str]:
    """Converts unix epoch seconds to ISO 8601 UTC formatted string."""
    if ts is None:
        return None
    return (
        datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    )


class DeviceResponse(BaseModel):
    device_id: str
    name: str
    tracking_enabled: bool
    is_available: bool
    created_at: int
    created_at_iso: str
    last_seen_at: Optional[int] = None
    last_seen_at_iso: Optional[str] = None


class DeviceTrackingUpdate(BaseModel):
    tracking_enabled: bool = Field(
        ..., description="Turn tracking on (true) or off (false)"
    )


class LocationPointResponse(BaseModel):
    id: int
    device_id: str
    latitude: float
    longitude: float
    recorded_at: int
    recorded_at_iso: str


class LocationHistoryResponse(BaseModel):
    device_id: str
    device_name: str
    start_time: int
    end_time: int
    start_time_iso: str
    end_time_iso: str
    count: int
    points: List[LocationPointResponse]


class HealthResponse(BaseModel):
    status: str
    database: str
    poller: str
    provider: str
    timestamp_utc: str


class ConfigResponse(BaseModel):
    tile_url: str
    tile_attribution: str
    poll_interval_seconds: int
    location_provider: str


class PushLocationRequest(BaseModel):
    latitude: float = Field(
        ..., ge=-90.0, le=90.0, description="Latitude between -90 and 90"
    )
    longitude: float = Field(
        ..., ge=-180.0, le=180.0, description="Longitude between -180 and 180"
    )
    recorded_at: Optional[int] = Field(
        None, description="UTC unix epoch seconds. Defaults to current time if omitted."
    )
