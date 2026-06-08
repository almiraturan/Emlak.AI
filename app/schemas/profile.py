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


class UserCreate(BaseModel):
    name: str
    budget_min: float = 1000000.0
    budget_max: float = 10000000.0
    preferred_rooms: int = 3
    prefers_quiet: bool = False
    prefers_central: bool = True
    purpose: str = "ikamet"
    password: str = "12345"
    province: Optional[str] = None
    district: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    preferred_rooms: Optional[int] = None
    prefers_quiet: Optional[bool] = None
    prefers_central: Optional[bool] = None
    purpose: Optional[str] = None
    password: Optional[str] = None
    province: Optional[str] = None
    district: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    name: str
    budget_min: float
    budget_max: float
    preferred_rooms: int
    prefers_quiet: bool
    prefers_central: bool
    purpose: str
    password: str
    province: Optional[str] = None
    district: Optional[str] = None

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str
    password: str