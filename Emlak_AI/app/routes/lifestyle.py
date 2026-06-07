from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Listing
from app.schemas.lifestyle import LifestyleScoreResponse
from app.services.lifestyle_service import POI_CATEGORIES, calculate_lifestyle_score, categorize_pois, fetch_nearby_places, update_listing_lifestyle_score

router = APIRouter(prefix="/api", tags=["lifestyle"])


@router.get("/listing/{listing_id}/lifestyle", response_model=LifestyleScoreResponse)
async def get_listing_lifestyle(listing_id: int, db: Session = Depends(get_db)):
    """Get lifestyle score for a listing."""
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    if not listing.latitude or not listing.longitude:
        raise HTTPException(status_code=400, detail="Listing has no coordinates")

    # If score already exists, return it
    if listing.lifestyle_score is not None:
        # Recalculate POI counts for response (cached score)
        places = await fetch_nearby_places(listing.latitude, listing.longitude)
        poi_counts = categorize_pois(places)
        score_breakdown = {}
        for cat, count in poi_counts.items():
            config = POI_CATEGORIES[cat]
            score_breakdown[cat] = min(count / config['max_count'], 1.0) * 10

        return LifestyleScoreResponse(
            listing_id=listing_id,
            lifestyle_score=listing.lifestyle_score,
            poi_counts=poi_counts,
            score_breakdown=score_breakdown
        )

    # Calculate score
    places = await fetch_nearby_places(listing.latitude, listing.longitude)
    poi_counts = categorize_pois(places)
    score = calculate_lifestyle_score(poi_counts)

    # Update listing
    listing.lifestyle_score = score
    db.commit()

    score_breakdown = {}
    for cat, count in poi_counts.items():
        config = POI_CATEGORIES[cat]
        score_breakdown[cat] = min(count / config['max_count'], 1.0) * 10

    return LifestyleScoreResponse(
        listing_id=listing_id,
        lifestyle_score=score,
        poi_counts=poi_counts,
        score_breakdown=score_breakdown
    )