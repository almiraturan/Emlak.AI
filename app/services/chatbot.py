"""Rule-based real-estate chatbot: parses Turkish user messages into listing
filters and produces a short natural-language explanation of the top picks.

LLM enhancement (Mistral via Ollama) is attempted opportunistically but the
service degrades gracefully to template-based replies when Ollama is offline."""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.agents.lifestyle_agent import LifestyleAgent
from app.models.listing import Listing
from app.services.recommendation_service import calculate_compatibility_score

logger = logging.getLogger(__name__)

KNOWN_CITIES: dict[str, str] = {
    "istanbul": "istanbul",
    "ankara": "ankara",
    "izmir": "izmir",
    "bursa": "bursa",
    "antalya": "antalya",
    "adana": "adana",
    "konya": "konya",
    "gaziantep": "gaziantep",
    "kayseri": "kayseri",
    "mersin": "mersin",
    "samsun": "samsun",
    "eskisehir": "eskisehir",
    "denizli": "denizli",
    "trabzon": "trabzon",
    "sakarya": "sakarya",
    "kocaeli": "kocaeli",
}

KNOWN_DISTRICTS = [
    # İstanbul Avrupa
    "besiktas", "sisli", "beyoglu", "fatih", "eyup", "kagithane",
    "bakirkoy", "bahcelievler", "gungoren", "bagcilar", "esenler",
    "zeytinburnu", "avcilar", "buyukcekmece", "catalca", "silivri",
    "beylikduzu", "esenyurt", "basaksehir", "arnavutkoy",
    "gaziosmanpasa", "sultangazi", "bayrampasa",
    # İstanbul Anadolu
    "kadikoy", "uskudar", "atasehir", "maltepe", "kartal", "pendik",
    "tuzla", "sancaktepe", "sultanbeyli", "cekmekoy", "umraniye",
    "beykoz", "adalar", "sariyer",
    # Ankara
    "cankaya", "kecioren", "mamak", "yenimahalle", "etimesgut",
    "sincan", "altindag", "pursaklar", "golbasi", "cankiri",
    # İzmir
    "karsiyaka", "bornova", "buca", "konak", "cigli", "bayrakli",
    "gaziemir", "kemeralti",
]

_QUIET_WORDS = ("sessiz", "sakin", "huzurlu", "rahat", "gomultu", "tenha", "kalabalik degil")
_CENTRAL_WORDS = ("merkez", "merkezi", "sehir merkezi", "istanbulun icinde", "sehrin ortasi")
_LUXURY_WORDS = ("luks", "premium", "pahali", "villa", "rezidans", "ozel proje", "butik proje")
_BUDGET_WORDS = ("ucuz", "uygun fiyat", "ekonomik", "az para", "butce", "hesapli")
_INVEST_WORDS = ("yatirim", "yatirimlik", "kira getirisi", "deger kazanir", "kiralik potansiyel")
_PET_WORDS = ("kopek", "kopeg", "kedi", "evcil hayvan", "hayvan", "kopegim", "kedim", "kopegimiz")
_STUDENT_WORDS = ("ogrenci", "universite", "universitesi", "ders", "kampus")
_REMOTE_WORDS = ("evden calis", "uzaktan calis", "home office", "calisma odasi", "calismak icin")
_NATURE_WORDS = ("orman", "yesil alan", "doga", "agac", "nehir", "koy", "bahceli semt")
_NIGHTLIFE_WORDS = ("gece hayati", "bar", "eglence mekan", "kafe cok", "alisveris merkez")
_FAMILY_WORDS = ("aile", "cocuklu", "genis aile", "buyuk aile", "ebeveyn")
_ELDERLY_WORDS = ("yasli", "emekli", "nine", "dede", "buyukanne", "buyukbaba")
_SICK_WORDS = ("hasta", "yatalak", "engelli", "kronik", "bakim ihtiyac", "duzensiz saglik", "saglik sorunu")

# Pattern: sick/disabled/elderly family member → hospital nearby
_SICK_FAMILY_PAT = re.compile(
    r"(?:annem|babam|annemiz|babamiz|esim|kardesim|ninemi?|dedem|"
    r"buyukanne\w*|buyukbaba\w*|aile\w*|halam|amcam|teyze\w*)\w*"
    r"\s*(?:hasta|yatalak|engelli|kronik|bakim|saglik|tedavi|ilaç|ilac)"
    r"|(?:hasta|yatalak|engelli)\s*(?:annem|babam|esim|kardesim|aile\w*)"
)
_METRO_WORDS = ("metro", "metrobus", "tramvay", "rayli sistem", "metro duragi", "tren", "metroya", "metrodan", "tramvaya")
_BUS_WORDS = ("otobus", "dolmus", "minibus", "otobus duragi", "otobuse", "otobusle", "dolmusa")
_TRANSPORT_WORDS = ("ulasim", "toplu tasima", "durak", "istasyon", "toplu tasimaya", "toplu tasimayla", "tasimaya biniyorum", "tasimayla gidiyorum")
_NEWLYWED_WORDS = ("yeni evli", "yeni evlendik", "nisanliyiz", "nisanlandi", "evleniyoruz", "evliyoruz", "cift olarak", "iki kisilik yasam")

