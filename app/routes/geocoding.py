import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.listing import Listing
from app.services.geocoding import backfill_coordinates

router = APIRouter(prefix="/api/geocode", tags=["geocoding"])


@router.post("/backfill")
async def geocode_backfill(db: Session = Depends(get_db)):
    """
    Geocode all active listings that have NULL latitude/longitude.

    Calls Nominatim (OpenStreetMap) once per unique (city, district,
    neighborhood) combination and writes the result back to both the
    listings and locations tables.  Rate-limited to 1 req/s per Nominatim ToS.
    """
    result = await backfill_coordinates(db)
    return result


@router.get("/status")
def geocode_status(db: Session = Depends(get_db)):
    """Return how many active listings still have NULL coordinates."""
    total = db.query(Listing).filter(Listing.is_active.is_(True)).count()
    missing = (
        db.query(Listing)
        .filter(
            Listing.is_active.is_(True),
            (Listing.latitude.is_(None) | Listing.longitude.is_(None)),
        )
        .count()
    )
    return {
        "total_active": total,
        "missing_coordinates": missing,
        "has_coordinates": total - missing,
        "coverage_pct": round((total - missing) / total * 100, 1) if total else 0,
    }
