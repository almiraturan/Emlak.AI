from typing import Dict, List
from math import radians, cos, sin, asin, sqrt

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import Listing, User, UserRecommendationFeedback
from app.services.price_analysis_service import calculate_price_analysis


def haversine_distance(lat1, lon1, lat2, lon2):
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 999.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in kilometers
    return c * r


def get_city_center(city_name: str) -> tuple[float, float]:
    city = (city_name or "").lower()
    if "ankara" in city:
        return 39.9208, 32.8541  # Kızılay
    elif "izmir" in city:
        return 38.4189, 27.1287  # Konak
    else:
        return 41.0369, 28.9775  # Taksim / İstanbul


def calculate_noise_score(listing: Listing) -> float:
    # Base noise score
    noise = 5.0
    # High lifestyle score implies more POIs (shops, transit, schools) = noisier
    if listing.lifestyle_score:
        noise += (listing.lifestyle_score - 5.0) * 0.7
    
    # Keyword adjustments
    neighborhood = (listing.neighborhood or "").lower()
    title = (listing.title or "").lower()
    description = (listing.description or "").lower()
    
    # Commercial or busy words increase noise
    if any(w in neighborhood or w in title for w in ["merkez", "levent", "mecidiyekoy", "nisantasi", "istasyon", "metro"]):
        noise += 2.0
    # Quiet or residential words decrease noise
    if any(w in neighborhood or w in title or w in description for w in ["sakin", "sessiz", "sahil", "park", "moda", "tarabya", "cengelkoy", "kuzguncuk"]):
        noise -= 2.0
        
    return max(1.0, min(10.0, noise))


def calculate_match_score(user: User, listing: Listing, db: Session) -> float:
    """Calculate match score between user and listing (0-100)."""
    score = 0.0
    listing_price = float(listing.price)
    budget_max = float(user.budget_max) if user.budget_max is not None else float(listing_price)

    # Budget match (30 points)
    if listing_price <= budget_max:
        budget_ratio = listing_price / budget_max
        score += (1 - budget_ratio) * 30  # Cheaper = higher score
    else:
        score += 10  # Some points if within 10% over

    # Room count match (20 points)
    if listing.room_count_total == user.preferred_rooms:
        score += 20
    elif abs(listing.room_count_total - user.preferred_rooms) == 1:
        score += 15
    else:
        score += 5

    # Location preference (20 points)
    loc_points = 10.0
    if user.prefers_quiet and user.prefers_central:
        # Evaluate both, each contributing up to 10 points
        noise_score = calculate_noise_score(listing)
        quiet_part = ((10.0 - noise_score) * 2.2) * 0.5
        
        center_lat, center_lon = get_city_center(listing.city)
        dist = haversine_distance(listing.latitude, listing.longitude, center_lat, center_lon)
        central_part = max(0.0, 20.0 - dist * 1.0) * 0.5
        
        loc_points = quiet_part + central_part
    elif user.prefers_quiet:
        noise_score = calculate_noise_score(listing)
        # Scale 1.0 (quietest) to 10.0 (noisiest)
        loc_points = (10.0 - noise_score) * 2.2
    elif user.prefers_central:
        center_lat, center_lon = get_city_center(listing.city)
        dist = haversine_distance(listing.latitude, listing.longitude, center_lat, center_lon)
        # Under 20km gets scaled
        loc_points = max(0.0, 20.0 - dist * 1.0)
    
    score += min(20.0, max(0.0, loc_points))

    # Lifestyle score (15 points)
    if listing.lifestyle_score:
        score += (listing.lifestyle_score / 10) * 15

    # Price fairness (15 points)
    if listing.price_verdict == 'fair':
        score += 15
    elif listing.price_verdict == 'underpriced':
        score += 12
    elif listing.price_verdict == 'overpriced':
        score += 5
    else:
        # Calculate if not cached
        try:
            analysis = calculate_price_analysis(listing.id, db)
            if analysis['verdict'] == 'fair':
                score += 15
            elif analysis['verdict'] == 'underpriced':
                score += 12
            else:
                score += 5
        except:
            score += 10

    return min(100.0, score)


