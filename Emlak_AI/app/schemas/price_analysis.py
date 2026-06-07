from typing import Optional

from pydantic import BaseModel


class PriceAnalysisResponse(BaseModel):
    listing_id: int
    market_avg: Optional[float]
    verdict: Optional[str]  # 'overpriced', 'fair', 'underpriced'
    trend_direction: str  # 'up', 'down', 'stable'
    comparables_count: int
    note: Optional[str] = None