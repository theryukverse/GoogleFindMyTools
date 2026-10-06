from typing import Dict, Type
from tracker.providers.base import LocationProvider

_PROVIDERS: Dict[str, Type[LocationProvider]] = {}

try:
    from tracker.providers.google_find_my import GoogleFindMyProvider

    _PROVIDERS["google_find_my"] = GoogleFindMyProvider
except Exception:
    pass


def get_provider(name: str = "google_find_my") -> LocationProvider:
    """Factory to retrieve a configured location provider instance."""
    provider_key = (name or "google_find_my").strip().lower()
    if provider_key not in _PROVIDERS:
        raise ValueError(
            f"Unknown location provider '{provider_key}'. Available: {list(_PROVIDERS.keys())}"
        )
    return _PROVIDERS[provider_key]()
