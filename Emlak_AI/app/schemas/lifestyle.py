from typing import Dict

from pydantic import BaseModel


class LifestyleScoreResponse(BaseModel):
    listing_id: int
    lifestyle_score: float
    poi_counts: Dict[str, int]  # transport, education, green, shopping, security
    score_breakdown: Dict[str, float]  # category scores