def generate_recommendation_explanation(user: User, listing: Listing, db: Session) -> str:
    """Generate plain-language explanation for recommendation."""
    reasons = []

    listing_price = float(listing.price)
    if listing_price <= user.budget_max:
        reasons.append("bütçe içinde")
    else:
        reasons.append("bütçe sınırında")

    if listing.room_count_total == user.preferred_rooms:
        reasons.append(f"{user.preferred_rooms} odalı")

    if user.prefers_central and 'merkez' in listing.neighborhood.lower():
        reasons.append("merkeze yakın")
    elif user.prefers_quiet and 'sessiz' in listing.neighborhood.lower():
        reasons.append("sessiz bir mahallede")

    if listing.lifestyle_score and listing.lifestyle_score > 7:
        reasons.append("yaşam kalitesi yüksek")

    if listing.price_verdict == 'underpriced':
        reasons.append("piyasa fiyatından uygun")

    reason_text = ", ".join(reasons)
    return f"Bu daire %{int(calculate_match_score(user, listing, db))} uyumlu çünkü {reason_text}."


def get_recommendations(user_id: int, db: Session, limit: int = 10) -> List[Dict]:
    """Get top recommendations for user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return []

    # Get all active listings
    listings = db.query(Listing).filter(Listing.is_active == True).all()

    # Calculate scores
    recommendations = []
    for listing in listings:
        score = calculate_match_score(user, listing, db)
        explanation = generate_recommendation_explanation(user, listing, db)

        recommendations.append({
            'listing_id': listing.id,
            'title': listing.title,
            'price': float(listing.price),
            'match_score': round(score, 1),
            'explanation': explanation,
            'lifestyle_score': listing.lifestyle_score,
            'price_verdict': listing.price_verdict
        })

    # Sort by score descending
    recommendations.sort(key=lambda x: x['match_score'], reverse=True)

    return recommendations[:limit]


def add_recommendation_feedback(user_id: int, listing_id: int, liked: bool, db: Session):
    """Add user feedback on recommendation."""
    feedback = UserRecommendationFeedback(
        user_id=user_id,
        listing_id=listing_id,
        liked=liked
    )
    db.add(feedback)
    db.commit()


def calculate_compatibility_score(listing: Listing, filters_obj) -> float | None:
    # Normalize input to a dict
    if hasattr(filters_obj, "to_dict") and callable(filters_obj.to_dict):
        filters = filters_obj.to_dict()
    elif hasattr(filters_obj, "__dict__"):
        filters = filters_obj.__dict__
    elif isinstance(filters_obj, dict):
        filters = filters_obj
    else:
        return None

    # Check if there are any active filters.
    # We ignore page, page_size, sort_by, user_id, city since they are not search filters.
    active_keys = []
    for k, v in filters.items():
        if k in ["page", "page_size", "sort_by", "user_id", "city"]:
            continue
        if v not in (None, [], ""):
            active_keys.append(k)

    if not active_keys:
        return None

    total_weight = 0.0
    matched_weight = 0.0

    # 1. Price Match (weight = 30)
    min_price = filters.get("min_price")
    max_price = filters.get("max_price")
    if min_price is not None or max_price is not None:
        total_weight += 30.0
        price = float(listing.price)
        if min_price is not None and max_price is not None:
            min_p = float(min_price)
            max_p = float(max_price)
            if min_p <= price <= max_p:
                matched_weight += 30.0
            elif price > max_p:
                decay_limit = max_p * 0.2
                diff = price - max_p
                ratio = max(0.0, 1.0 - (diff / decay_limit)) if decay_limit > 0 else 0.0
                matched_weight += ratio * 30.0
            else:  # price < min_p
                decay_limit = min_p * 0.2
                diff = min_p - price
                ratio = max(0.0, 1.0 - (diff / decay_limit)) if decay_limit > 0 else 0.0
                matched_weight += ratio * 30.0
        elif max_price is not None:
            max_p = float(max_price)
            if price <= max_p:
                matched_weight += 30.0
            else:
                decay_limit = max_p * 0.2
                diff = price - max_p
                ratio = max(0.0, 1.0 - (diff / decay_limit)) if decay_limit > 0 else 0.0
                matched_weight += ratio * 30.0
        elif min_price is not None:
            min_p = float(min_price)
            if price >= min_p:
                matched_weight += 30.0
            else:
                decay_limit = min_p * 0.2
                diff = min_p - price
                ratio = max(0.0, 1.0 - (diff / decay_limit)) if decay_limit > 0 else 0.0
                matched_weight += ratio * 30.0

    # 2. Rooms Match (weight = 25)
    ideal_rooms = filters.get("ideal_rooms")
    min_rooms = filters.get("min_rooms")
    max_rooms = filters.get("max_rooms")
    if ideal_rooms is not None or min_rooms is not None or max_rooms is not None:
        total_weight += 25.0
        rooms = listing.room_count_total or 0
        if ideal_rooms is not None:
            diff = abs(rooms - ideal_rooms)
            if diff == 0:
                matched_weight += 25.0
            elif diff == 1:
                matched_weight += 17.0
            elif diff == 2:
                matched_weight += 8.0
            else:
                matched_weight += 2.0
        elif min_rooms is not None and max_rooms is not None:
            if min_rooms <= rooms <= max_rooms:
                matched_weight += 25.0
            else:
                diff = min(abs(rooms - min_rooms), abs(rooms - max_rooms))
                if diff == 1:
                    matched_weight += 15.0
                else:
                    matched_weight += 5.0
        elif min_rooms is not None:
            if rooms >= min_rooms:
                matched_weight += 25.0
            elif min_rooms - rooms == 1:
                matched_weight += 15.0
            else:
                matched_weight += 5.0
        elif max_rooms is not None:
            if rooms <= max_rooms:
                matched_weight += 25.0
            elif rooms - max_rooms == 1:
                matched_weight += 15.0
            else:
                matched_weight += 5.0

    # 3. District Match (weight = 20)
    district = filters.get("district")
    if district:
        total_weight += 20.0
        def canonical(text):
            if not text:
                return ""
            repl = {
                'İ': 'i', 'I': 'i', 'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c',
                'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c'
            }
            t = text.lower()
            for k, v in repl.items():
                t = t.replace(k, v)
            return t.strip()
        
        if canonical(listing.district) == canonical(district):
            matched_weight += 20.0

    # 4. Area Match (weight = 15)
    min_area = filters.get("min_area")
    max_area = filters.get("max_area")
    if min_area is not None or max_area is not None:
        total_weight += 15.0
        area = listing.area_m2
        if area is not None:
            if min_area is not None and max_area is not None:
                if min_area <= area <= max_area:
                    matched_weight += 15.0
                elif area > max_area:
                    decay = max_area * 0.2
                    ratio = max(0.0, 1.0 - (area - max_area) / decay) if decay > 0 else 0.0
                    matched_weight += ratio * 15.0
                else:  # area < min_area
                    decay = min_area * 0.2
                    ratio = max(0.0, 1.0 - (min_area - area) / decay) if decay > 0 else 0.0
                    matched_weight += ratio * 15.0
            elif min_area is not None:
                if area >= min_area:
                    matched_weight += 15.0
                else:
                    decay = min_area * 0.2
                    ratio = max(0.0, 1.0 - (min_area - area) / decay) if decay > 0 else 0.0
                    matched_weight += ratio * 15.0
            elif max_area is not None:
                if area <= max_area:
                    matched_weight += 15.0
                else:
                    decay = max_area * 0.2
                    ratio = max(0.0, 1.0 - (area - max_area) / decay) if decay > 0 else 0.0
                    matched_weight += ratio * 15.0

    # 5. Search Text Match (weight = 20)
    search_term = filters.get("search")
    if search_term:
        total_weight += 20.0
        s = search_term.strip().lower()
        title = (listing.title or "").lower()
        desc = (listing.description or "").lower()
        dist = (listing.district or "").lower()
        neigh = (listing.neighborhood or "").lower()
        if s in title or s in dist or s in neigh:
            matched_weight += 20.0
        elif s in desc:
            matched_weight += 10.0

    # 6. Keywords Match (weight = 10 * count, max 30)
    keywords = filters.get("keywords")
    if keywords:
        if isinstance(keywords, str):
            kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
        elif isinstance(keywords, list):
            kw_list = keywords
        else:
            kw_list = []

        if kw_list:
            kw_weight = min(30.0, 10.0 * len(kw_list))
            total_weight += kw_weight
            
            matched_kw_count = 0
            title_lower = (listing.title or "").lower()
            desc_lower = (listing.description or "").lower()
            
            for kw in kw_list:
                kw_clean = kw.lower()
                if kw_clean in ["toplu tasima yakini", "metro", "ulasim", "toplu taşıma yakını"]:
                    if any(w in desc_lower or w in title_lower for w in ["metro", "metrobus", "otobus", "tramvay", "ulasim", "durak", "istasyon"]):
                        matched_kw_count += 1
                elif kw_clean in ["sakin", "sessiz", "huzurlu"]:
                    if any(w in desc_lower or w in title_lower for w in ["sakin", "sessiz", "huzurlu", "tenha"]):
                        matched_kw_count += 1
                elif kw_clean in ["merkez", "merkezi"]:
                    if any(w in desc_lower or w in title_lower or w in (listing.neighborhood or "").lower() for w in ["merkez", "merkezi"]):
                        matched_kw_count += 1
                elif kw_clean in ["luks", "premium", "villa", "rezidans", "lüks"]:
                    if any(w in desc_lower or w in title_lower for w in ["luks", "lüks", "premium", "villa", "rezidans"]):
                        matched_kw_count += 1
                elif kw_clean in ["uygun fiyat", "ucuz"]:
                    if listing.price_verdict == "underpriced" or any(w in desc_lower for w in ["ucuz", "uygun fiyat", "firsat", "fırsat"]):
                        matched_kw_count += 1
                elif kw_clean in ["asansorlu", "asansor", "asansörlü", "asansör"]:
                    if "asansor" in desc_lower or "asansör" in desc_lower or "asansor" in title_lower or "asansör" in title_lower:
                        matched_kw_count += 1
                elif kw_clean in ["balkonlu", "balkon"]:
                    if "balkon" in desc_lower or "balkon" in title_lower:
                        matched_kw_count += 1
                elif kw_clean in ["bahceli", "bahce", "bahçeli", "bahçe"]:
                    if "bahce" in desc_lower or "bahçe" in desc_lower or "bahce" in title_lower or "bahçe" in title_lower:
                        matched_kw_count += 1
                elif kw_clean in ["garajli", "garaj", "otopark", "garajlı"]:
                    if any(w in desc_lower or w in title_lower for w in ["garaj", "otopark"]):
                        matched_kw_count += 1
                elif kw_clean in ["guvenlikli", "guvenlik", "güvenlikli", "güvenlik"]:
                    if any(w in desc_lower or w in title_lower for w in ["guvenlik", "güvenlik", "kapici", "kapıcı"]):
                        matched_kw_count += 1
                elif kw_clean in ["yeni bina", "sifir bina", "sıfır bina"]:
                    if (listing.building_age is not None and listing.building_age <= 5) or any(w in desc_lower or w in title_lower for w in ["sifir", "sıfır", "yeni bina"]):
                        matched_kw_count += 1
                elif kw_clean in ["okul yakini", "okul yakını"]:
                    if "okul" in desc_lower or "okul" in title_lower:
                        matched_kw_count += 1
                elif kw_clean in ["hastane yakini", "hastane yakını"]:
                    if "hastane" in desc_lower or "hastane" in title_lower or "klinik" in desc_lower:
                        matched_kw_count += 1
                else:
                    if kw_clean in title_lower or kw_clean in desc_lower:
                        matched_kw_count += 1
            
            if len(kw_list) > 0:
                matched_ratio = min(1.0, matched_kw_count / len(kw_list))
                matched_weight += matched_ratio * kw_weight

    # 7. Building Age (weight = 10)
    max_building_age = filters.get("max_building_age")
    if max_building_age is not None:
        total_weight += 10.0
        age = listing.building_age
        if age is not None:
            if age <= max_building_age:
                matched_weight += 10.0
            else:
                diff = age - max_building_age
                ratio = max(0.0, 1.0 - (diff / 10.0))
                matched_weight += ratio * 10.0

    # 8. Context match (weight = 15)
    context = filters.get("context")
    if context:
        total_weight += 15.0
        matched_context = False
        desc_lower = (listing.description or "").lower()
        title_lower = (listing.title or "").lower()
        if context == "pets":
            if any(w in desc_lower or w in title_lower for w in ["evcil", "hayvan", "kopek", "kedi", "bahce", "park"]):
                matched_context = True
        elif context in ["family", "family_kids"]:
            if (listing.room_count_total and listing.room_count_total >= 3) or any(w in desc_lower for w in ["aile", "cocuk", "çocuk", "okul"]):
                matched_context = True
        elif context == "student":
            if (listing.price_verdict == "underpriced") or any(w in desc_lower for w in ["ogrenci", "öğrenci", "universite", "üniversite", "uygun"]):
                matched_context = True
        elif context in ["elderly", "elderly_care"]:
            if any(w in desc_lower or w in title_lower for w in ["asansor", "asansör", "hastane", "dalk", "saglik", "sağlık", "yasli", "yaşlı"]):
                matched_context = True
        elif context == "remote":
            if any(w in desc_lower for w in ["home office", "calisma", "çalışma", "sessiz", "internet"]):
                matched_context = True
        elif context == "nature":
            if any(w in desc_lower or w in title_lower for w in ["doga", "doğa", "yesil", "yeşil", "orman", "park"]):
                matched_context = True
        elif context == "nightlife":
            if any(w in desc_lower or w in title_lower for w in ["kafe", "bar", "eglence", "eğlence", "merkez"]):
                matched_context = True
        elif context == "newlywed":
            if any(w in desc_lower or w in title_lower for w in ["yeni evli", "cift", "çift", "modern", "luks", "lüks"]):
                matched_context = True
        
        if matched_context:
            matched_weight += 15.0

    if total_weight == 0:
        return None

    score = (matched_weight / total_weight) * 10.0
    return round(score, 1)