from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Listing, User, UserBehavior


def calculate_user_profile(user_id: int, db: Session) -> Dict:
    """
    Calculate weighted preference profile for a user based on their behaviors.
    Returns: {
        'budget_min': float,
        'budget_max': float,
        'preferred_rooms': int,
        'prefers_quiet': bool,
        'prefers_central': bool,
        'lifestyle_priority': str  # 'quiet', 'central', 'balanced'
    }
    """
    # Get user base preferences
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")

    base_profile = {
        'budget_min': user.budget_min,
        'budget_max': user.budget_max,
        'preferred_rooms': user.preferred_rooms,
        'prefers_quiet': user.prefers_quiet,
        'prefers_central': user.prefers_central,
        'lifestyle_priority': 'balanced'
    }

    # Get behaviors in last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    behaviors = db.query(UserBehavior).filter(
        and_(UserBehavior.user_id == user_id, UserBehavior.timestamp >= thirty_days_ago)
    ).all()

    if not behaviors:
        return base_profile

    # Analyze behaviors
    search_filters = []
    saved_listings = []
    skipped_listings = []
    clicked_listings = []

    for behavior in behaviors:
        if behavior.behavior_type == 'search' and behavior.search_metadata:
            search_filters.append(behavior.search_metadata)
        elif behavior.behavior_type == 'save' and behavior.listing_id:
            saved_listings.append(behavior.listing_id)
        elif behavior.behavior_type == 'skip' and behavior.listing_id:
            skipped_listings.append(behavior.listing_id)
        elif behavior.behavior_type == 'click' and behavior.listing_id:
            clicked_listings.append(behavior.listing_id)

    # Calculate weighted preferences
    profile = base_profile.copy()

    # Budget from search filters and saved listings
    if search_filters:
        budgets = [f.get('budget_max', 0) for f in search_filters if f.get('budget_max')]
        if budgets:
            profile['budget_max'] = sum(budgets) / len(budgets)

    if saved_listings:
        avg_price = db.query(func.avg(Listing.price)).filter(Listing.id.in_(saved_listings)).scalar()
        if avg_price:
            profile['budget_max'] = float(avg_price) * 1.1  # Slightly higher

    # Room count from saved/clicked
    positive_listings = saved_listings + clicked_listings
    if positive_listings:
        avg_rooms = db.query(func.avg(Listing.room_count_total)).filter(Listing.id.in_(positive_listings)).scalar()
        if avg_rooms:
            profile['preferred_rooms'] = int(round(avg_rooms))

    # Lifestyle priority
    quiet_count = sum(1 for lid in positive_listings if db.query(Listing).filter(and_(Listing.id == lid, Listing.neighborhood.ilike('%sessiz%'))).first())
    central_count = sum(1 for lid in positive_listings if db.query(Listing).filter(and_(Listing.id == lid, Listing.neighborhood.ilike('%merkez%'))).first())

    if quiet_count > central_count * 1.5:
        profile['lifestyle_priority'] = 'quiet'
        profile['prefers_quiet'] = True
    elif central_count > quiet_count * 1.5:
        profile['lifestyle_priority'] = 'central'
        profile['prefers_central'] = True

    return profile


def add_user_behavior(user_id: int, behavior_type: str, listing_id: int | None = None, metadata: dict | None = None, db: Session = None):
    """Add a new user behavior record."""
    if db is None:
        db = next(get_db())

    behavior = UserBehavior(
        user_id=user_id,
        behavior_type=behavior_type,
        listing_id=listing_id,
        search_metadata=metadata,
    )
    db.add(behavior)
    db.commit()
    db.refresh(behavior)
    return behavior