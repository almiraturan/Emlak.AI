"""Lifestyle Scoring using RAG with Overpass API."""
import logging
import math
from typing import Dict
import httpx

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

# Overpass API endpoint
OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 10  # seconds
OVERPASS_HEADERS = {
    "User-Agent": "EmlakAI/1.0 (contact: dev@localhost)",
    "Accept": "application/json",
}

# POI weights for rule-based scoring
POI_WEIGHTS = {
    "school": 1.5,
    "hospital": 2.0,
    "bus": 1.5,
    "subway": 2.5,
    "park": 1.0,
    "supermarket": 1.5,
    "restaurant": 0.5,
}


class LifestyleAgent(BaseAgent):
    """Lifestyle Scoring using RAG (Overpass API + Mistral LLM)."""

    def __init__(self):
        """Initialize the agent."""
        super().__init__()

    def get_pois_nearby(
        self, latitude: float, longitude: float, radius_m: int = 1000
    ) -> tuple[Dict[str, int], Dict[str, float | None], Dict[str, list[str]]]:
        """
        Fetch POIs within radius using Overpass API.

        Args:
            latitude: Location latitude
            longitude: Location longitude
            radius_m: Search radius in meters (default 1km)

        Returns:
            Tuple: (POI counts by type, nearest distance in km by type, POI names by type)
        """
        pois = {
            "school": 0,
            "hospital": 0,
            "bus": 0,
            "subway": 0,
            "park": 0,
            "supermarket": 0,
            "restaurant": 0,
        }
        nearest_distances_km: Dict[str, float | None] = {
            "school": None,
            "hospital": None,
            "bus": None,
            "subway": None,
            "park": None,
            "supermarket": None,
            "restaurant": None,
        }
        poi_names: Dict[str, list[str]] = {
            "school": [],
            "hospital": [],
            "bus": [],
            "subway": [],
            "park": [],
            "supermarket": [],
            "restaurant": [],
        }

        if latitude is None or longitude is None:
            return pois, nearest_distances_km, poi_names

        try:
            category_radius_m = {
                "school": radius_m,
                "hospital": radius_m,
                "bus": 1000,
                "subway": 1000,
                "park": radius_m,
                "supermarket": radius_m,
                "restaurant": radius_m,
            }

            queries = {
                "school": '"amenity"="school"',
                "hospital": '"amenity"="hospital"',
                "bus": '"highway"="bus_stop"',
                "subway": '"railway"="subway_entrance"',
                "park": '"leisure"="park"',
                "supermarket": '"shop"="supermarket"',
                "restaurant": '"amenity"="restaurant"',
            }

            for poi_type, overpass_filter in queries.items():
                category_radius = category_radius_m.get(poi_type, radius_m)
                overpass_query = (
                    "[out:json][timeout:25];"
                    f"(nwr[{overpass_filter}](around:{category_radius},{latitude},{longitude}););"
                    "out center qt;"
                )
                response = httpx.post(
                    OVERPASS_ENDPOINT,
                    data={"data": overpass_query},
                    headers=OVERPASS_HEADERS,
                    timeout=OVERPASS_TIMEOUT,
                )

                if response.status_code == 200:
                    data = response.json()
                    elements = data.get("elements", [])
                    pois[poi_type] = len(elements)
                    nearest_distances_km[poi_type] = self._nearest_distance_km(
                        latitude,
                        longitude,
                        elements,
                    )
                    poi_names[poi_type] = self._extract_poi_names(elements, poi_type)
                else:
                    logger.warning(
                        f"Overpass query failed for {poi_type}: {response.status_code}"
                    )

        except httpx.TimeoutException:
            logger.warning("Overpass API timeout, continuing with empty POI list")
        except Exception as e:
            logger.error(f"Error fetching POIs: {e}")

        return pois, nearest_distances_km, poi_names

    def score_lifestyle(
        self, latitude: float, longitude: float
    ) -> Dict:
        """
        Score lifestyle quality of a location using RAG.

        Args:
            latitude: Location latitude
            longitude: Location longitude

        Returns:
            Dictionary with score, description, and POI counts
        """
        try:
            # Step 1: Retrieval - fetch POIs
            radius_m = 5000
            pois, nearest_distances_km, poi_names = self.get_pois_nearby(
                latitude,
                longitude,
                radius_m=radius_m,
            )

            # Step 2: Augmented Generation - send to LLM (if available)
            if sum(pois.values()) > 0 and self.is_llm_available():
                # Format POI list for LLM
                poi_text = ", ".join(
                    [f"{k}: {v}" for k, v in pois.items() if v > 0]
                )

                prompt = f"""Based on the following nearby places, evaluate the lifestyle quality
of this property. Give a score from 1-10 and write a short English
explanation. Return only JSON, no extra text:
{{score: float, description: str}}
Places: {poi_text}"""

                response = self.call_llm(prompt)

                if response:
                    result = self.parse_json(response)
                    if result and "score" in result:
                        return {
                            "score": float(result.get("score", 5.0)),
                            "description": result.get(
                                "description", "Moderate lifestyle quality"
                            ),
                            "poi_counts": pois,
                            "nearest_distances_km": nearest_distances_km,
                            "poi_names": poi_names,
                            "search_radius_km": round(radius_m / 1000.0, 2),
                            "transit_search_radius_km": 1.0,
                            "source": "llm",
                        }
            else:
                logger.debug("No POIs found, using rule-based scoring")

            # Fallback: Rule-based scoring
            score = self._calculate_rule_based_score(pois)
            return {
                "score": score,
                "description": "Insufficient data for detailed analysis"
                if score == 5.0
                else f"Based on {sum(pois.values())} nearby places",
                "poi_counts": pois,
                "nearest_distances_km": nearest_distances_km,
                "poi_names": poi_names,
                "search_radius_km": round(radius_m / 1000.0, 2),
                "transit_search_radius_km": 1.0,
                "source": "rule_based",
            }

        except Exception as e:
            logger.error(f"Error scoring lifestyle: {e}")
            return {
                "score": 5.0,
                "description": "Error calculating lifestyle score",
                "poi_counts": {},
                "nearest_distances_km": {},
                "poi_names": {},
                "search_radius_km": 5.0,
                "transit_search_radius_km": 1.0,
                "source": "error",
            }

    def _extract_poi_names(self, elements: list[dict], poi_type: str) -> list[str]:
        """Extract human-readable POI names from Overpass elements."""
        names: list[str] = []

        for element in elements:
            if not isinstance(element, dict):
                continue

            tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
            candidate = (
                tags.get("name")
                or tags.get("official_name")
                or tags.get("short_name")
                or tags.get("operator")
                or tags.get("brand")
                or tags.get("ref")
            )

            if not candidate:
                candidate = f"Unnamed {poi_type}"

            text = str(candidate).strip()
            if text and text not in names:
                names.append(text)

        names.sort()
        return names

    def _nearest_distance_km(
        self,
        origin_lat: float,
        origin_lon: float,
        elements: list[dict],
    ) -> float | None:
        """Compute nearest POI distance in kilometers from Overpass elements."""
        nearest: float | None = None

        for element in elements:
            poi_lat = None
            poi_lon = None

            if isinstance(element, dict):
                poi_lat = element.get("lat")
                poi_lon = element.get("lon")

                # Ways/relations often expose coordinates under center.
                if (poi_lat is None or poi_lon is None) and isinstance(element.get("center"), dict):
                    center = element["center"]
                    poi_lat = center.get("lat")
                    poi_lon = center.get("lon")

            if poi_lat is None or poi_lon is None:
                continue

            distance_km = self._haversine_km(origin_lat, origin_lon, poi_lat, poi_lon)
            if nearest is None or distance_km < nearest:
                nearest = distance_km

        return round(nearest, 3) if nearest is not None else None

    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Haversine distance between two coordinates in kilometers."""
        radius_km = 6371.0

        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)

        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius_km * c

    def _calculate_rule_based_score(self, pois: Dict[str, int]) -> float:
        """Calculate lifestyle score using POI weights."""
        try:
            total_score = 0.0
            for poi_type, count in pois.items():
                weight = POI_WEIGHTS.get(poi_type, 1.0)
                total_score += min(count, 5) * weight

            # Normalize to 1-10 scale
            normalized_score = min(10.0, 1.0 + (total_score / 10.0))
            return float(normalized_score)
        except Exception as e:
            logger.error(f"Error in rule-based scoring: {e}")
            return 5.0

    def _get_bbox(
        self, latitude: float, longitude: float, radius_m: int
    ) -> str:
        """
        Get bounding box for Overpass query.

        Args:
            latitude: Center latitude
            longitude: Center longitude
            radius_m: Radius in meters

        Returns:
            Overpass bbox string (south,west,north,east)
        """
        # Simple approximation: 1 degree ≈ 111 km
        deg_radius = radius_m / 111000.0

        south = latitude - deg_radius
        north = latitude + deg_radius
        west = longitude - deg_radius
        east = longitude + deg_radius

        return f"({south},{west},{north},{east})"