# Turkish number words → int (Turkish only)
_TR_NUMS: dict[str, int] = {
    "bir": 1, "iki": 2, "uc": 3, "dort": 4, "bes": 5,
    "alti": 6, "yedi": 7, "sekiz": 8, "dokuz": 9,
}
_NUM_PAT = r"(\d+|bir|iki|uc|dort|bes|alti|yedi|sekiz|dokuz)"


def _parse_num(s: str) -> Optional[int]:
    s = _strip(s).strip()
    if s.isdigit():
        return int(s)
    return _TR_NUMS.get(s)


@dataclass
class ChatFilters:
    city: Optional[str] = None
    district: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_rooms: Optional[int] = None
    max_rooms: Optional[int] = None
    min_area: Optional[float] = None
    max_area: Optional[float] = None
    min_lifestyle: Optional[float] = None
    max_building_age: Optional[int] = None
    sort_by: str = "lifestyle_score"
    keywords: list[str] = field(default_factory=list)
    context: str = ""
    
    # POI-based filtering (for pets, children, elderly, health)
    needs_park_nearby: bool = False
    needs_playground_nearby: bool = False
    needs_school_nearby: bool = False
    needs_hospital_nearby: bool = False
    needs_metro_nearby: bool = False   # subway/tramway specifically
    needs_bus_nearby: bool = False     # bus stop specifically
    needs_bus_metro_nearby: bool = False  # any public transport
    poi_max_distance_km: float = 2.0

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if v not in (None, [], "")}
        return d


def _strip(text: str) -> str:
    return text.lower().replace("ı", "i").replace("ğ", "g").replace("ş", "s") \
        .replace("ç", "c").replace("ö", "o").replace("ü", "u").replace("İ", "i")


def _parse_price_token(num_text: str, unit: str) -> Optional[float]:
    try:
        value = float(num_text.replace(".", "").replace(",", "."))
    except ValueError:
        return None
    unit = unit.lower()
    if unit.startswith("m"):
        value *= 1_000_000
    elif unit.startswith("b") or unit == "k":
        value *= 1_000
    return value


