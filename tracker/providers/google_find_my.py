import asyncio
import logging
from typing import Optional, Tuple

from tracker.providers.base import LocationProvider

logger = logging.getLogger(__name__)


class GoogleFindMyProvider(LocationProvider):
    """
    Location provider that fetches device locations using the local
    GoogleFindMyTools NovaApi / LocateTracker integration.
    """

    def __init__(self):
        try:
            from NovaApi.ExecuteAction.LocateTracker.location_request import (
                get_location_data_for_device,
            )

            self._fetch_func = get_location_data_for_device
            logger.info("GoogleFindMyProvider initialized successfully.")
        except Exception as e:
            logger.error("Failed to import GoogleFindMyTools NovaApi: %s", e)
            self._fetch_func = None

    async def get_location(
        self, device_id: str, name: Optional[str] = None
    ) -> Optional[Tuple[float, float]]:
        if self._fetch_func is None:
            raise RuntimeError(
                "GoogleFindMyTools dependencies or modules are not available."
            )

        def _sync_fetch():
            return self._fetch_func(device_id, name or device_id)

        try:
            logger.info(
                "Requesting Google Find My location for device: %s (%s)",
                device_id,
                name,
            )
            loc = await asyncio.to_thread(_sync_fetch)
            if loc is None:
                logger.warning(
                    "No location returned for Google Find My device: %s", device_id
                )
                return None

            lat = loc.latitude
            lon = loc.longitude

            if lat is None or lon is None:
                logger.warning(
                    "Google Find My device %s returned None coordinates: %s",
                    device_id,
                    loc,
                )
                return None

            lat = float(lat)
            lon = float(lon)

            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                logger.error(
                    "Coordinates out of range for device %s: (%f, %f)",
                    device_id,
                    lat,
                    lon,
                )
                return None

            return (lat, lon)
        except Exception as e:
            logger.error(
                "Error fetching Google Find My location for %s: %s", device_id, e
            )
            raise
