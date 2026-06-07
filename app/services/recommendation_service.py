from typing import Dict, List

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import Listing, User, UserRecommendationFeedback
from app.services.price_analysis_service import calculate_price_analysis


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
    if user.prefers_central and listing.neighborhood.lower().find('merkez') != -1:
        score += 20
    elif user.prefers_quiet and listing.neighborhood.lower().find('sessiz') != -1:
        score += 20
    else:
        score += 10

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