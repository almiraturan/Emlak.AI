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