from typing import List

from pydantic import BaseModel


class Recommendation(BaseModel):
    listing_id: int
    title: str
    price: float
    match_score: float
    explanation: str
    lifestyle_score: float | None
    price_verdict: str | None


class RecommendationsResponse(BaseModel):
    recommendations: List[Recommendation]


class FeedbackRequest(BaseModel):
    listing_id: int
    liked: bool