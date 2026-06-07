from typing import List, Optional

from pydantic import BaseModel


class ComparisonRequest(BaseModel):
    listing_ids: List[int]
    user_id: int


class ListingComparison(BaseModel):
    listing_id: int
    title: str
    price: float
    lifestyle_score: Optional[float]
    price_verdict: Optional[str]
    location_score: float  # 0-10, based on centrality
    total_score: float  # weighted


class ComparisonResponse(BaseModel):
    comparisons: List[ListingComparison]
    trade_offs: List[str]  # explanations like "A has better lifestyle but B is cheaper"