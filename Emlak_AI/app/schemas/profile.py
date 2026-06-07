from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class UserBehaviorCreate(BaseModel):
    behavior_type: str  # 'search', 'save', 'skip', 'click'
    listing_id: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class UserBehaviorResponse(BaseModel):
    id: int
    user_id: int
    behavior_type: str
    listing_id: Optional[int]
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime


class UserProfile(BaseModel):
    budget_min: float
    budget_max: float
    preferred_rooms: int
    prefers_quiet: bool
    prefers_central: bool
    lifestyle_priority: str  # 'quiet', 'central', 'balanced'