from __future__ import annotations

from hashlib import sha1
import re
from typing import Any

from app.core.config import settings
from app.providers.base import ListingProvider, ProviderCapabilities, RawListingPayload
from app.providers.web_utils import extract_json_blocks, fetch_text, first_present, to_str, walk_dict_candidates
from app.services.listing_normalizer import normalize_listing_payload


def canonize(s: str | None) -> str:
    if not s:
        return ""
    s = str(s).lower()
    for a, b in [('ı', 'i'), ('ğ', 'g'), ('ü', 'u'), ('ş', 's'), ('ö', 'o'), ('ç', 'c')]:
        s = s.replace(a, b)
    return "".join(c for c in s if c.isalnum())


class EmlakjetProvider(ListingProvider):
    name = "emlakjet"

    def _search_url(self) -> str:
        return settings.emlakjet_search_url

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

        if not results:
            return self._extract_from_embedded_payload(html)[: self._max_items()]

        return results

    def fetch_listing_detail(self, source_listing_id: str) -> RawListingPayload | None:
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
        listing_url = to_str(first_present(node, ["url", "link", "detailUrl", "seoUrl"]))
        if listing_url and listing_url.startswith("/"):
            listing_url = f"https://www.emlakjet.com{listing_url}"

        # Sadece gercek proje/listing kartlarini islemek icin temel pattern kontrolu.
        if listing_url is None or "/projeler/proje/" not in listing_url:
            return None

        location_info = first_present(node, ["locationInfo", "location", "address"]) or {}
        if not isinstance(location_info, dict):
            return None

        price_obj = first_present(node, ["price", "listingPrice", "amount", "priceDetail"])
        unit_types = first_present(node, ["unitTypes", "roomTypes"])
        first_unit = unit_types[0] if isinstance(unit_types, list) and unit_types and isinstance(unit_types[0], dict) else {}

        title = to_str(first_present(node, ["title", "name", "headline", "listingTitle"]))
        if title is not None and title.upper() in {"CASH", "DELAY", "INTEREST", "INSTALLMENT", "PESIN", "PEŞİN", "VADELI", "VADELİ"}:
            return None
        price = self._normalize_price(price_obj)
        area_m2 = first_present(node, ["grossSquareMeter", "grossSquareMeters", "m2", "area", "netSquareMeter"])
        if area_m2 is None and isinstance(first_unit, dict):
            area_m2 = first_present(first_unit, ["unitArea", "grossSquareMeter", "area"])

        room_layout = to_str(first_present(node, ["roomType", "room", "oda_sayisi", "roomCountText"]))
        if room_layout is None and isinstance(first_unit, dict):
            room_layout = to_str(first_present(first_unit, ["roomType", "room", "name"]))

        city = first_present(location_info, ["city", "cityName", "province"])
        district = first_present(location_info, ["district", "districtName", "town"])
        neighborhood = first_present(location_info, ["neighborhood", "neighborhoodName", "quarter", "districtName"])

        signal_count = sum(
            value is not None
            for value in [title, price, area_m2, city, district, neighborhood]
        )
        if signal_count < 5:
            return None

        image_value = first_present(node, ["images", "image", "coverImage", "photos"])
        images: list[str] = []
        if isinstance(image_value, list):
            images = [str(item).strip() for item in image_value if str(item).strip()]
        elif isinstance(image_value, str) and image_value.strip():
            images = [image_value.strip()]

        source_listing_id = to_str(first_present(node, ["id", "listingId", "itemId", "ilanNo"]))
        if source_listing_id is None:
            stable_key = listing_url or (title or "")
            if not stable_key:
                return None
            source_listing_id = sha1(stable_key.encode("utf-8")).hexdigest()[:16]

        listing_type = to_str(first_present(node, ["listingType", "type", "tradeType"]))
        if isinstance(node.get("tradeType"), dict):
            listing_type = listing_type or to_str(first_present(node["tradeType"], ["name", "slug", "id"]))
        property_type = to_str(first_present(node, ["propertyType", "categoryType", "estateType"]))
        if isinstance(node.get("estateType"), dict):
            property_type = property_type or to_str(first_present(node["estateType"], ["name", "slug", "id"]))

        if area_m2 is None:
            return None

        room_count_total = first_present(node, ["roomCount", "rooms"])
        if room_count_total is None and room_layout is not None:
            room_count_total = room_layout
        if room_count_total is None:
            return None

        currency = self._normalize_currency(first_present(node, ["currency", "currencyCode"]))
        if isinstance(price_obj, dict):
            currency = self._normalize_currency(first_present(price_obj, ["currency", "currencyCode"]))

        return {
            "source": self.name,
            "source_listing_id": source_listing_id,
            "title": title,
            "price": price,
            "currency": currency,
            "area_m2": area_m2,
            "room_layout_raw": room_layout,
            "room_count_total": room_count_total,
            "city": city,
            "district": district,
            "neighborhood": neighborhood,
            "source_url": listing_url,
            "images": images,
            "image_count": len(images),
            "listing_type": listing_type,
            "property_type": property_type,
            "latitude": first_present(node, ["lat", "latitude", "coordinates.lat"])
            or (node.get("coordinates", {}).get("lat") if isinstance(node.get("coordinates"), dict) else None),
            "longitude": first_present(node, ["lon", "lng", "longitude", "coordinates.lon"])
            or (node.get("coordinates", {}).get("lon") if isinstance(node.get("coordinates"), dict) else None),
            "published_at": first_present(node, ["createdAt", "publishedAt", "datePosted"]),
            "source_updated_at": first_present(node, ["updatedAt", "modifiedAt"]),
        }

    def _normalize_price(self, raw_price: Any) -> Any:
        if isinstance(raw_price, dict):
            return first_present(raw_price, ["startPrice", "minPrice", "maxPrice", "value", "amount"])
        return raw_price

    def _extract_from_embedded_payload(self, html: str) -> list[RawListingPayload]:
        # Next.js flight payloadlari parse edilemediginde proje URL'sini anchor alip yakin alanlari cikarir.
        flattened = html.replace('\\"', '"')
        url_pattern = re.compile(r'"url":"(?P<url>/projeler/proje/[^"]+)"')

        seen_ids: set[str] = set()
        results: list[RawListingPayload] = []
        for url_match in url_pattern.finditer(flattened):
            raw_url = url_match.group("url")
            listing_url = f"https://www.emlakjet.com{raw_url}"
            slug = raw_url.rsplit("/", 1)[-1].strip()
            if not slug or slug in seen_ids:
                continue

            start = max(0, url_match.start() - 3000)
            end = min(len(flattened), url_match.end() + 3000)
            window = flattened[start:end]

            names = re.findall(r'"name":"([^"]+)"', window)
            title = None
            blocked_names = {"CASH", "DELAY", "INTEREST", "INSTALLMENT", "PESIN", "PEŞİN", "VADELI", "VADELİ", "KONUT", "DAİRE", "DAIRE", "SATILIK", "SATILIK", "KİRALIK", "KIRALIK"}
            
            # 1. Exact canonical match with slug
            canonical_slug = canonize(slug)
            for n in names:
                if canonize(n) == canonical_slug:
                    title = n
                    break
            
            # 2. Substring match with slug (excluding generic words)
            if not title:
                for n in names:
                    cn = canonize(n)
                    if cn and cn.upper() not in blocked_names and len(cn) > 3:
                        if cn in canonical_slug or canonical_slug in cn:
                            title = n
                            break
            
            # 3. Fallback to first non-blocked name
            if not title:
                for n in names:
                    if n.upper() not in blocked_names:
                        title = n
                        break

            city_match = re.search(r'"cityName":"([^"]+)"', window)
            district_match = re.search(r'"districtName":"([^"]+)"', window)
            currency_match = re.search(r'"currency":"([^"]+)"', window)
            price_match = re.search(r'"startPrice":(\d+(?:\.\d+)?)|"minPrice":(\d+(?:\.\d+)?)', window)
            area_match = re.search(r'"unitArea":(\d+(?:\.\d+)?)', window)
            room_match = re.search(r'"roomType":"([^"]+)"', window)
            lat_match = re.search(r'"lat":(-?\d+(?:\.\d+)?)', window)
            lon_match = re.search(r'"lon":(-?\d+(?:\.\d+)?)', window)
            created_match = re.search(r'"createdAt":"([^"]+)"', window)
            updated_match = re.search(r'"updatedAt":"([^"]+)"', window)
            city = city_match.group(1) if city_match else None
            district = district_match.group(1) if district_match else None
            price = price_match.group(1) if price_match and price_match.group(1) else None
            if price_match and price is None:
                price = price_match.group(2)
            area_m2 = area_match.group(1) if area_match else None
            room_layout = room_match.group(1) if room_match else None
            room_total = room_layout if room_layout is not None else None

            if not all([title, city, district, price, area_m2, room_total]):
                continue

            seen_ids.add(slug)
            results.append(
                {
                    "source": self.name,
                    "source_listing_id": slug,
                    "title": title,
                    "price": price,
                    "currency": self._normalize_currency(currency_match.group(1) if currency_match else None),
                    "area_m2": area_m2,
                    "room_layout_raw": room_layout,
                    "room_count_total": room_total,
                    "city": city,
                    "district": district,
                    "neighborhood": district,
                    "source_url": listing_url,
                    "latitude": lat_match.group(1) if lat_match else None,
                    "longitude": lon_match.group(1) if lon_match else None,
                    "published_at": created_match.group(1) if created_match else None,
                    "source_updated_at": updated_match.group(1) if updated_match else None,
                }
            )
            if len(results) >= self._max_items():
                break

        return results

    def _normalize_currency(self, value: str | None) -> str:
        if value is None:
            return "TRY"
        code = value.upper()
        if code in {"TL", "TRY"}:
            return "TRY"
        if code in {"USD", "$"}:
            return "USD"
        if code in {"EUR", "€"}:
            return "EUR"
        if code in {"GBP", "£"}:
            return "GBP"
        return "TRY"
