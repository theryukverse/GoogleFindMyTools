import asyncio
import logging
import time
from typing import Optional

from tracker import database as db
from tracker.providers.base import LocationProvider

logger = logging.getLogger(__name__)


class DevicePoller:
    """
    Background worker that periodically polls tracked, available devices
    and records their locations in SQLite.
    """

    def __init__(
        self, db_path: str, provider: LocationProvider, interval_seconds: int = 300
    ):
        self.db_path = db_path
        self.provider = provider
        self.interval_seconds = interval_seconds
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> None:
        """Starts the background polling task."""
        if self._is_running:
            return
        self._stop_event.clear()
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "DevicePoller started (interval: %d seconds, provider: %s)",
            self.interval_seconds,
            self.provider.__class__.__name__,
        )

    async def stop(self) -> None:
        """Signals the background poller to stop and awaits task termination."""
        if not self._is_running:
            return
        logger.info("Stopping DevicePoller...")
        self._stop_event.set()
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("DevicePoller stopped cleanly.")

    async def poll_once(self) -> dict:
        """
        Executes a single polling cycle over all tracked, available devices.
        Returns a summary dictionary of results.
        """
        success_count = 0
        failure_count = 0

        # Read active tracked devices using a fresh connection for the cycle
        try:
            with db.get_db_connection(self.db_path) as conn:
                tracked_devices = db.get_devices(
                    conn, tracked_only=True, available_only=True
                )
        except Exception as e:
            logger.error("Failed to fetch tracked devices from database: %s", e)
            return {"success": 0, "failure": 0, "total": 0}

        device_count = len(tracked_devices)
        logger.info("Starting polling cycle for %d tracked device(s)...", device_count)

        if device_count == 0:
            logger.info("No tracked devices enabled for polling.")
            return {"success": 0, "failure": 0, "total": 0}

        for device in tracked_devices:
            if self._stop_event.is_set():
                logger.info("Poller cycle interrupted by shutdown request.")
                break

            dev_id = device["device_id"]
            dev_name = device["name"]

            try:
                coords = await self.provider.get_location(dev_id, name=dev_name)
                if coords is None:
                    raise ValueError(
                        f"Provider returned no coordinates for device '{dev_id}'"
                    )

                lat, lon = coords
                if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                    raise ValueError(f"Coordinates out of bounds: lat={lat}, lon={lon}")

                now_ts = int(time.time())
                with db.get_db_connection(self.db_path) as conn:
                    db.record_location(conn, dev_id, lat, lon, now_ts)

                success_count += 1
                logger.info(
                    "Poll successful: %s (%s) -> Lat: %.6f, Lon: %.6f at %d",
                    dev_id,
                    dev_name,
                    lat,
                    lon,
                    now_ts,
                )
            except Exception as e:
                failure_count += 1
                logger.error(
                    "Polling failure for device %s (%s): %s", dev_id, dev_name, e
                )
                # Failure for one device never stops others or crashes the poller

        summary = {
            "success": success_count,
            "failure": failure_count,
            "total": device_count,
        }
        logger.info("Polling cycle finished. Summary: %s", summary)
        return summary

    async def _run_loop(self) -> None:
        """Main loop that invokes poll_once periodically until stopped."""
        # Initial poll immediately on startup
        try:
            await self.poll_once()
        except Exception as e:
            logger.error("Unexpected error in initial polling cycle: %s", e)

        while not self._stop_event.is_set():
            try:
                # Wait for the interval or until stop_event is set
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.interval_seconds
                )
                # If we woke up without timeout, stop_event was set
                break
            except asyncio.TimeoutError:
                # Interval elapsed, run next poll cycle
                if self._stop_event.is_set():
                    break
                try:
                    await self.poll_once()
                except Exception as e:
                    logger.error("Unexpected error in periodic polling cycle: %s", e)
            except asyncio.CancelledError:
                break
