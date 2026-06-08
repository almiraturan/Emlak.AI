import asyncio
import logging
from collections import defaultdict
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.listing import Listing
from app.models.location import Location

logger = logging.getLogger(__name__)

_NOMINATIM_DELAY = 1.1  # Nominatim ToS: max 1 req/sec


async def _nominatim_geocode(address: str) -> Optional[tuple[float, float]]:
    """Return (lat, lon) for the given address string, or None on failure."""
    url = f"{settings.nominatim_url}/search"
    params = {"q": address, "format": "json", "limit": 1, "countrycodes": "tr"}
    headers = {"User-Agent": settings.user_agent, "Accept": "application/json"}

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            results = resp.json()
            if results:
                return float(results[0]["lat"]), float(results[0]["lon"])
        except Exception as exc:
            logger.warning("Nominatim geocode failed for %r: %s", address, exc)
    return None


def _build_address(city: str, district: str, neighborhood: str) -> str:
    """Build a progressive address string for Nominatim, most specific first."""
    parts = [p for p in [neighborhood, district, city] if p]
    parts.append("Türkiye")
    return ", ".join(parts)


async def backfill_coordinates(db: Session) -> dict:
    """
    Geocode all active listings with NULL coordinates using Nominatim.

    Listings are grouped by their canonical (city, district, neighborhood)
    triplet so each unique location only requires one API call.
    Returns a summary dict: {total, geocoded_listings, failed_listings,
    unique_locations_tried, unique_locations_ok}.
    """
    missing = (
        db.query(Listing)
        .filter(
            Listing.is_active.is_(True),
            (Listing.latitude.is_(None) | Listing.longitude.is_(None)),
        )
        .all()
    )

    if not missing:
        return {
            "total": 0,
            "geocoded_listings": 0,
            "failed_listings": 0,
            "unique_locations_tried": 0,
            "unique_locations_ok": 0,
        }

    # Group by canonical triplet (fallback to raw names if canonicals absent)
    groups: dict[tuple, list[Listing]] = defaultdict(list)
    for listing in missing:
        key = (
            (listing.city_canonical or listing.city or "").lower().strip(),
            (listing.district_canonical or listing.district or "").lower().strip(),
            (listing.neighborhood_canonical or listing.neighborhood or "").lower().strip(),
        )
        groups[key].append(listing)

    geocoded = 0
    failed = 0
    locations_ok = 0

    for idx, ((city, district, neighborhood), group) in enumerate(groups.items()):
        if idx > 0:
            await asyncio.sleep(_NOMINATIM_DELAY)

        address = _build_address(city, district, neighborhood)
        coords = await _nominatim_geocode(address)

        # If neighborhood-level fails, fall back to district-level
        if coords is None and neighborhood:
            address_fallback = _build_address(city, district, "")
            await asyncio.sleep(_NOMINATIM_DELAY)
            coords = await _nominatim_geocode(address_fallback)

        if coords is None:
            logger.warning("Could not geocode: %s", address)
            failed += len(group)
            continue

        lat, lon = coords
        for listing in group:
            listing.latitude = lat
            listing.longitude = lon
        geocoded += len(group)
        locations_ok += 1

        # Update locations table centroid if the record exists and is NULL
        location_row = (
            db.query(Location)
            .filter(
                Location.city_canonical == city,
                Location.district_canonical == district,
                Location.neighborhood_canonical == neighborhood,
            )
            .first()
        )
        if location_row and location_row.centroid_latitude is None:
            location_row.centroid_latitude = lat
            location_row.centroid_longitude = lon

        logger.info(
            "Geocoded %d listing(s) for '%s' → (%.5f, %.5f)",
            len(group),
            address,
            lat,
            lon,
        )

    db.commit()

    return {
        "total": len(missing),
        "geocoded_listings": geocoded,
        "failed_listings": failed,
        "unique_locations_tried": len(groups),
        "unique_locations_ok": locations_ok,
    }


def get_centroid_for_listing(db: Session, listing: Listing) -> Optional[tuple[float, float]]:
    """
    Return the location-table centroid for a listing, or None.
    Used as a lightweight fallback when listing.latitude/longitude are NULL.
    """
    if not listing.location_id:
        # Try matching by canonical triplet
        city = (listing.city_canonical or listing.city or "").lower().strip()
        district = (listing.district_canonical or listing.district or "").lower().strip()
        neighborhood = (listing.neighborhood_canonical or listing.neighborhood or "").lower().strip()
        if not city:
            return None
        loc = (
            db.query(Location)
            .filter(
                Location.city_canonical == city,
                Location.district_canonical == district,
                Location.neighborhood_canonical == neighborhood,
                Location.centroid_latitude.isnot(None),
            )
            .first()
        )
    else:
        loc = (
            db.query(Location)
            .filter(
                Location.id == listing.location_id,
                Location.centroid_latitude.isnot(None),
            )
            .first()
        )

    if loc:
        return loc.centroid_latitude, loc.centroid_longitude
    return None
