from __future__ import annotations

from hashlib import sha1
from typing import Any

from app.core.config import settings
from app.providers.base import ListingProvider, ProviderCapabilities, RawListingPayload
from app.providers.web_utils import extract_json_blocks, fetch_text, first_present, to_str, walk_dict_candidates
from app.services.listing_normalizer import normalize_listing_payload


class SahibindenProvider(ListingProvider):
    name = "sahibinden"

    def _search_url(self) -> str:
        return settings.sahibinden_search_url

    def _max_items(self) -> int:
        return settings.provider_max_items

    def _timeout(self) -> int:
        return settings.provider_request_timeout_seconds

    def fetch_listings(self) -> list[RawListingPayload]:
        html = fetch_text(self._search_url(), timeout_seconds=self._timeout())
        blocks = extract_json_blocks(html)

        results: list[RawListingPayload] = []
        for block in blocks:
            for node in walk_dict_candidates(block):
                mapped = self._map_candidate(node)
                if mapped is None:
                    continue
                results.append(mapped)
                if len(results) >= self._max_items():
                    return results

        return results

    def fetch_listing_detail(self, source_listing_id: str) -> RawListingPayload | None:
        # MVP asamada search kaynakli id ile detay endpointine gecis kurulmadigi icin None doner.
        _ = source_listing_id
        return None

    def normalize(
        self,
        raw_payload: RawListingPayload,
        *,
        fallback_source_listing_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return normalize_listing_payload(
            raw_payload=raw_payload,
            fallback_source=self.name,
            fallback_source_listing_id=fallback_source_listing_id,
        )

    def health_check(self) -> dict[str, object]:
        try:
            count = len(self.fetch_listings())
            return {"provider": self.name, "status": "ok", "fetched": count}
        except Exception as exc:
            return {"provider": self.name, "status": "error", "detail": str(exc)}

    def provider_type(self) -> str:
        return "browser"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_detail_fetch=False,
            supports_incremental_sync=False,
            supports_images=True,
            full_sync=True,
        )

    def _map_candidate(self, node: dict[str, Any]) -> RawListingPayload | None:
        title = to_str(first_present(node, ["title", "name", "heading", "ilanBaslik"]))
        price = first_present(node, ["price", "amount", "listingPrice", "value"])
        area_m2 = first_present(node, ["grossSquareMeters", "grossArea", "m2", "squareMeter", "area"])

        location = first_present(node, ["location", "address"]) or {}
        city = first_present(location, ["city", "cityName", "province"]) if isinstance(location, dict) else None
        district = (
            first_present(location, ["district", "town", "county"]) if isinstance(location, dict) else None
        )
        neighborhood = (
            first_present(location, ["neighborhood", "quarter", "areaName"]) if isinstance(location, dict) else None
        )

        # Kaydin listing adayi olmasi icin temel alanlardan en az ikisi beklenir.
        signal_count = sum(
            value is not None
            for value in [title, price, area_m2, city, district, neighborhood]
        )
        if signal_count < 3:
            return None

        listing_url = to_str(first_present(node, ["url", "link", "listingUrl", "detailUrl"]))
        room_layout = to_str(first_present(node, ["room", "roomCountText", "odaSayisi", "roomType"]))
        listing_type = to_str(first_present(node, ["listingType", "tradeType", "adType"]))
        property_type = to_str(first_present(node, ["propertyType", "category", "estateType"]))

        image_value = first_present(node, ["images", "image", "photos"])
        images: list[str] = []
        if isinstance(image_value, list):
            images = [str(item).strip() for item in image_value if str(item).strip()]
        elif isinstance(image_value, str) and image_value.strip():
            images = [image_value.strip()]

        source_listing_id = to_str(first_present(node, ["id", "listingId", "adId", "itemId"]))
        if source_listing_id is None:
            stable_key = listing_url or (title or "")
            if not stable_key:
                return None
            source_listing_id = sha1(stable_key.encode("utf-8")).hexdigest()[:16]

        return {
            "source": self.name,
            "source_listing_id": source_listing_id,
            "title": title,
            "price": price,
            "currency": first_present(node, ["currency", "currencyCode"]),
            "area_m2": area_m2,
            "room_layout_raw": room_layout,
            "room_count_total": first_present(node, ["roomCount", "rooms"]),
            "city": city,
            "district": district,
            "neighborhood": neighborhood,
            "source_url": listing_url,
            "images": images,
            "image_count": len(images),
            "listing_type": listing_type,
            "property_type": property_type,
            "latitude": first_present(node, ["lat", "latitude"]),
            "longitude": first_present(node, ["lon", "lng", "longitude"]),
            "published_at": first_present(node, ["publishedAt", "createdAt", "datePosted"]),
            "source_updated_at": first_present(node, ["updatedAt", "modifiedAt", "lastUpdateDate"]),
        }
