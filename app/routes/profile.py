from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.profile import UserBehaviorCreate, UserBehaviorResponse, UserProfile
from app.services.profile_service import add_user_behavior, calculate_user_profile

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/profile/{user_id}", response_model=UserProfile)
def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    """Get user's preference profile summary."""
    try:
        profile = calculate_user_profile(user_id, db)
        return UserProfile(**profile)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/behavior", response_model=UserBehaviorResponse)
def create_behavior(behavior: UserBehaviorCreate, user_id: int, db: Session = Depends(get_db)):
    """Add a new user behavior record."""
    try:
        new_behavior = add_user_behavior(
            user_id=user_id,
            behavior_type=behavior.behavior_type,
            listing_id=behavior.listing_id,
            metadata=behavior.metadata,
            db=db
        )
        return UserBehaviorResponse(
            id=new_behavior.id,
            user_id=new_behavior.user_id,
            behavior_type=new_behavior.behavior_type,
            listing_id=new_behavior.listing_id,
            metadata=new_behavior.search_metadata,
            timestamp=new_behavior.timestamp
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))