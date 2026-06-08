from __future__ import annotations

import re
from hashlib import sha1
from typing import Any

from app.core.config import settings
from app.providers.base import ListingProvider, ProviderCapabilities, RawListingPayload
from app.providers.web_utils import fetch_text, first_present, to_str, walk_dict_candidates
from app.services.listing_normalizer import normalize_listing_payload


class HepsiemlakProvider(ListingProvider):
    name = "hepsiemlak"

    def _search_url(self) -> str:
        return getattr(settings, "hepsiemlak_search_url", "https://www.hepsiemlak.com/istanbul-satilik")

    def _max_items(self) -> int:
        return getattr(settings, "provider_max_items", 20)

    def _timeout(self) -> int:
        return getattr(settings, "provider_request_timeout_seconds", 30)

    def fetch_listings(self) -> list[RawListingPayload]:
        html = fetch_text(self._search_url(), timeout_seconds=self._timeout())

        # Try __NEXT_DATA__ extraction first
        results = self._extract_from_next_data(html)
        if results:
            return results[: self._max_items()]

        # Fallback: regex-based extraction
        results = self._extract_from_regex(html)
        return results[: self._max_items()]

    def fetch_listing_detail(self, source_listing_id: str) -> RawListingPayload | None:
        return None

    def normalize(self, raw_payload: RawListingPayload, *, fallback_source_listing_id: str):
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

    def _extract_from_next_data(self, html: str) -> list[RawListingPayload]:
        import json

        match = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not match:
            return []

        try:
            data = json.loads(match.group(1))
        except Exception:
            return []

        results: list[RawListingPayload] = []
        for node in walk_dict_candidates(data):
            mapped = self._map_candidate(node)
            if mapped is not None:
                results.append(mapped)
                if len(results) >= self._max_items():
                    break

        return results

    def _map_candidate(self, node: dict[str, Any]) -> RawListingPayload | None:
        # Hepsiemlak listing URLs follow /ilan/{slug} or /satilik/{slug}
        listing_url = to_str(first_present(node, ["url", "seoUrl", "detailUrl", "link", "slug"]))
        if listing_url:
            if listing_url.startswith("/"):
                listing_url = f"https://www.hepsiemlak.com{listing_url}"
        else:
            return None

        # Must look like a real listing URL
        if not any(p in listing_url for p in ["/ilan/", "/satilik/", "/kiralik/", "hepsiemlak.com"]):
            return None

        title = to_str(first_present(node, ["title", "listingTitle", "header", "name", "baslik"]))
        price = first_present(node, ["price", "fiyat", "listingPrice", "amount"])
        if isinstance(price, dict):
            price = first_present(price, ["value", "amount", "text", "formattedPrice"])

        area_m2 = first_present(node, [
            "grossSquareMeter", "netSquareMeter", "m2", "area",
            "brutM2", "netM2", "squareMeter", "alan"
        ])
        room_layout = to_str(first_present(node, [
            "roomType", "room", "odaSayisi", "roomCount", "roomText", "oda"
        ]))

        location = first_present(node, ["location", "locationInfo", "address", "konum"]) or {}
        if isinstance(location, str):
            location = {}

        city = to_str(first_present(location, ["city", "cityName", "sehir"]) or
                      first_present(node, ["city", "cityName", "sehir"]))
        district = to_str(first_present(location, ["district", "districtName", "ilce"]) or
                         first_present(node, ["district", "districtName", "ilce"]))
        neighborhood = to_str(first_present(location, ["neighborhood", "mahalle", "quarter"]) or
                             first_present(node, ["neighborhood", "mahalle"]))

        if city is None:
            city = "İstanbul"

        signals = sum(v is not None for v in [title, price, area_m2, district])
        if signals < 3:
            return None

        source_listing_id = to_str(first_present(node, ["id", "listingId", "ilanNo", "itemId"]))
        if source_listing_id is None:
            source_listing_id = sha1((listing_url or title or "").encode()).hexdigest()[:16]

        images_raw = first_present(node, ["images", "photos", "resimler", "imageList"])
        images: list[str] = []
        if isinstance(images_raw, list):
            images = [str(i).strip() for i in images_raw if str(i).strip()]
        elif isinstance(images_raw, str) and images_raw.strip():
            images = [images_raw.strip()]

        lat = first_present(node, ["latitude", "lat", "enlem"])
        lon = first_present(node, ["longitude", "lng", "lon", "boylam"])
        if isinstance(node.get("coordinates"), dict):
            lat = lat or node["coordinates"].get("lat")
            lon = lon or node["coordinates"].get("lng") or node["coordinates"].get("lon")

        return {
            "source": self.name,
            "source_listing_id": source_listing_id,
            "title": title,
            "price": price,
            "currency": "TRY",
            "area_m2": area_m2,
            "room_layout_raw": room_layout,
            "room_count_total": room_layout,
            "city": city,
            "district": district,
            "neighborhood": neighborhood or district,
            "source_url": listing_url,
            "images": images,
            "image_count": len(images),
            "listing_type": "satilik",
            "property_type": "daire",
            "latitude": lat,
            "longitude": lon,
            "published_at": first_present(node, ["createdAt", "publishedAt", "date", "tarih"]),
        }

    def _extract_from_regex(self, html: str) -> list[RawListingPayload]:
        """Regex fallback when Next.js data can't be parsed."""
        flattened = html.replace('\\"', '"')

        # Hepsiemlak listing IDs in URLs: /ilan/123456 or slugs
        url_pattern = re.compile(r'"(?:seoUrl|url|detailUrl)":\s*"(/(?:ilan|[a-z]+-satilik|[a-z]+-kiralik)/[^"]+)"')

        seen: set[str] = set()
        results: list[RawListingPayload] = []

        for m in url_pattern.finditer(flattened):
            raw_url = m.group(1)
            slug = raw_url.rsplit("/", 1)[-1].strip()
            if not slug or slug in seen:
                continue

            start = max(0, m.start() - 2000)
            end = min(len(flattened), m.end() + 2000)
            window = flattened[start:end]

            title_m = re.search(r'"(?:title|baslik|header)"\s*:\s*"([^"]{5,100})"', window)
            price_m = re.search(r'"(?:price|fiyat|amount)"\s*:\s*(\d[\d,.]+)', window)
            area_m = re.search(r'"(?:grossSquareMeter|netM2|m2|alan)"\s*:\s*(\d+(?:\.\d+)?)', window)
            district_m = re.search(r'"(?:districtName|ilce|district)"\s*:\s*"([^"]{2,50})"', window)
            room_m = re.search(r'"(?:roomType|odaSayisi|roomCount)"\s*:\s*"([^"]{2,20})"', window)

            if not (title_m and price_m and district_m):
                continue

            seen.add(slug)
            results.append({
                "source": self.name,
                "source_listing_id": slug,
                "title": title_m.group(1),
                "price": price_m.group(1),
                "currency": "TRY",
                "area_m2": area_m.group(1) if area_m else None,
                "room_layout_raw": room_m.group(1) if room_m else None,
                "room_count_total": room_m.group(1) if room_m else None,
                "city": "İstanbul",
                "district": district_m.group(1),
                "neighborhood": district_m.group(1),
                "source_url": f"https://www.hepsiemlak.com{raw_url}",
                "listing_type": "satilik",
                "property_type": "daire",
            })
            if len(results) >= self._max_items():
                break

        return results
