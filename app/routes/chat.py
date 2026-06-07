from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.listing import ListingCardResponse
from app.services.chatbot import build_reply, match_listings, parse_message

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    user_id: Optional[int] = 1


class ChatResponse(BaseModel):
    reply: str
    filters: dict
    listings: list[ListingCardResponse]
    total_matched: int


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    filters = parse_message(req.message)
    picks = match_listings(db, filters, limit=5)

    # Total matched (without limit) for the reply text.
    total_query = match_listings(db, filters, limit=10_000)
    total = len(total_query)

    reply = build_reply(req.message, filters, picks, total)

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
    )
