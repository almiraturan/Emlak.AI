from __future__ import annotations

from app.providers.base import ListingProvider
from app.providers.emlakjet import EmlakjetProvider
from app.providers.hepsiemlak import HepsiemlakProvider
from app.providers.sahibinden import SahibindenProvider


_PROVIDERS: dict[str, ListingProvider] = {
    "emlakjet": EmlakjetProvider(),
    "hepsiemlak": HepsiemlakProvider(),
    "sahibinden": SahibindenProvider(),
}


def get_provider(name: str) -> ListingProvider:
    provider = _PROVIDERS.get(name)
    if provider is None:
        supported = ", ".join(sorted(_PROVIDERS))
        raise ValueError(f"Unknown provider '{name}'. Supported providers: {supported}")
    return provider


def get_default_provider() -> ListingProvider:
    return get_provider("emlakjet")


def list_providers() -> list[str]:
    return sorted(_PROVIDERS)
