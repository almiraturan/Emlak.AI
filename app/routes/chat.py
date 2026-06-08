from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.listing import ListingCardResponse
from app.services.chatbot import build_reply, match_listings, parse_message, analyze_user_input

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    user_id: Optional[int] = 1


class UserInputAnalysis(BaseModel):
    intent: str
    lifecycle: str
    priority: list[str]
    summary: str


class ChatResponse(BaseModel):
    reply: str
    filters: dict
    listings: list[ListingCardResponse]
    total_matched: int
    user_analysis: Optional[UserInputAnalysis] = None


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    filters = parse_message(req.message)
    
    # Analyze user input for detailed requirements
    user_analysis = analyze_user_input(req.message)
    
    # Apply POI requirements from user analysis
    if user_analysis.get('poi_requirements'):
        poi_reqs = user_analysis['poi_requirements']
        filters.needs_park_nearby = poi_reqs.get('park_nearby', filters.needs_park_nearby)
        filters.needs_playground_nearby = poi_reqs.get('playground_nearby', filters.needs_playground_nearby)
        filters.needs_school_nearby = poi_reqs.get('school_nearby', filters.needs_school_nearby)
        filters.needs_hospital_nearby = poi_reqs.get('hospital_nearby', filters.needs_hospital_nearby)
        filters.needs_bus_metro_nearby = poi_reqs.get('bus_metro_nearby', filters.needs_bus_metro_nearby)
    
    picks = match_listings(db, filters, limit=5)

    # Total matched (without limit) for the reply text.
    total_query = match_listings(db, filters, limit=10_000)
    total = len(total_query)

    import logging as _log
    _log.getLogger(__name__).info(
        "chat: city=%s district=%s picks=%d total=%d",
        filters.city, filters.district, len(picks), total,
    )

    reply = build_reply(req.message, filters, picks, total)
    
    # Build user analysis response
    user_analysis_response = UserInputAnalysis(
        intent=user_analysis.get('intent', 'unknown'),
        lifecycle=user_analysis.get('lifecycle', 'unknown'),
        priority=user_analysis.get('priority', []),
        summary=user_analysis.get('summary', '')
    )

    cards = [
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
        for l in picks
    ]

    return ChatResponse(
        reply=reply,
        filters=filters.to_dict(),
        listings=cards,
        total_matched=total,
        user_analysis=user_analysis_response,
    )
