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
    ) -> tuple[Dict[str, int], Dict[str, float | None], Dict[str, list[str]], list[dict]]:
        """
        Fetch POIs within radius using a single combined Overpass API query.

        Args:
            latitude: Location latitude
            longitude: Location longitude
            radius_m: Search radius in meters (default 1km)

        Returns:
            Tuple: (POI counts by type, nearest distance in km by type, POI names by type, school_details)
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
        school_details = []

        if latitude is None or longitude is None:
            return pois, nearest_distances_km, poi_names, []

        try:
            # Combined query for all POI types
            overpass_query = (
                "[out:json][timeout:30];"
                "("
                f"nwr[\"amenity\"=\"school\"](around:{radius_m},{latitude},{longitude});"
                f"nwr[\"amenity\"=\"university\"](around:{radius_m},{latitude},{longitude});"
                f"nwr[\"amenity\"=\"college\"](around:{radius_m},{latitude},{longitude});"
                f"nwr[\"amenity\"=\"kindergarten\"](around:{radius_m},{latitude},{longitude});"
                f"nwr[\"amenity\"=\"hospital\"](around:{radius_m},{latitude},{longitude});"
                f"nwr[\"highway\"=\"bus_stop\"](around:1000,{latitude},{longitude});"
                f"nwr[\"railway\"=\"subway_entrance\"](around:1000,{latitude},{longitude});"
                f"nwr[\"railway\"=\"station\"][\"station\"=\"subway\"](around:1000,{latitude},{longitude});"
                f"nwr[\"railway\"=\"tram_stop\"](around:1000,{latitude},{longitude});"
                f"nwr[\"leisure\"=\"park\"](around:{radius_m},{latitude},{longitude});"
                f"nwr[\"shop\"=\"supermarket\"](around:{radius_m},{latitude},{longitude});"
                f"nwr[\"amenity\"=\"restaurant\"](around:{radius_m},{latitude},{longitude});"
                ");"
                "out center qt;"
            )

            # Define mirror list in case the main one rate-limits
            OVERPASS_ENDPOINTS = [
                "https://overpass-api.de/api/interpreter",
                "https://lz4.overpass-api.de/api/interpreter",
                "https://z.overpass-api.de/api/interpreter",
                "https://overpass.kumi.systems/api/interpreter",
                "https://overpass.nchc.org.tw/api/interpreter",
            ]

            response = None
            for endpoint in OVERPASS_ENDPOINTS:
                try:
                    response = httpx.post(
                        endpoint,
                        data={"data": overpass_query},
                        headers=OVERPASS_HEADERS,
                        timeout=OVERPASS_TIMEOUT,
                    )
                    if response.status_code == 200:
                        break
                    else:
                        logger.warning(f"Mirror {endpoint} returned status {response.status_code}, trying next...")
                except httpx.TimeoutException:
                    logger.warning(f"Mirror {endpoint} timed out, trying next...")
                except Exception as e:
                    logger.warning(f"Mirror {endpoint} failed: {e}, trying next...")

            if response and response.status_code == 200:
                data = response.json()
                elements = data.get("elements", [])
                
                # Separate elements into their respective lists
                categorized_elements = {
                    "school": [],
                    "hospital": [],
                    "bus": [],
                    "subway": [],
                    "park": [],
                    "supermarket": [],
                    "restaurant": []
                }

                for el in elements:
                    if not isinstance(el, dict):
                        continue
                    tags = el.get("tags") if isinstance(el.get("tags"), dict) else {}
                    
                    # 1. School / Education
                    if tags.get("amenity") in ("school", "university", "college", "kindergarten"):
                        categorized_elements["school"].append(el)
                    # 2. Hospital
                    elif tags.get("amenity") == "hospital":
                        categorized_elements["hospital"].append(el)
                    # 3. Bus Stop
                    elif tags.get("highway") == "bus_stop":
                        categorized_elements["bus"].append(el)
                    # 4. Subway / Station / Tram
                    elif tags.get("railway") == "subway_entrance" or (tags.get("railway") == "station" and tags.get("station") == "subway") or tags.get("railway") == "tram_stop":
                        categorized_elements["subway"].append(el)
                    # 5. Park
                    elif tags.get("leisure") == "park":
                        categorized_elements["park"].append(el)
                    # 6. Supermarket
                    elif tags.get("shop") == "supermarket":
                        categorized_elements["supermarket"].append(el)
                    # 7. Restaurant
                    elif tags.get("amenity") == "restaurant":
                        categorized_elements["restaurant"].append(el)

                # Process details for each category
                for poi_type, el_list in categorized_elements.items():
                    pois[poi_type] = len(el_list)
                    nearest_distances_km[poi_type] = self._nearest_distance_km(
                        latitude,
                        longitude,
                        el_list,
                    )
                    poi_names[poi_type] = self._extract_poi_names(el_list, poi_type)

                    # Extract detailed school metadata
                    if poi_type == "school":
                        for element in el_list:
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
                            sch_lat = element.get("lat")
                            sch_lon = element.get("lon")
                            if (sch_lat is None or sch_lon is None) and isinstance(element.get("center"), dict):
                                sch_lat = element["center"].get("lat")
                                sch_lon = element["center"].get("lon")
                            
                            dist_km = None
                            if sch_lat is not None and sch_lon is not None:
                                dist_km = self._haversine_km(latitude, longitude, sch_lat, sch_lon)

                            category = self._classify_school(name, tags)
                            school_details.append({
                                "name": str(name).strip(),
                                "category": category,
                                "distance_km": round(dist_km, 3) if dist_km is not None else None
                            })
            else:
                logger.error("All Overpass API endpoints failed or returned errors.")
        except Exception as e:
            logger.error(f"Error fetching POIs: {e}")

        return pois, nearest_distances_km, poi_names, school_details

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
            pois, nearest_distances_km, poi_names, school_details = self.get_pois_nearby(
                latitude,
                longitude,
                radius_m=radius_m,
            )

            # Step 2: Augmented Generation - send to LLM
            if sum(pois.values()) > 0:
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
                            "school_details": school_details,
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
                "school_details": school_details,
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
                "school_details": [],
                "search_radius_km": 5.0,
                "transit_search_radius_km": 1.0,
                "source": "error",
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