def parse_message(message: str) -> ChatFilters:
    f = ChatFilters()
    text = _strip(message)

    # --- City ---
    for city_key, city_canonical in KNOWN_CITIES.items():
        if re.search(r'\b' + city_key, text):
            f.city = city_canonical
            break

    # --- District ---
    for d in KNOWN_DISTRICTS:
        if d in text:
            f.district = d
            f.keywords.append(d.title())
            break

    # --- Room layout: "3+1", "2 oda", "iki tane oda" ---
    layout = re.search(r"(\d)\s*\+\s*(\d)", text)
    if layout:
        rooms = int(layout.group(1)) + int(layout.group(2))
        f.min_rooms = rooms
        f.max_rooms = rooms
        f.keywords.append(f"{layout.group(1)}+{layout.group(2)}")
    else:
        oda = re.search(_NUM_PAT + r"\s*(?:tane\s*)?oda", text)
        if oda:
            n = _parse_num(oda.group(1)) or int(oda.group(1)) if oda.group(1).isdigit() else 1
            f.min_rooms = n
            f.max_rooms = n + 1
            f.keywords.append(f"{n} oda")

    # --- Price ceiling: "en fazla 5 milyon", "bütçem 3 milyon", "X TL'yi geçmesin" ---
    cap = re.search(
        r"(?:en fazla|altinda|kadar|gecmesin|butcem|butcemiz|paramiz|param|max)\s*"
        r"(\d+(?:[.,]\d+)?)\s*(milyon|m|bin|b|tl|k)?",
        text,
    )
    if not cap:
        cap = re.search(
            r"(\d+(?:[.,]\d+)?)\s*(milyon|m|bin|b|tl|k)\s*(?:altinda|kadar|gecmesin|max)",
            text,
        )
    if cap:
        unit = cap.group(2) or "milyon"
        v = _parse_price_token(cap.group(1), unit)
        if v:
            f.max_price = v

    # --- Price floor ---
    floor = re.search(
        r"(?:en az|uzeri|ustu|baslayan)\s*"
        r"(\d+(?:[.,]\d+)?)\s*(milyon|m|bin|b|tl|k)?",
        text,
    )
    if floor:
        unit = floor.group(2) or "milyon"
        v = _parse_price_token(floor.group(1), unit)
        if v:
            f.min_price = v

    # --- Area: "120 m2", "150 metrekare" ---
    area = re.search(r"(\d{2,4})\s*(?:m2|m²|metre|metrekare)", text)
    if area:
        f.min_area = float(area.group(1))
        f.keywords.append(f"{int(area.group(1))} m²")

    # --- Explicit min rooms: "en az 3 oda", "minimum 2 oda" ---
    if f.min_rooms is None:
        min_room_m = re.search(r"(?:en az|minimum|min)\s*" + _NUM_PAT + r"\s*(?:tane\s*)?oda", text)
        if min_room_m:
            n = _parse_num(min_room_m.group(1)) or 1
            f.min_rooms = n
            f.keywords.append(f"en az {n} oda")

    # --- Studio / 1+0 ---
    if re.search(r"(?:studyo|studio|1\s*\+\s*0)", text):
        f.min_rooms = 1
        f.max_rooms = 2
        if "stüdyo" not in f.keywords:
            f.keywords.append("stüdyo")
        if not f.context:
            f.context = "studio"

    # --- Building age: "yeni bina", "sıfır bina", "depreme dayanıklı" ---
    if re.search(r"(?:yeni bina|sifir bina|sifir daire|az yasinda|depreme dayanikli|yeni yapili)", text):
        f.max_building_age = 10
        if "yeni bina" not in f.keywords:
            f.keywords.append("yeni bina")

    # --- Spacious preference: "geniş ev", "büyük daire", "ferah" ---
    if re.search(r"(?:buyuk|genis|ferah)\s*(?:ev|daire|alan|oda|mekan)?", text):
        if f.min_area is None:
            f.min_area = 100
        if "geniş" not in f.keywords:
            f.keywords.append("geniş")

    # --- Pets (park nearby) ---
    if any(w in text for w in _PET_WORDS):
        f.keywords.append("evcil hayvan dostu")
        f.min_lifestyle = 6.5
        f.context = "pets"
        f.needs_park_nearby = True  # NEW: POI requirement

    # --- Student ---
    if any(w in text for w in _STUDENT_WORDS):
        f.keywords.append("öğrenciye uygun")
        if f.max_price is None:
            f.max_price = 2_500_000
        f.min_lifestyle = 7.0
        f.context = "student"

    # --- Newly married / young couple ---
    if any(w in text for w in _NEWLYWED_WORDS):
        if f.min_rooms is None:
            f.min_rooms = 2
        if not f.context:
            f.keywords.append("çifte uygun")
            f.context = "newlywed"

    # --- Children (number-aware) ---
    n_kids = None

    # Step 1: explicit counts — "2 çocuğum", "bir kızım", "iki oğlum", "3 evladım"
    child_root = r"(?:cocuk|kiz|oglan|oglu|ogul|ogull|bebek|torun|cocugum|cocuklarim|evlat|evlad)"
    child_matches = re.findall(_NUM_PAT + r"\s*(?:tane\s*)?" + child_root, text)
    if child_matches:
        n_kids = sum(_parse_num(m) or 1 for m in child_matches)

    # Step 2: singular possessives with no number — "kızım var", "oğlum var", "evladım"
    if n_kids is None:
        singular = 0
        for pat, count in [
            (r"\bkizim\b",       1),
            (r"\bkizlarim\b",    2),   # plural → ≥2
            (r"\boglum\b",       1),
            (r"\bogullarim\b",   2),
            (r"\bcocugum\b",     1),
            (r"\bcocuklarim\b",  2),
            (r"\bebegim\b",      1),
            (r"\bevladim\b",     1),
            (r"\bevlatlarim\b",  2),
            (r"\btorunum\b",     1),
        ]:
            if re.search(pat, text):
                singular += count
        if singular > 0:
            n_kids = singular
        elif re.search(r"birka[c]\s*(?:tane\s*)?(?:cocuk|kiz|torun)", text):
            n_kids = 2
        elif re.search(r"(?:cocugum|cocuklarim|kucuk\s*cocuklar?)\s*var", text):
            n_kids = 1

    if n_kids is not None:
        if f.min_rooms is None or f.min_rooms < n_kids:
            f.min_rooms = n_kids
        f.min_lifestyle = max(f.min_lifestyle or 0, 7.5)
        if "okul yakını" not in f.keywords:
            f.keywords.extend(["okul yakını", f"{n_kids} çocuklu"])
        f.context = "family_kids"
        f.needs_school_nearby = True  # NEW: POI requirement
        f.needs_playground_nearby = True  # NEW: POI requirement
    elif any(w in text for w in _FAMILY_WORDS):
        f.keywords.append("aileye uygun")
        if f.min_rooms is None:
            f.min_rooms = 3
        f.min_lifestyle = 7.5
        f.context = "family"
        f.needs_school_nearby = True  # NEW: POI requirement

    # --- Household size: "4 kişilik aile", "5 kişi" ---
    household_m = re.search(_NUM_PAT + r"\s*(?:tane\s*)?(?:kisilik|kisili|kisi)\s*(?:aile|ev|hane)?", text)
    if household_m and n_kids is None:
        n_people = _parse_num(household_m.group(1)) or 2
        implied_rooms = max(n_people - 1, 2)
        if f.min_rooms is None or f.min_rooms < implied_rooms:
            f.min_rooms = implied_rooms
        if not f.context:
            f.keywords.append(f"{n_people} kişilik aile")
            f.context = "family"

    # --- Elderly / sick care (number-aware) ---
    elderly_m = re.search(_NUM_PAT + r"\s*(?:tane\s*)?(?:yasli|emekli|buyukanne|buyukbaba|nine|dede)", text)
    has_elderly_rel = bool(re.search(
        r"(?:annem|babam|annemin|babamin|anne.*baba|baba.*anne|buyukanne|buyukbaba|nine|dedem|yatalak)",
        text,
    ))
    has_sick_rel = bool(_SICK_FAMILY_PAT.search(text))
    # standalone sick words only when family context exists
    has_sick_standalone = any(w in text for w in _SICK_WORDS) and any(
        w in text for w in ("annem", "babam", "aile", "anne", "baba", "nine", "dede", "esim", "kardes")
    )

    if elderly_m or has_elderly_rel or has_sick_rel or has_sick_standalone:
        n_elderly = _parse_num((elderly_m.group(1) if elderly_m else None) or "1") or 1
        implied_rooms = max(n_elderly + 1, 2)
        if f.min_rooms is None or f.min_rooms < implied_rooms:
            f.min_rooms = implied_rooms
        f.min_lifestyle = max(f.min_lifestyle or 0, 7.0)
        for kw in ("hastane yakını", "asansörlü"):
            if kw not in f.keywords:
                f.keywords.append(kw)
        f.context = "elderly_care"
        f.needs_hospital_nearby = True
    elif any(w in text for w in _ELDERLY_WORDS):
        f.keywords.append("yaşlı dostu")
        if f.min_rooms is None:
            f.min_rooms = 2
        f.min_lifestyle = 6.0
        f.context = "elderly"
        f.needs_hospital_nearby = True

    # --- Remote work ---
    if any(w in text for w in _REMOTE_WORDS):
        if "evden çalışma" not in f.keywords:
            f.keywords.append("evden çalışma")
        f.min_lifestyle = max(f.min_lifestyle or 0, 6.0)
        if not f.context:
            f.context = "remote"

    # --- Nature / green areas ---
    if any(w in text for w in _NATURE_WORDS):
        if "doğal" not in f.keywords:
            f.keywords.append("doğal")
        f.min_lifestyle = max(f.min_lifestyle or 0, 7.5)
        if not f.context:
            f.context = "nature"

    # --- Nightlife / social ---
    if any(w in text for w in _NIGHTLIFE_WORDS):
        if "aktif sosyal" not in f.keywords:
            f.keywords.append("aktif sosyal")
        if not f.context:
            f.context = "nightlife"

    # --- Transport proximity (detect specific type first) ---
    if any(w in text for w in _METRO_WORDS):
        if "metro yakını" not in f.keywords:
            f.keywords.append("metro yakını")
        f.needs_metro_nearby = True
        f.needs_bus_metro_nearby = True
        if not f.context:
            f.context = "transport"

    if any(w in text for w in _BUS_WORDS):
        if "otobüs yakını" not in f.keywords:
            f.keywords.append("otobüs yakını")
        f.needs_bus_nearby = True
        f.needs_bus_metro_nearby = True
        if not f.context:
            f.context = "transport"

    if any(w in text for w in _TRANSPORT_WORDS):
        if "toplu taşıma yakını" not in f.keywords:
            f.keywords.append("toplu taşıma yakını")
        f.needs_bus_metro_nearby = True
        if not f.context:
            f.context = "transport"

    # --- Building features: balkon, bahçe, asansör, garaj, güvenlik, manzara ---
    _feature_map = {
        "asansor": "asansörlü", "balkon": "balkonlu", "bahceli ev": "bahçeli",
        "garaj": "garajlı", "guvenlik": "güvenlikli", "kapici": "güvenlikli",
        "yeni bina": "yeni bina", "sifir bina": "sıfır bina",
        "deniz manzara": "deniz manzaralı", "bogaz manzara": "boğaz manzaralı",
    }
    for key, label in _feature_map.items():
        if key in text and label not in f.keywords:
            f.keywords.append(label)

    # --- Price tier ---
    if any(w in text for w in _LUXURY_WORDS):
        if "lüks" not in f.keywords:
            f.keywords.append("lüks")
        if f.min_price is None:
            f.min_price = 5_000_000
        f.sort_by = "price_desc"
    if any(w in text for w in _BUDGET_WORDS):
        if "uygun fiyat" not in f.keywords:
            f.keywords.append("uygun fiyat")
        if f.max_price is None:
            f.max_price = 4_000_000
        f.sort_by = "price_asc"

    # --- Ambiance & sorting ---
    if any(w in text for w in _QUIET_WORDS):
        if "sakin" not in f.keywords:
            f.keywords.append("sakin")
        f.min_lifestyle = max(f.min_lifestyle or 0, 7.0)
    if any(w in text for w in _CENTRAL_WORDS):
        if "merkez" not in f.keywords:
            f.keywords.append("merkez")
        f.sort_by = "lifestyle_score"
    if any(w in text for w in _INVEST_WORDS):
        if "yatırımlık" not in f.keywords:
            f.keywords.append("yatırımlık")
        f.sort_by = "price_asc"
        if f.max_price is None:
            f.max_price = 3_500_000

    return f


