from abc import ABC, abstractmethod
from typing import Optional, Tuple


class LocationProvider(ABC):
    """Abstract base class for device location providers."""

    @abstractmethod
    async def get_location(
        self, device_id: str, name: Optional[str] = None
    ) -> Optional[Tuple[float, float]]:
        """
        Fetches the current latitude and longitude for the given device ID.
        Returns (latitude, longitude) as a tuple of floats, or None / raises an exception on failure.
        """
        pass
