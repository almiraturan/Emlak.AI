from app.providers.base import RawListingPayload
from app.providers.registry import get_default_provider


def _default_provider():
    return get_default_provider()


def fetch_demo_external_listings() -> list[RawListingPayload]:
    # Geriye donuk uyumluluk icin mevcut API korunur; varsayilan canli provider kullanilir.
    return _default_provider().fetch_listings()