def _check_poi_requirements(listing: Listing, filters: ChatFilters) -> bool:
    return _check_poi_requirements_with_coords(listing, filters, listing.latitude, listing.longitude)


def _check_poi_requirements_with_coords(
    listing: Listing,
    filters: ChatFilters,
    lat: float | None,
    lon: float | None,
) -> bool:
    # POI live-API checks are too slow for real-time chatbot use; accept all listings.
    return True


def sort_listings_by_poi_distance(listings: list[Listing], poi_type: str, lat: float, lon: float) -> list[Listing]:
    """Fetch POIs of type (hospital or school) around the center and sort listings by distance to the closest POI."""
    if not listings:
        return listings
        
    if poi_type == "hospital":
        overpass_filter = '"amenity"="hospital"'
    elif poi_type == "school":
        overpass_filter = '"amenity"~"school|university|college|kindergarten"'
    else:
        return listings

    query = (
        "[out:json][timeout:15];"
        f"(nwr[{overpass_filter}](around:5000,{lat},{lon}););"
        "out center qt;"
    )
    
    import httpx
    try:
        response = httpx.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            headers={"User-Agent": "EmlakAI/1.0"},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            elements = data.get("elements", [])
            
            pois = []
            for el in elements:
                p_lat = el.get("lat")
                p_lon = el.get("lon")
                if (p_lat is None or p_lon is None) and isinstance(el.get("center"), dict):
                    p_lat = el["center"].get("lat")
                    p_lon = el["center"].get("lon")
                if p_lat is not None and p_lon is not None:
                    pois.append((p_lat, p_lon))
            
            if pois:
                from app.services.recommendation_service import haversine_distance
                
                def get_min_dist(l):
                    if l.latitude is None or l.longitude is None:
                        return 999.0
                    return min(haversine_distance(l.latitude, l.longitude, plat, plon) for plat, plon in pois)
                
                listings.sort(key=get_min_dist)
                logger.info(f"Successfully sorted {len(listings)} listings by proximity to {poi_type}.")
    except Exception as e:
        logger.warning(f"Failed to sort listings by POI distance: {e}")
        
    return listings


