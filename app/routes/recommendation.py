from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.recommendation import FeedbackRequest, RecommendationsResponse
from app.services.recommendation_service import add_recommendation_feedback, get_recommendations

router = APIRouter(prefix="/api", tags=["recommendations"])


@router.get("/recommendations/{user_id}", response_model=RecommendationsResponse)
def get_user_recommendations(user_id: int, db: Session = Depends(get_db)):
    """Get personalized recommendations for user."""
    try:
        recommendations = get_recommendations(user_id, db)
        return RecommendationsResponse(recommendations=recommendations)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommendations/{user_id}/feedback")
def add_feedback(user_id: int, feedback: FeedbackRequest, db: Session = Depends(get_db)):
    """Add user feedback on a recommendation."""
    try:
        add_recommendation_feedback(user_id, feedback.listing_id, feedback.liked, db)
        return {"message": "Feedback recorded"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))