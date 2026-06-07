from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.listing import Listing
from app.models.user_behavior import UserBehavior
from app.schemas.listing import ListingCardResponse

router = APIRouter(prefix="/api/saved", tags=["saved"])


class SaveRequest(BaseModel):
    listing_id: int
    user_id: int = 1


class SaveStatusResponse(BaseModel):
    saved: bool
    listing_id: int


def _is_saved(db: Session, user_id: int, listing_id: int) -> bool:
    return (
        db.query(UserBehavior.id)
        .filter(
            UserBehavior.user_id == user_id,
            UserBehavior.listing_id == listing_id,
            UserBehavior.behavior_type == "save",
        )
        .first()
        is not None
    )


@router.get("", response_model=list[ListingCardResponse])
def list_saved(user_id: int = Query(default=1), db: Session = Depends(get_db)):
    # Most recent save per listing.
    latest = (
        db.query(
            UserBehavior.listing_id.label("listing_id"),
            func.max(UserBehavior.timestamp).label("saved_at"),
        )
        .filter(
            UserBehavior.user_id == user_id,
            UserBehavior.behavior_type == "save",
            UserBehavior.listing_id.isnot(None),
        )
        .group_by(UserBehavior.listing_id)
        .subquery()
    )

    rows = (
        db.query(Listing)
        .join(latest, Listing.id == latest.c.listing_id)
        .filter(Listing.is_active.is_(True))
        .order_by(desc(latest.c.saved_at))
        .all()
    )

    return [
        ListingCardResponse(
            id=l.id,
            title=l.title,
            price=l.price,
            district=l.district,
            area_m2=l.area_m2,
            room_count_total=l.room_count_total,
            lifestyle_score=l.lifestyle_score,
            price_verdict=l.price_verdict,
            source=l.source,
            latitude=l.latitude,
            longitude=l.longitude,
        )
        for l in rows
    ]


@router.get("/status/{listing_id}", response_model=SaveStatusResponse)
def saved_status(listing_id: int, user_id: int = Query(default=1), db: Session = Depends(get_db)):
    return SaveStatusResponse(saved=_is_saved(db, user_id, listing_id), listing_id=listing_id)


@router.post("", response_model=SaveStatusResponse)
def save_listing(req: SaveRequest, db: Session = Depends(get_db)):
    listing = db.query(Listing.id).filter(Listing.id == req.listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    if _is_saved(db, req.user_id, req.listing_id):
        return SaveStatusResponse(saved=True, listing_id=req.listing_id)

    record = UserBehavior(
        user_id=req.user_id,
        behavior_type="save",
        listing_id=req.listing_id,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    return SaveStatusResponse(saved=True, listing_id=req.listing_id)


@router.delete("/{listing_id}", response_model=SaveStatusResponse)
def unsave_listing(
    listing_id: int,
    user_id: int = Query(default=1),
    db: Session = Depends(get_db),
):
    deleted = (
        db.query(UserBehavior)
        .filter(
            UserBehavior.user_id == user_id,
            UserBehavior.listing_id == listing_id,
            UserBehavior.behavior_type == "save",
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return SaveStatusResponse(saved=False, listing_id=listing_id)