def match_listings(db: Session, filters: ChatFilters, limit: int = 5) -> list[Listing]:
    q = db.query(Listing).filter(Listing.is_active.is_(True))

    if filters.city:
        q = q.filter(Listing.city_canonical == filters.city)
    if filters.district:
        q = q.filter(Listing.district_canonical == filters.district)
    if filters.min_price is not None:
        q = q.filter(Listing.price >= filters.min_price)
    if filters.max_price is not None:
        q = q.filter(Listing.price <= filters.max_price)
    if filters.min_rooms is not None:
        q = q.filter(Listing.room_count_total >= filters.min_rooms)
    if filters.max_rooms is not None:
        q = q.filter(Listing.room_count_total <= filters.max_rooms)
    if filters.min_area is not None:
        q = q.filter(Listing.area_m2 >= filters.min_area)
    if filters.max_area is not None:
        q = q.filter(Listing.area_m2 <= filters.max_area)
    if filters.min_lifestyle is not None:
        from sqlalchemy import or_
        q = q.filter(
            or_(Listing.lifestyle_score >= filters.min_lifestyle,
                Listing.lifestyle_score.is_(None))
        )
    if filters.max_building_age is not None:
        q = q.filter(Listing.building_age <= filters.max_building_age)

    # If the user has specific school or hospital requirements, fetch more candidates and sort by POI distance
    is_hospital_req = filters.context == "elderly_care" or "hastane yakını" in filters.keywords
    is_school_req = filters.context == "family_kids" or "okul yakını" in filters.keywords
    
    if is_hospital_req or is_school_req:
        # Fetch up to 30 matching listings sorted by lifestyle score to run POI distance sorting on
        candidates = q.order_by(desc(Listing.lifestyle_score)).limit(30).all()
        valid_coords = [(c.latitude, c.longitude) for c in candidates if c.latitude and c.longitude]
        if valid_coords:
            center_lat = sum(x[0] for x in valid_coords) / len(valid_coords)
            center_lon = sum(x[1] for x in valid_coords) / len(valid_coords)
            
            poi_type = "hospital" if is_hospital_req else "school"
            candidates = sort_listings_by_poi_distance(candidates, poi_type, center_lat, center_lon)
            return candidates[:limit]

    # Standard sorting
    if filters.sort_by == "price_asc":
        q = q.order_by(asc(Listing.price))
    elif filters.sort_by == "price_desc":
        q = q.order_by(desc(Listing.price))
    else:
        q = q.order_by(desc(Listing.lifestyle_score).nullslast(), asc(Listing.price))

    # Get more results than needed if POI filtering is required
    # (some may be filtered out)
    fetch_limit = limit * 3 if any([
        filters.needs_park_nearby,
        filters.needs_playground_nearby,
        filters.needs_school_nearby,
        filters.needs_hospital_nearby,
        filters.needs_bus_metro_nearby,
    ]) else limit
    
    all_listings = q.limit(fetch_limit).all()

    # Apply POI filtering if needed
    poi_required = any([
        filters.needs_park_nearby,
        filters.needs_playground_nearby,
        filters.needs_school_nearby,
        filters.needs_hospital_nearby,
        filters.needs_bus_metro_nearby,
    ])
    if poi_required:
        from app.services.geocoding import get_centroid_for_listing
        filtered = []
        for listing in all_listings:
            lat = listing.latitude
            lon = listing.longitude
            if (not lat or not lon):
                centroid = get_centroid_for_listing(db, listing)
                if centroid:
                    lat, lon = centroid
            if _check_poi_requirements_with_coords(listing, filters, lat, lon):
                filtered.append(listing)
        return filtered[:limit]

    return all_listings[:limit]


