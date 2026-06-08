"""API routes for AI agents."""
import asyncio
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.agents.orchestrator import OrchestratorAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.lifestyle_agent import LifestyleAgent
from app.agents.price_agent import PriceAgent
from app.agents.comparison_agent import ComparisonAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.schemas.comparison import ComparisonRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])

# Initialize agents
orchestrator = OrchestratorAgent()


@router.get("/train-all")
def train_all_models(db: Session = Depends(get_db)):
    """Train all ML models."""
    try:
        results = orchestrator.train_all_models(db)
        return {
            "status": "success",
            "message": "All models trained",
            "results": results,
        }
    except Exception as e:
        logger.error(f"Error training models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile/{user_id}")
def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    """Get user profile with cluster assignment."""
    try:
        profile_agent = ProfileAgent()
        profile = profile_agent.get_profile(user_id, db)
        return profile
    except Exception as e:
        logger.error(f"Error getting profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/listing/{listing_id}/lifestyle")
def get_listing_lifestyle(
    listing_id: int,
    radius_km: float = Query(default=5.0, ge=0.5, le=10.0),
    db: Session = Depends(get_db),
):
    """Get lifestyle score for a listing with configurable search radius."""
    try:
        from app.models.listing import Listing

        listing = db.query(Listing).filter(Listing.id == listing_id).first()
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")

        if not listing.latitude or not listing.longitude:
            return {
                "score": 5.0,
                "description": "No location data",
                "poi_counts": {},
                "source": "error",
            }

        lifestyle_agent = LifestyleAgent()
        result = lifestyle_agent.score_lifestyle(
            listing.latitude, listing.longitude, radius_m=int(radius_km * 1000)
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting lifestyle score: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/listing/{listing_id}/price-analysis")
def get_listing_price_analysis(listing_id: int, db: Session = Depends(get_db)):
    """Get price analysis for a listing."""
    try:
        price_agent = PriceAgent()
        result = price_agent.analyze_price(listing_id, db)
        return result
    except Exception as e:
        logger.error(f"Error analyzing price: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare")
def compare_listings(request: ComparisonRequest, db: Session = Depends(get_db)):
    """Compare multiple listings based on user profile."""
    try:
        if not request.listing_ids:
            raise HTTPException(status_code=400, detail="No listings provided")

        comparison_agent = ComparisonAgent()
        result = comparison_agent.compare_listings(request.listing_ids, request.user_id, db)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing listings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommendations/{user_id}")
def get_recommendations(user_id: int, db: Session = Depends(get_db)):
    """Get personalized recommendations for a user."""
    try:
        recommendation_agent = RecommendationAgent()
        result = recommendation_agent.get_recommendations(user_id, db)
        return result
    except Exception as e:
        logger.error(f"Error getting recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze/{user_id}/{listing_id}")
async def analyze_user_listing(
    user_id: int, listing_id: int, db: Session = Depends(get_db)
):
    """Comprehensive analysis of user and listing combination."""
    try:
        # Run orchestration and return the unified result. Orchestrator now
        # merges DB-stored lifestyle score with live POI details when present.
        result = await orchestrator.analyze_user_listing(user_id, listing_id, db)
        return result
    except Exception as e:
        logger.error(f"Error in comprehensive analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backfill-lifestyle-scores")
def backfill_lifestyle_scores(limit: int = 100, db: Session = Depends(get_db)):
    """Enqueue background tasks to backfill missing lifestyle scores."""
    try:
        from app.models.listing import Listing
        from app.services.lifestyle_service import update_lifestyle_score_task

        listings = (
            db.query(Listing)
            .filter(Listing.lifestyle_score.is_(None))
            .filter(Listing.latitude.isnot(None))
            .filter(Listing.longitude.isnot(None))
            .limit(limit)
            .all()
        )

        processed = 0
        for l in listings:
            try:
                update_lifestyle_score_task.send(l.id)
                processed += 1
            except Exception:
                logger.exception("Failed to enqueue lifestyle backfill for listing %s", l.id)

        return {"status": "success", "processed": processed}
    except Exception as e:
        logger.error(f"Error backfilling lifestyle scores: {e}")
        raise HTTPException(status_code=500, detail=str(e))

