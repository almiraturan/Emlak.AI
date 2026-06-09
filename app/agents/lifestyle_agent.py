"""Lifestyle Scoring using RAG with Overpass API."""
import logging
import math
from typing import Dict
import httpx

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

# Overpass API endpoints (tried in order on failure/rate-limit)
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]
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

# Radius within which POIs are counted normally (metres)
CATEGORY_COUNT_RADIUS_M = {
    "school": 1000,
    "hospital": 3000,
    "bus": 1000,
    "subway": 1000,
    "park": 1000,
    "supermarket": 1000,
    "restaurant": 1000,
}

# Wider search radius so we can always find the nearest POI (metres)
CATEGORY_SEARCH_RADIUS_M = {
    "school": 5000,
    "hospital": 5000,
    "bus": 5000,
    "subway": 5000,
    "park": 5000,
    "supermarket": 2000,
    "restaurant": 2000,
}


class LifestyleAgent(BaseAgent):
    """Lifestyle Scoring using RAG (Overpass API + Mistral LLM)."""

    def __init__(self):
        super().__init__()

    # Maps OSM tags → our internal POI category
    _TAG_CATEGORY_MAP = [
        (("amenity", "school"),          "school"),
        (("amenity", "university"),      "school"),
        (("amenity", "college"),         "school"),
        (("amenity", "kindergarten"),     "school"),
        (("amenity", "hospital"),        "hospital"),
        (("highway", "bus_stop"),        "bus"),
        (("railway", "subway_entrance"), "subway"),
        (("leisure", "park"),            "park"),
        (("shop", "supermarket"),        "supermarket"),
        (("amenity", "restaurant"),      "restaurant"),
    ]
    def get_pois_nearby(
        self, latitude: float, longitude: float, radius_m: int = 1000
    ) -> tuple[Dict[str, int], Dict[str, float | None], Dict[str, list[str]], list[dict]]:
        """
        Fetch POIs with a single batched Overpass query.

        Each category uses its own count radius (CATEGORY_COUNT_RADIUS_M).
        A wider search radius (CATEGORY_SEARCH_RADIUS_M) ensures we always
        find the nearest POI even when nothing is within the count radius.

        Returns:
            Tuple: (pois, nearest_distances_km, poi_names, school_details)
        """
        pois: Dict[str, int] = {k: 0 for _, k in self._TAG_CATEGORY_MAP}
        nearest_distances_km: Dict[str, float | None] = {k: None for _, k in self._TAG_CATEGORY_MAP}
        poi_names: Dict[str, list[str]] = {k: [] for _, k in self._TAG_CATEGORY_MAP}
        school_details = []

        if latitude is None or longitude is None:
            return pois, nearest_distances_km, poi_names, []

        # Use per-category SEARCH radius in the query so we can always find the nearest.
        # Use `node` for bus/subway (always point features) and `nwr` only for area features.
        sr = CATEGORY_SEARCH_RADIUS_M
        overpass_query = (
            "[out:json][timeout:30];\n(\n"
            f'  nwr["amenity"="school"](around:{sr["school"]},{latitude},{longitude});\n'
            f'  nwr["amenity"="university"](around:{sr["school"]},{latitude},{longitude});\n'
            f'  nwr["amenity"="college"](around:{sr["school"]},{latitude},{longitude});\n'
            f'  nwr["amenity"="kindergarten"](around:{sr["school"]},{latitude},{longitude});\n'
            f'  nwr["amenity"="hospital"](around:{sr["hospital"]},{latitude},{longitude});\n'
            f'  node["highway"="bus_stop"](around:{sr["bus"]},{latitude},{longitude});\n'
            f'  node["railway"="subway_entrance"](around:{sr["subway"]},{latitude},{longitude});\n'
            f'  nwr["leisure"="park"](around:{sr["park"]},{latitude},{longitude});\n'
            f'  node["shop"="supermarket"](around:{sr["supermarket"]},{latitude},{longitude});\n'
            f'  node["amenity"="restaurant"](around:{sr["restaurant"]},{latitude},{longitude});\n'
            ");\nout center tags qt;"
        )

        try:
            response = None
            for endpoint in OVERPASS_ENDPOINTS:
                try:
                    r = httpx.post(
                        endpoint,
                        data={"data": overpass_query},
                        headers=OVERPASS_HEADERS,
                        timeout=30,
                    )
                    if r.status_code == 200:
                        response = r
                        break
                    logger.warning("Overpass %s returned %s, trying next", endpoint, r.status_code)
                except httpx.TimeoutException:
                    logger.warning("Overpass %s timed out, trying next", endpoint)
                except Exception as e:
                    logger.warning("Overpass %s error: %s, trying next", endpoint, e)

            if response is None:
                logger.error("All Overpass endpoints failed")
                return pois, nearest_distances_km, poi_names, school_details

            elements = response.json().get("elements", [])

            # Bucket every element into its category
            buckets: Dict[str, list] = {k: [] for _, k in self._TAG_CATEGORY_MAP}
            for el in elements:
                tags = el.get("tags") or {}
                for (tag_key, tag_val), category in self._TAG_CATEGORY_MAP:
                    if tags.get(tag_key) == tag_val:
                        buckets[category].append(el)
                        break

            for category, els in buckets.items():
                count_r_km = CATEGORY_COUNT_RADIUS_M[category] / 1000.0

                # Split elements into "within count radius" and "outside"
                within, outside = [], []
                for el in els:
                    d = self._element_distance_km(latitude, longitude, el)
                    if d is not None and d <= count_r_km:
                        within.append((d, el))
                    else:
                        outside.append((d, el))

                # Count and names from within-radius set
                pois[category] = len(within)
                poi_names[category] = self._extract_poi_names([e for _, e in within], category)

                # Nearest is absolute nearest across ALL elements (within + outside)
                all_with_dist = [(d, el) for d, el in within + outside if d is not None]
                if all_with_dist:
                    nearest_d = min(d for d, _ in all_with_dist)
                    nearest_distances_km[category] = round(nearest_d, 3)

                    # If nothing within count radius, include the nearest element's name
                    if not poi_names[category]:
                        nearest_el = min(all_with_dist, key=lambda x: x[0])[1]
                        poi_names[category] = self._extract_poi_names([nearest_el], category)

                # Extract detailed school metadata
                if category == "school":
                    for d, element in within + outside:
                        tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
                        name = (
                            tags.get("name")
                            or tags.get("official_name")
                            or tags.get("short_name")
                            or tags.get("operator")
                            or tags.get("brand")
                            or tags.get("ref")
                            or "Unnamed school"
                        )
                        category_type = self._classify_school(name, tags)
                        school_details.append({
                            "name": str(name).strip(),
                            "category": category_type,
                            "distance_km": round(d, 3) if d is not None else None
                        })

        except Exception as e:
            logger.error("Error fetching POIs: %s", e)

        return pois, nearest_distances_km, poi_names, school_details

    def _element_distance_km(self, lat: float, lon: float, element: dict) -> float | None:
        """Compute distance in km from origin to a single Overpass element."""
        el_lat = element.get("lat")
        el_lon = element.get("lon")
        if (el_lat is None or el_lon is None) and isinstance(element.get("center"), dict):
            el_lat = element["center"].get("lat")
            el_lon = element["center"].get("lon")
        if el_lat is None or el_lon is None:
            return None
        return self._haversine_km(lat, lon, el_lat, el_lon)

    def score_lifestyle(
        self, latitude: float, longitude: float, radius_m: int = 5000
    ) -> Dict:
        """Score lifestyle quality using per-category radii (radius_m param is ignored)."""
        pois: Dict[str, int] = {}
        nearest_distances_km: Dict[str, float | None] = {}
        poi_names: Dict[str, list[str]] = {}
        school_details = []
        try:
            # radius_m kept for API compatibility but per-category radii are used internally
            pois, nearest_distances_km, poi_names, school_details = self.get_pois_nearby(
                latitude,
                longitude,
            )

            # Step 2: Augmented Generation - send to LLM (if available)
            if sum(pois.values()) > 0 and self.is_ollama_available():
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
                            "description": result.get("description", "Moderate lifestyle quality"),
                            "poi_counts": pois,
                            "nearest_distances_km": nearest_distances_km,
                            "poi_names": poi_names,
                            "school_details": school_details,
                            "category_radii_km": {k: v / 1000 for k, v in CATEGORY_COUNT_RADIUS_M.items()},
                            "search_radius_km": round(5000 / 1000.0, 2),
                            "transit_search_radius_km": 1.0,
                            "source": "llm",
                        }
            else:
                logger.debug("No POIs found, using rule-based scoring")

            # Fallback: Rule-based scoring
            score = self._calculate_rule_based_score(pois)
            return {
                "score": score,
                "description": f"{sum(pois.values())} yakın nokta bulundu" if sum(pois.values()) > 0 else "Yakında nokta bulunamadı",
                "poi_counts": pois,
                "nearest_distances_km": nearest_distances_km,
                "poi_names": poi_names,
                "school_details": school_details,
                "category_radii_km": {k: v / 1000 for k, v in CATEGORY_COUNT_RADIUS_M.items()},
                "search_radius_km": round(5000 / 1000.0, 2),
                "transit_search_radius_km": 1.0,
                "source": "rule_based",
            }

        except Exception as e:
            logger.error(f"Error scoring lifestyle: {e}")
            return {
                "score": self._calculate_rule_based_score(pois) if pois else 5.0,
                "description": "Kısmi veri ile hesaplandı" if pois else "Konum verisi alınamadı",
                "poi_counts": pois,
                "nearest_distances_km": nearest_distances_km,
                "poi_names": poi_names,
                "school_details": school_details,
                "category_radii_km": {k: v / 1000 for k, v in CATEGORY_COUNT_RADIUS_M.items()},
                "search_radius_km": 5.0,
                "transit_search_radius_km": 1.0,
                "source": "partial" if pois else "error",
            }

    def _turkish_lower(self, s: str) -> str:
        """Convert string to lowercase taking Turkish characters into account."""
        return s.replace("İ", "i").replace("I", "ı").lower()

    def _classify_school(self, name: str, tags: dict) -> str:
        """Classify school into primary, middle, high, daycare, university, or other."""
        name_lower = self._turkish_lower(name)
        amenity = tags.get("amenity", "")

        # 1. Daycare / Kindergarten / Bakımevi
        if (
            amenity == "kindergarten"
            or "bakımevi" in name_lower
            or "bakim evi" in name_lower
            or "kreş" in name_lower
            or "anaokulu" in name_lower
            or "gündüz bakım" in name_lower
            or "gunduz bakim" in name_lower
            or "kindergarten" in name_lower
            or "preschool" in name_lower
            or "daycare" in name_lower
            or "çocuk evi" in name_lower
            or "cocuk evi" in name_lower
        ):
            return "Bakımevi"

        # 2. University
        if (
            amenity in ("university", "college")
            or "üniversite" in name_lower
            or "universite" in name_lower
            or "university" in name_lower
            or "kampüs" in name_lower
            or "kampus" in name_lower
            or "fakülte" in name_lower
            or "fakulte" in name_lower
        ):
            return "Üniversite"

        # 3. High School (Lise)
        if (
            "lise" in name_lower
            or "high school" in name_lower
            or "fen lisesi" in name_lower
            or "anadolu lisesi" in name_lower
            or "mesleki ve teknik" in name_lower
            or "koleji" in name_lower
            or "kolej" in name_lower
        ):
            return "Lise"

        # 4. Middle School (Ortaokul)
        if (
            "ortaokul" in name_lower
            or "middle school" in name_lower
            or "imam hatip ortaokulu" in name_lower
        ):
            return "Ortaokul"

        # 5. Primary School (İlkokul)
        if (
            "ilkokul" in name_lower
            or "ilköğretim" in name_lower
            or "ilkogretim" in name_lower
            or "primary school" in name_lower
        ):
            return "İlkokul"

        return "Diğer"

    def _extract_poi_names(self, elements: list[dict], poi_type: str) -> list[str]:
        """Extract human-readable POI names from Overpass elements."""
        names: list[str] = []

        # For subway, build a list of stations to resolve unnamed entrances
        stations = []
        if poi_type == "subway":
            for element in elements:
                if not isinstance(element, dict):
                    continue
                tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
                railway = tags.get("railway")
                if railway in ("station", "tram_stop"):
                    lat = element.get("lat")
                    lon = element.get("lon")
                    if (lat is None or lon is None) and isinstance(element.get("center"), dict):
                        lat = element["center"].get("lat")
                        lon = element["center"].get("lon")

                    name = (
                        tags.get("name")
                        or tags.get("official_name")
                        or tags.get("short_name")
                    )
                    if name and lat is not None and lon is not None:
                        stations.append({
                            "name": str(name).strip(),
                            "lat": lat,
                            "lon": lon
                        })

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

            # Special resolution for subway entrances
            if poi_type == "subway" and tags.get("railway") == "subway_entrance":
                # Check if candidate is empty or just a number/ref
                is_unnamed_or_ref = (
                    not candidate
                    or str(candidate).isdigit()
                    or len(str(candidate)) <= 2
                    or "unnamed" in str(candidate).lower()
                )
                if is_unnamed_or_ref:
                    # Find coordinates of this entrance
                    ent_lat = element.get("lat")
                    ent_lon = element.get("lon")
                    if (ent_lat is None or ent_lon is None) and isinstance(element.get("center"), dict):
                        ent_lat = element["center"].get("lat")
                        ent_lon = element["center"].get("lon")

                    if ent_lat is not None and ent_lon is not None and stations:
                        # Find nearest station
                        nearest_station = None
                        min_dist = float("inf")
                        for station in stations:
                            dist = self._haversine_km(ent_lat, ent_lon, station["lat"], station["lon"])
                            if dist < min_dist:
                                min_dist = dist
                                nearest_station = station

                        # If station is within 0.5 km (500 meters)
                        if nearest_station and min_dist <= 0.5:
                            station_name = nearest_station["name"]
                            ref = tags.get("ref")
                            if ref:
                                candidate = f"{station_name} Metro Girişi ({ref})"
                            else:
                                candidate = f"{station_name} Metro Girişi"
                        else:
                            # Try to see if station tag is present on the entrance itself
                            station_tag = tags.get("station") or tags.get("railway:station")
                            if station_tag:
                                candidate = f"{station_tag} Metro Girişi"

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