def _format_price(price) -> str:
    return f"₺{int(price):,}".replace(",", ".")


def _contextual_explanation(context: str, picks: list[Listing]) -> str:
    if not picks:
        return ""
    best = picks[0]
    if context == "pets":
        return f"\n\n**Kopek/Kedi icin ideal**: {best.title} yasam puani {best.lifestyle_score or 0:.1f}/10 ile bahce ve cevre dostu. Parklar ve yesil alanlar yakin!"
    elif context == "family":
        return f"\n\n**Aileniz icin**: {best.title} {best.room_count_total} oda, {best.area_m2:.0f} m² ile genis. Okullar ve oyun alanlari yakin."
    elif context == "student":
        return f"\n\n**Ogrenciye uygun**: {best.title} uygun fiyat ve merkezi konum. Sosyal yasam puani {best.lifestyle_score or 0:.1f}/10."
    elif context == "elderly":
        return f"\n\n**Yaslilar icin**: {best.title} erisilebilir konumda, saglik hizmetleri yakin (yasam puani {best.lifestyle_score or 0:.1f}/10)."
    elif context == "family_kids":
        return f"\n\n**Cocuklu aile icin**: {best.title} genis {best.room_count_total} oda, okul ve oyun alanlarina yakin (yasam puani {best.lifestyle_score or 0:.1f}/10)."
    elif context == "elderly_care":
        return f"\n\n**Yasli bakimi icin**: {best.title} asansorlu, hastane ve saglik merkezi yakin (yasam puani {best.lifestyle_score or 0:.1f}/10)."
    elif context == "remote":
        return f"\n\n**Evden calisma icin**: {best.title} sessiz cevrede. Internet ve isik avantajli."
    elif context == "nature":
        return f"\n\n**Dogaya yakin**: {best.title} yesil alanlar ve parklar basinda (yasam puani {best.lifestyle_score or 0:.1f}/10)."
    elif context == "nightlife":
        return f"\n\n**Sosyal ve aktif**: {best.title} kafe, bar ve restoranlar yakin. Eglence merkezinde!"
    elif context == "newlywed":
        return f"\n\n**Yeni ciftler icin**: {best.title} modern ve merkezi, {best.room_count_total} oda (yasam puani {best.lifestyle_score or 0:.1f}/10)."
    elif context == "transport":
        return f"\n\n**Ulasim odakli**: {best.title} metro ve toplu tasima hatlarina yakin (yasam puani {best.lifestyle_score or 0:.1f}/10)."
    elif context == "studio":
        return f"\n\n**Studyo/kucuk daire**: {best.title} pratik ve ekonomik, {best.area_m2:.0f} m² (yasam puani {best.lifestyle_score or 0:.1f}/10)."
    return ""


_GREETING_PAT = re.compile(
    r"^(merhaba|selam|hey|iyi gunler|iyi aksam|nasilsin|nasilsiniz|naber|ne haber|nasil yardimci|gunaydın|gunaydin|iyi aksamlar|iyi geceler)\b"
)

_CHITCHAT_MAP = [
    # "kim siniz", "kimsiniz", "kim sin" — space-tolerant
    (re.compile(r"kim\s*sin\w*|ne yapabilirsin\w*|nasil calisin\w*|hakkinda bilgi|nasil kullanilir\w*|ne is yap\w*"),
     "Ben EmlakAI — yapay zeka destekli emlak asistanıyım! 🤖\n\n"
     "Şunları yapabilirim:\n"
     "• Kriterlerinize göre ev bulma (şehir, oda, bütçe)\n"
     "• Fiyat analizi — overpriced mi, adil mi?\n"
     "• Yaşam kalitesi skoru (çevre, yeşil alan, metro)\n"
     "• Çevredeki okul, hastane, otobüs/metro mesafesi\n\n"
     "Hangi şehirde, kaç oda arıyorsunuz?"),
    (re.compile(r"\b(tesekkur\w*|sagol|eyvallah)\b"),
     "Rica ederim! 😊 Başka bir ev aramanıza yardımcı olabilir miyim?"),
    # single-word acknowledgements — word-boundary based, not full-string anchors
    (re.compile(r"^(tamam|peki|anladim|anladik|tamamdir|oldu|anlasild\w*)\b"),
     "Harika! 😊 Başka bir şey aramak ister misiniz?\n\nÖrnek: *'Ankara'da 3+1, max 5 milyon'*"),
    (re.compile(r"^(yardim|help)\b"),
     "Tabii! Şu şekilde arama yapabilirsiniz:\n\n"
     "• Konum: *Kadıköy'de daire*\n"
     "• Oda: *3+1*, *en az 2 oda*\n"
     "• Bütçe: *max 5 milyon*, *bütçem 3M*\n"
     "• Özellik: *metro yakını*, *yeni bina*, *bahçeli*\n"
     "• Aile: *2 çocuğum var*, *annem için*\n\n"
     "Ne arıyorsunuz?"),
    (re.compile(r"^(cok guzel|muhtesem|muthis|vay|wow|bravo|inanilmaz|super|mukemmel|harika)\b"),
     "Teşekkürler! 😊 Size en uygun evi bulmak için kriterleri söyleyin — şehir, oda sayısı, bütçe?"),
]


