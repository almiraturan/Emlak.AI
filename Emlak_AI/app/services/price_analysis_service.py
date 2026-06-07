from datetime import datetime, timedelta
from typing import Dict, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import Listing


def calculate_price_analysis(listing_id: int, db: Session) -> Dict:
    """
    Calculate price analysis for a listing.
    Returns: {
        'market_avg': float,
        'verdict': str,  # 'overpriced', 'fair', 'underpriced'
        'trend_direction': str,  # 'up', 'down', 'stable'
        'comparables_count': int
    }
    """
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise ValueError("Listing not found")

    # Find comparable listings: same district, area within 20%, active
    area_min = listing.area_m2 * 0.8
    area_max = listing.area_m2 * 1.2

    comparables = db.query(Listing).filter(
        and_(
            Listing.district == listing.district,
            Listing.area_m2.between(area_min, area_max),
            Listing.is_active == True,
            Listing.id != listing_id
        )
    ).all()

    if not comparables:
        return {
            'market_avg': None,
            'verdict': None,
            'trend_direction': 'stable',
            'comparables_count': 0
        }

    # Calculate median price
    prices = sorted([l.price for l in comparables])
    n = len(prices)
    if n % 2 == 0:
        market_avg = (prices[n//2 - 1] + prices[n//2]) / 2
    else:
        market_avg = prices[n//2]

    market_avg = float(market_avg)

    # Determine verdict
    price_ratio = float(listing.price) / market_avg
    if price_ratio > 1.1:
        verdict = 'overpriced'
    elif price_ratio < 0.9:
        verdict = 'underpriced'
    else:
        verdict = 'fair'

    # Simple trend: compare with listings from 6 months ago
    six_months_ago = datetime.utcnow() - timedelta(days=180)
    old_comparables = db.query(Listing).filter(
        and_(
            Listing.district == listing.district,
            Listing.area_m2.between(area_min, area_max),
            Listing.is_active == True,
            Listing.published_at <= six_months_ago,
            Listing.id != listing_id
        )
    ).all()

    if old_comparables:
        old_prices = [float(l.price) for l in old_comparables]
        old_avg = sum(old_prices) / len(old_prices)
        if market_avg > old_avg * 1.05:
            trend = 'up'
        elif market_avg < old_avg * 0.95:
            trend = 'down'
        else:
            trend = 'stable'
    else:
        trend = 'stable'

    return {
        'market_avg': market_avg,
        'verdict': verdict,
        'trend_direction': trend,
        'comparables_count': len(comparables)
    }


def update_listing_price_analysis(listing_id: int, db: Session):
    """Update price analysis fields for a listing."""
    analysis = calculate_price_analysis(listing_id, db)

    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if listing:
        listing.price_market_avg = analysis['market_avg']
        listing.price_verdict = analysis['verdict']
        listing.price_trend_direction = analysis['trend_direction']
        listing.price_comparables_count = analysis['comparables_count']
        db.commit()