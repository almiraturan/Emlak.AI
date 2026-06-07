from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.comparison import ComparisonRequest, ComparisonResponse
from app.services.comparison_service import compare_listings

router = APIRouter(prefix="/api", tags=["comparison"])


@router.post("/compare", response_model=ComparisonResponse)
def compare_listings_endpoint(request: ComparisonRequest, db: Session = Depends(get_db)):
    """Compare multiple listings based on user preferences."""
    result = compare_listings(request, db)
    return ComparisonResponse(**result)