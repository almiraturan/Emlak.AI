from datetime import datetime
from decimal import Decimal
from math import ceil
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ListingResponse(BaseModel):
    # API'den donen ilan cevabi; frontend bu alanlari dogrudan kullanir.
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    listing_type: str
    property_type: str
    price: Decimal
    currency: str
    area_m2: float
    net_m2: float | None
    gross_m2: float | None
    room_layout_raw: str | None
    room_count_main: int | None
    room_count_living: int | None
    room_count_total: int
    city: str
    district: str
    neighborhood: str
    city_canonical: str | None
    district_canonical: str | None
    neighborhood_canonical: str | None
    location_id: int | None
    city_code: str | None
    district_code: str | None
    neighborhood_code: str | None
    location_match_confidence: float | None
    latitude: float | None
    longitude: float | None
    building_age: int | None
    floor: int | None
    heating_type: str | None
    image_count: int
    images: list[str]
    published_at: datetime | None
    source_updated_at: datetime | None
    is_active: bool


class ListingCardResponse(BaseModel):
    # Liste ekraninda kart olarak gosterilecek ilan ozeti.
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    price: Decimal
    district: str
    area_m2: float | None
    room_count_total: int | None
    lifestyle_score: float | None
    price_verdict: str | None
    source: str | None
    latitude: float | None
    longitude: float | None


class ListingQueryParams(BaseModel):
    # Liste endpointinde kullanilan filtre, siralama ve sayfalama parametrelerini toplar.
    city: str | None = None
    district: str | None = None
    neighborhood: str | None = None
    fuzzy_location: bool = True
    location_similarity_threshold: float = Field(default=0.72, ge=0.5, le=1.0)
    near_lat: float | None = Field(default=None, ge=-90, le=90)
    near_lng: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=100)
    min_price: Decimal | None = Field(default=None, ge=0)
    max_price: Decimal | None = Field(default=None, ge=0)
    min_m2: float | None = Field(default=None, ge=0)
    max_m2: float | None = Field(default=None, ge=0)
    min_room_count_total: int | None = Field(default=None, ge=0, le=70)
    max_room_count_total: int | None = Field(default=None, ge=0, le=70)
    min_room_count_living: int | None = Field(default=None, ge=0, le=20)
    max_room_count_living: int | None = Field(default=None, ge=0, le=20)
    room_count_main: int | None = Field(default=None, ge=0, le=50)
    room_count_living: int | None = Field(default=None, ge=0, le=20)
    room_count_total: int | None = Field(default=None, ge=0, le=70)
    room_layout_raw: str | None = Field(default=None, max_length=20)
    listing_type: Literal["satilik", "kiralik"] | None = None
    property_type: Literal["daire", "villa", "arsa", "isyeri", "mustakil"] | None = None
    is_active: bool | None = None
    sort_by: Literal["price", "published_at", "source_updated_at"] = "published_at"
    sort_order: Literal["asc", "desc"] = "desc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)


class ListingListResponse(BaseModel):
    # Sayfalanmis ilan cevabi; frontend listeleme ekranlarini bununla kurar.
    items: list[ListingCardResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(cls, *, items: list[ListingCardResponse], total: int, page: int, page_size: int) -> "ListingListResponse":
        total_pages = ceil(total / page_size) if total > 0 else 0
        return cls(items=items, total=total, page=page, page_size=page_size, total_pages=total_pages)