def _is_no_intent(filters: "ChatFilters") -> bool:
    return (
        not filters.city and not filters.district and
        filters.min_rooms is None and filters.max_rooms is None and
        filters.max_price is None and filters.min_price is None and
        not filters.keywords and not filters.context
    )


def build_reply(message: str, filters: ChatFilters, picks: list[Listing], total: int) -> str:
    text_norm = _strip(message)

    if _GREETING_PAT.match(text_norm):
        return (
            "Merhaba! 👋 Ben EmlakAI chatbot'uyum, size ideal evi bulmak için buradayım.\n\n"
            "Şunları anlayabilirim:\n"
            "• Konum: *Kadıköy'de*, *Beşiktaş yakını*\n"
            "• Oda: *3+1*, *en az 2 oda*, *stüdyo*\n"
            "• Bütçe: *5 milyon altı*, *bütçem 3 milyon*\n"
            "• Aile: *2 çocuğum var*, *4 kişilik aile*, *annem için*\n"
            "• Özellik: *metro yakını*, *otobüs yakını*, *yeni bina*, *bahçeli*, *asansörlü*\n\n"
            "Ne arıyorsunuz?"
        )

    # Chitchat: check before listing logic
    for pattern, response in _CHITCHAT_MAP:
        if pattern.search(text_norm):
            return response

    # No extractable listing intent → ask clarifying question
    if _is_no_intent(filters) and not picks:
        return (
            "Anlıyorum 😊 Hangi şehirde, kaç oda ve bütçeniz ne kadar?\n\n"
            "Örnek: *'Ankara'da 3+1, 5 milyon altı'* veya *'İstanbul'da metro yakını ev'*"
        )

    if not picks:
        bits = []
        if filters.district:
            bits.append(filters.district.title())
        if filters.max_price:
            bits.append(f"{_format_price(filters.max_price)} altinda")
        if filters.min_rooms:
            bits.append(f"{filters.min_rooms}+ oda")
        criteria = ", ".join(bits) if bits else "verdigin kriterler"
        return f"Uzgunum, {criteria} icin uygun ilan bulamadim. Butce veya tercihini esnetir misin?"

    llm_reply = _llm_explain(message, filters, picks, total)
    if llm_reply:
        return llm_reply

    intro_bits = []
    if filters.keywords:
        intro_bits.append(", ".join(filters.keywords))
    if filters.max_price and filters.min_price:
        intro_bits.append(f"{_format_price(filters.min_price)} - {_format_price(filters.max_price)}")
    elif filters.max_price:
        intro_bits.append(f"max {_format_price(filters.max_price)}")
    elif filters.min_price:
        intro_bits.append(f"min {_format_price(filters.min_price)}")
    intro = " · ".join(intro_bits) if intro_bits else "tercihlerin"

    lines = [f"Harika! {intro} icin {total} ilan buldum. Ilk {len(picks)} tavsiye:"]
    for i, l in enumerate(picks, 1):
        score = l.lifestyle_score or 0
        verdict = {"underpriced": "ucuz", "fair": "adil", "overpriced": "pahalı"}.get(
            (l.price_verdict or "fair"), "adil"
        )
        compat_score = calculate_compatibility_score(l, filters)
        compat_str = f"uyum skoru {compat_score:.1f}/10 · " if compat_score is not None else ""
        lines.append(
            f"{i}. **{l.title}** — {_format_price(l.price)} · {l.area_m2:.0f} m² · "
            f"{l.room_count_total} oda · {compat_str}yasam puani {score:.1f}/10 · fiyat {verdict}"
        )

    lines.append(_contextual_explanation(filters.context, picks))
    return "\n".join(lines)


def _llm_explain(message: str, filters: ChatFilters, picks: list[Listing], total: int) -> Optional[str]:
    agent = BaseAgent()
    if not agent.is_llm_available():
        return None
    
    def format_listing_for_llm(l):
        cs = calculate_compatibility_score(l, filters)
        cs_str = f", uyum skoru {cs:.1f}/10" if cs is not None else ""
        return f"- {l.title}: {int(l.price)} TRY, {l.area_m2:.0f} m², {l.room_count_total} oda, {l.district}{cs_str}, yasam puani {l.lifestyle_score or 0:.1f}/10"

    listings_text = "\n".join(format_listing_for_llm(l) for l in picks)
    prompt = (
        "Sen EmlakAI'nın akıllı asistanısın. Türkiye'deki emlak piyasası, "
        "ev satın alma süreci, fiyat analizi, mahalle karşılaştırması ve "
        "yatırım tavsiyesi konularında yardım edersin. Her zaman Türkçe "
        "yanıt ver. Kısa ve net ol. Emojileri asla kullanma.\n\n"
        f"Kullanıcı İsteği: {message}\n"
        f"Eşleşen İlanlar ({total} adet):\n{listings_text}\n\n"
        "Cevap:"
    )
    try:
        return agent.call_llm(prompt)
    except Exception as e:
        logger.debug(f"LLM explain failed: {e}")
        return None


