from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import User, UserBehavior
from app.schemas.profile import (
    UserBehaviorCreate,
    UserBehaviorResponse,
    UserProfile,
    UserCreate,
    UserUpdate,
    UserResponse,
    LoginRequest
)
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


@router.get("/users", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db)):
    """List all users."""
    return db.query(User).order_by(User.id.asc()).all()


@router.post("/users", response_model=UserResponse)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    """Create a new user."""
    # Check if name already exists to avoid confusion (not strictly unique, but helpful)
    existing = db.query(User).filter(User.name == user_in.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu isimde bir kullanıcı zaten mevcut.")

    user = User(
        name=user_in.name,
        budget_min=user_in.budget_min,
        budget_max=user_in.budget_max,
        preferred_rooms=user_in.preferred_rooms,
        prefers_quiet=user_in.prefers_quiet,
        prefers_central=user_in.prefers_central,
        purpose=user_in.purpose,
        password=user_in.password,
        province=user_in.province,
        district=user_in.district
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/login", response_model=UserResponse)
def login_user(login_in: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user and return profile."""
    user = db.query(User).filter(User.name == login_in.username).first()
    if not user or user.password != login_in.password:
        raise HTTPException(status_code=400, detail="Kullanıcı adı veya şifre hatalı!")
    return user


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Get user by ID."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    return user


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: int, user_in: UserUpdate, db: Session = Depends(get_db)):
    """Update user preferences."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    update_data = user_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}/behavior")
def clear_user_behavior(user_id: int, db: Session = Depends(get_db)):
    """Clear user behavior log to reset AI recommendations."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    db.query(UserBehavior).filter(UserBehavior.user_id == user_id).delete()
    db.commit()
    return {"message": "Davranış geçmişi temizlendi ve AI profili sıfırlandı."}


@router.get("/users/{user_id}/behavior", response_model=list[UserBehaviorResponse])
def get_user_behaviors(user_id: int, db: Session = Depends(get_db)):
    """Get all behavior records for a specific user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    behaviors = (
        db.query(UserBehavior)
        .filter(UserBehavior.user_id == user_id)
        .order_by(UserBehavior.timestamp.desc())
        .limit(100)
        .all()
    )

    return [
        UserBehaviorResponse(
            id=b.id,
            user_id=b.user_id,
            behavior_type=b.behavior_type,
            listing_id=b.listing_id,
            metadata=b.search_metadata,
            timestamp=b.timestamp
        )
        for b in behaviors
    ]