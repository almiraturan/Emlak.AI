import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.listing import Listing
from app.services.email_service import notify_high_lifestyle_listing
from app.services.ingestion import ingest_provider_listings

broker = RedisBroker(url=settings.redis_url)
dramatiq.set_broker(broker)


@dramatiq.actor
def ping_background_job(payload: str) -> str:
    return f"processed:{payload}"


@dramatiq.actor
def ingest_demo_source_job(provider_name: str | None = None) -> None:
    db = SessionLocal()
    try:
        ingest_provider_listings(db, provider_name=provider_name)
    finally:
        db.close()


@dramatiq.actor
def notify_high_lifestyle_job(listing_id: int) -> int:
    """Background task to send email notifications for high-lifestyle listings."""
    db = SessionLocal()
    try:
        listing = db.query(Listing).filter(Listing.id == listing_id).first()
        if listing and listing.lifestyle_score and listing.lifestyle_score >= 8:
            return notify_high_lifestyle_listing(db, listing)
        return 0
    finally:
        db.close()

