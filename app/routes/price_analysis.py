from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import Listing
from app.schemas.price_analysis import PriceAnalysisResponse
from app.services.price_analysis_service import calculate_price_analysis, update_listing_price_analysis

router = APIRouter(prefix="/api", tags=["price-analysis"])


@router.get("/listing/{listing_id}/price-analysis", response_model=PriceAnalysisResponse)
def get_listing_price_analysis(listing_id: int, db: Session = Depends(get_db)):
    """Get price analysis for a listing."""
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    # If analysis already exists, return it
    if listing.price_market_avg is not None:
        note = None
        if not listing.price_comparables_count:
            note = 'Bu ilan için yeterli karşılaştırılabilir aktif ilan yok; piyasa ortalaması hesaplanamadı.'

        return PriceAnalysisResponse(
            listing_id=listing_id,
            market_avg=listing.price_market_avg,
            verdict=listing.price_verdict,
            trend_direction=listing.price_trend_direction or 'stable',
            comparables_count=listing.price_comparables_count or 0,
            note=note
        )

    # Calculate analysis
    try:
        analysis = calculate_price_analysis(listing_id, db)
        update_listing_price_analysis(listing_id, db)

        note = None
        if analysis['comparables_count'] == 0:
            note = 'Bu ilan için yeterli karşılaştırılabilir aktif ilan yok; piyasa ortalaması hesaplanamadı.'

        return PriceAnalysisResponse(
            listing_id=listing_id,
            market_avg=analysis['market_avg'],
            verdict=analysis['verdict'],
            trend_direction=analysis['trend_direction'],
            comparables_count=analysis['comparables_count'],
            note=note
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))