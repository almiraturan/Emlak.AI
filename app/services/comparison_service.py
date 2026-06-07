from typing import Dict, List

from sqlalchemy.orm import Session

from app.models import Listing, User
from app.schemas.comparison import ComparisonRequest, ListingComparison
from app.services.price_analysis_service import calculate_price_analysis
from app.services.profile_service import calculate_user_profile


def calculate_location_score(listing: Listing) -> float:
    """Calculate location score based on centrality (0-10)."""
    if not listing.latitude or not listing.longitude:
        return 5.0  # neutral

    # Simple centrality: distance from city center (approximate Istanbul center)
    istanbul_center_lat, istanbul_center_lng = 41.0082, 28.9784

    # Rough distance calculation (not accurate, but for demo)
    lat_diff = abs(listing.latitude - istanbul_center_lat)
    lng_diff = abs(listing.longitude - istanbul_center_lng)
    distance = (lat_diff + lng_diff) * 111  # approx km

    # Closer to center = higher score
    if distance < 5:
        return 10.0
    elif distance < 10:
        return 8.0
    elif distance < 20:
        return 6.0
    else:
        return 4.0


def get_price_fairness_score(verdict: str) -> float:
    """Convert price verdict to score."""
    if verdict == 'fair':
        return 1.0
    elif verdict == 'underpriced':
        return 1.5
    elif verdict == 'overpriced':
        return 0.5
    else:
        return 1.0


def compare_listings(request: ComparisonRequest, db: Session) -> Dict:
    """Compare listings based on user preferences."""
    user_profile = calculate_user_profile(request.user_id, db)

    # Weights based on user preferences
    weights = {
        'lifestyle': 0.4 if user_profile['lifestyle_priority'] == 'quiet' else 0.3,
        'price': 0.3,
        'location': 0.4 if user_profile['prefers_central'] else 0.3
    }

    comparisons = []
    for listing_id in request.listing_ids:
        listing = db.query(Listing).filter(Listing.id == listing_id).first()
        if not listing:
            continue

        # Get scores
        lifestyle_score = listing.lifestyle_score or 5.0
        location_score = calculate_location_score(listing)

        # Price analysis
        if listing.price_verdict:
            price_score = get_price_fairness_score(listing.price_verdict)
        else:
            analysis = calculate_price_analysis(listing_id, db)
            price_score = get_price_fairness_score(analysis['verdict'] or 'fair')

        # Weighted total
        total_score = (
            (lifestyle_score / 10) * weights['lifestyle'] +
            price_score * weights['price'] +
            (location_score / 10) * weights['location']
        ) * 10  # 0-10 scale

        comparisons.append(ListingComparison(
            listing_id=listing_id,
            title=listing.title,
            price=float(listing.price),
            lifestyle_score=lifestyle_score,
            price_verdict=listing.price_verdict,
            location_score=location_score,
            total_score=round(total_score, 1)
        ))

    # Sort by total score descending
    comparisons.sort(key=lambda x: x.total_score, reverse=True)

    # Generate trade-offs
    trade_offs = []
    if len(comparisons) >= 2:
        best = comparisons[0]
        second = comparisons[1]

        if best.lifestyle_score > second.lifestyle_score and best.price > second.price:
            trade_offs.append(f"{best.title} daha iyi yaşam kalitesi sunuyor ama daha pahalı.")
        elif best.price < second.price and best.lifestyle_score < second.lifestyle_score:
            trade_offs.append(f"{best.title} daha uygun fiyatlı ama {second.title} daha iyi konumda.")

    return {
        'comparisons': comparisons,
        'trade_offs': trade_offs
    }