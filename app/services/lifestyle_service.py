import asyncio
from typing import Dict, List

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db
from app.models import Listing


# POI categories and their weights
POI_CATEGORIES = {
    'transport': {
        'tags': [
            ('highway', 'bus_stop'),
            ('railway', 'station'),
            ('public_transport', 'platform'),
            ('public_transport', 'station'),
            ('amenity', 'bus_station'),
            ('amenity', 'train_station')
        ],
        'weight': 0.3,
        'max_count': 5
    },
    'education': {
        'tags': [
            ('amenity', 'school'),
            ('amenity', 'university'),
            ('amenity', 'college'),
            ('amenity', 'kindergarten')
        ],
        'weight': 0.2,
        'max_count': 3
    },
    'green': {
        'tags': [
            ('leisure', 'park'),
            ('leisure', 'garden'),
            ('landuse', 'forest'),
            ('natural', 'wood')
        ],
        'weight': 0.2,
        'max_count': 4
    },
    'shopping': {
        'tags': [
            ('shop', 'supermarket'),
            ('shop', 'mall'),
            ('shop', 'department_store'),
            ('shop', 'convenience'),
            ('amenity', 'market')
        ],
        'weight': 0.15,
        'max_count': 3
    },
    'security': {
        'tags': [
            ('amenity', 'police'),
            ('amenity', 'fire_station'),
            ('amenity', 'hospital'),
            ('amenity', 'clinic')
        ],
        'weight': 0.15,
        'max_count': 2
    }
}


def build_overpass_query(lat: float, lng: float, radius: int = 1000) -> str:
    """Build an Overpass query for the relevant lifestyle POI tags."""
    query_lines = ["[out:json][timeout:25];", "("]
    seen_filters = set()
    for category in POI_CATEGORIES.values():
        for tag_key, tag_value in category['tags']:
            filter_key = (tag_key, tag_value)
            if filter_key in seen_filters:
                continue
            seen_filters.add(filter_key)
            query_lines.append(f"  node(around:{radius},{lat},{lng})[{tag_key}={tag_value}];")
            query_lines.append(f"  way(around:{radius},{lat},{lng})[{tag_key}={tag_value}];")
            query_lines.append(f"  relation(around:{radius},{lat},{lng})[{tag_key}={tag_value}];")

    query_lines.append(")")
    query_lines.append("out center tags;")
    return "\n".join(query_lines)


async def fetch_nearby_places(lat: float, lng: float, radius: int = 1000) -> List[Dict]:
    """Fetch nearby POIs from OpenStreetMap Overpass API."""
    url = settings.overpass_url
    query = build_overpass_query(lat, lng, radius)
    headers = {
        'User-Agent': settings.user_agent,
        'Accept': 'application/json'
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, data=query, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get('elements', [])
        except Exception:
            return []


async def geocode_address(address: str, limit: int = 5) -> List[Dict]:
    """Geocode a text address using Nominatim."""
    url = f"{settings.nominatim_url}/search"
    params = {
        'q': address,
        'format': 'json',
        'addressdetails': 1,
        'limit': limit
    }
    headers = {
        'User-Agent': settings.user_agent,
        'Accept': 'application/json'
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception:
            return []


async def reverse_geocode(lat: float, lng: float) -> Dict[str, str] | None:
    """Reverse geocode coordinates using Nominatim."""
    url = f"{settings.nominatim_url}/reverse"
    params = {
        'lat': lat,
        'lon': lng,
        'format': 'json',
        'addressdetails': 1
    }
    headers = {
        'User-Agent': settings.user_agent,
        'Accept': 'application/json'
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None


def categorize_pois(elements: List[Dict]) -> Dict[str, int]:
    """Categorize OSM elements into our POI categories."""
    counts = {cat: 0 for cat in POI_CATEGORIES}

    for element in elements:
        tags = element.get('tags', {}) or {}
        for category, config in POI_CATEGORIES.items():
            for tag_key, tag_value in config['tags']:
                if tags.get(tag_key) == tag_value:
                    counts[category] += 1
                    break
            else:
                continue
            break

    return counts


def calculate_lifestyle_score(poi_counts: Dict[str, int]) -> float:
    """Calculate lifestyle score from POI counts (1-10 scale)."""
    total_score = 0.0

    for category, count in poi_counts.items():
        config = POI_CATEGORIES[category]
        # Normalize to 0-10 based on max_count
        category_score = min(count / config['max_count'], 1.0) * 10
        total_score += category_score * config['weight']

    # Ensure score is between 1-10
    return max(1.0, min(10.0, total_score))


async def update_listing_lifestyle_score(listing_id: int):
    """Update lifestyle score for a listing using Overpass API."""
    db = next(get_db())
    try:
        listing = db.query(Listing).filter(Listing.id == listing_id).first()
        if not listing or not listing.latitude or not listing.longitude:
            return

        # Fetch nearby places
        places = await fetch_nearby_places(listing.latitude, listing.longitude)

        # Skip if API returned nothing — likely a timeout/rate-limit, not truly 0 POIs
        if not places:
            return

        # Categorize POIs
        poi_counts = categorize_pois(places)

        # Calculate score
        score = calculate_lifestyle_score(poi_counts)

        # Update listing
        listing.lifestyle_score = score
        db.commit()

    finally:
        db.close()


# Dramatiq task for background processing
import dramatiq

@dramatiq.actor
def update_lifestyle_score_task(listing_id: int):
    """Dramatiq task to update lifestyle score in background."""
    asyncio.run(update_listing_lifestyle_score(listing_id))