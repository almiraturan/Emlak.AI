from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

RawListingPayload = dict[str, object]
ProviderKind = Literal["api", "browser", "hybrid"]


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_detail_fetch: bool = False
    supports_incremental_sync: bool = False
    supports_images: bool = True
    full_sync: bool = True


class ListingProvider(ABC):
    name: str

    @abstractmethod
    def fetch_listings(self) -> list[RawListingPayload]:
        """Fetch raw listing collection from the provider source."""

    @abstractmethod
    def fetch_listing_detail(self, source_listing_id: str) -> RawListingPayload | None:
        """Fetch a single listing detail payload by source id."""

    @abstractmethod
    def normalize(
        self,
        raw_payload: RawListingPayload,
        *,
        fallback_source_listing_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Normalize provider payload into the common ingestion model."""

    @abstractmethod
    def health_check(self) -> dict[str, object]:
        """Return provider availability/health details."""

    @abstractmethod
    def provider_type(self) -> ProviderKind:
        """Return strategy kind used by provider implementation."""

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()