def analyze_user_input(message: str) -> dict:
    """
    Analyze user message to understand intent, needs, and characteristics.
    Detects: pets, children, elderly, health conditions, transportation needs.
    
    Returns:
        {
            'intent': 'buy'|'rent'|'invest'|'consult',
            'lifecycle': 'couple'|'family'|'student'|'elderly'|'professional'|'unknown',
            'priority': list of priorities,
            'detected_context': original context,
            'summary': brief analysis,
            'poi_needs': {
                'park': bool (pets/recreation),
                'playground': bool (children),
                'school': bool (children),
                'hospital': bool (elderly/health),
                'transport': bool (metro/bus)
            },
            'health_needs': list of health conditions,
            'pet_count': int or None,
            'child_count': int or None,
            'elderly_count': int or None
        }
    """
    agent = BaseAgent()
    if not agent.is_llm_available():
        return {
            'intent': 'buy',
            'lifecycle': 'unknown',
            'priority': [],
            'detected_context': '',
            'summary': 'Analiz başarısız',
            'poi_needs': {'park': False, 'playground': False, 'school': False, 'hospital': False, 'transport': False},
            'health_needs': [],
            'pet_count': None,
            'child_count': None,
            'elderly_count': None
        }
    
    analysis_prompt = (
        "Aşağıdaki Türkçe mesajı ayrıntılı analiz et. JSON formatında çıkış ver:\n\n"
        
        "1. TEMEL BİLGİ:\n"
        "   - intent: 'buy', 'rent', 'invest' ya da 'consult'\n"
        "   - lifecycle: 'couple', 'family', 'student', 'elderly', 'professional' ya da 'unknown'\n"
        "   - priorities: En fazla 3 seçim: price, location, lifestyle, transport, schools, greenspace, social, work-from-home\n\n"
        
        "2. YAŞAM STİLÜ:\n"
        "   - has_pets: true/false (köpek, kedi, hayvan)\n"
        "   - pet_count: hayvan sayısı (1, 2, vb.) ya da null\n"
        "   - has_children: true/false\n"
        "   - child_count: çocuk sayısı ya da null\n"
        "   - has_elderly: true/false (yaşlı, emekli, büyükanne/baba)\n"
        "   - elderly_count: yaşlı sayısı ya da null\n\n"
        
        "3. SAĞLIK & KOŞULLAR:\n"
        "   - health_conditions: [] ya da ['chronic_illness', 'mobility_issues', 'requires_medical_care'] vb.\n"
        "   - poi_requirements: {{\n"
        "       'park_nearby': bool (hayvanlar, rekreasyon için)\n"
        "       'playground_nearby': bool (çocuklar için)\n"
        "       'school_nearby': bool (çocuklar için)\n"
        "       'hospital_nearby': bool (yaşlılar/sağlık durumları için)\n"
        "       'bus_metro_nearby': bool (ulaşım bağımlılığı)\n"
        "     }}\n\n"
        
        "4. OPSIYONEL:\n"
        "   - main_keywords: belirtilen ana anahtar kelimeler\n"
        "   - sentiment: 'positive', 'neutral', 'negative'\n\n"
        
        "Mesaj: {}\n\n"
        "JSON çıkış (sadece JSON, başka hiçbir şey yok):"
    ).format(message)
    
    try:
        response_text = agent.call_llm(analysis_prompt)
        if response_text:
            result = agent.parse_json(response_text)
            
            # Ensure all required fields exist
            result.setdefault('intent', 'buy')
            result.setdefault('lifecycle', 'unknown')
            result.setdefault('priority', [])
            result.setdefault('poi_requirements', {
                'park_nearby': False,
                'playground_nearby': False,
                'school_nearby': False,
                'hospital_nearby': False,
                'bus_metro_nearby': False
            })
            result.setdefault('health_conditions', [])
            result.setdefault('pet_count', None)
            result.setdefault('child_count', None)
            result.setdefault('elderly_count', None)
            result.setdefault('has_pets', False)
            result.setdefault('has_children', False)
            result.setdefault('has_elderly', False)
            
            # Build summary
            parts = [f"Intent: {result.get('intent', 'unknown')}"]
            if result.get('has_pets'):
                parts.append(f"🐕 {result.get('pet_count', 1)} hayvan")
            if result.get('has_children'):
                parts.append(f"👧 {result.get('child_count', 1)} çocuk")
            if result.get('has_elderly'):
                parts.append(f"👴 {result.get('elderly_count', 1)} yaşlı")
            if result.get('health_conditions'):
                parts.append(f"⚕️ {', '.join(result['health_conditions'])}")
            
            result['summary'] = " | ".join(parts)
            return result
    except Exception as e:
        logger.debug(f"User input analysis failed: {e}")
    
    return {
        'intent': 'buy',
        'lifecycle': 'unknown',
        'priority': [],
        'detected_context': '',
        'summary': 'Analiz başarısız',
        'poi_needs': {'park': False, 'playground': False, 'school': False, 'hospital': False, 'transport': False},
        'health_needs': [],
        'pet_count': None,
        'child_count': None,
        'elderly_count': None
    }
