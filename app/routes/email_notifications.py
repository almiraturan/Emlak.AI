from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.listing import Listing
from app.services.email_service import (
    get_subscription_status,
    notify_high_lifestyle_listing,
    subscribe_email,
    unsubscribe_email,
)

router = APIRouter(prefix="/api/email", tags=["email"])


class EmailSubscribeRequest(BaseModel):
    email: EmailStr
    user_id: int = 1
    min_lifestyle_score: int = 8


class EmailStatusResponse(BaseModel):
    email: str
    subscribed: bool
    min_lifestyle_score: int


@router.post("/subscribe", response_model=EmailStatusResponse)
def subscribe(req: EmailSubscribeRequest, db: Session = Depends(get_db)):
    """Subscribe to high-lifestyle listing notifications."""
    success = subscribe_email(db, req.email, req.user_id, req.min_lifestyle_score)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to subscribe")

    status = get_subscription_status(db, req.email)
    return EmailStatusResponse(**status)


@router.delete("/unsubscribe")
def unsubscribe(email: str = Query(...), db: Session = Depends(get_db)):
    """Unsubscribe from notifications."""
    success = unsubscribe_email(db, email)
    return {"unsubscribed": success}


@router.get("/status", response_model=Optional[EmailStatusResponse])
def check_status(email: str = Query(...), db: Session = Depends(get_db)):
    """Check subscription status for an email."""
    status = get_subscription_status(db, email)
    if not status:
        return None
    return EmailStatusResponse(**status)


@router.post("/notify-listings")
def trigger_notifications(db: Session = Depends(get_db)):
    """Manually trigger notifications for recent high-lifestyle listings."""
    recent_listings = (
        db.query(Listing)
        .filter(
            Listing.is_active.is_(True),
            Listing.lifestyle_score >= 8,
        )
        .order_by(Listing.published_at.desc().nullslast())
        .limit(20)
        .all()
    )

    total_sent = 0
    notifications = {}
    for listing in recent_listings:
        sent = notify_high_lifestyle_listing(db, listing)
        if sent > 0:
            notifications[listing.id] = {
                "title": listing.title,
                "lifestyle_score": listing.lifestyle_score,
                "emails_sent": sent,
            }
            total_sent += sent

    return {
        "total_sent": total_sent,
        "listings_notified": len(notifications),
        "details": notifications,
    }
