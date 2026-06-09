import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import User
from app.models.listing import Listing
from app.schemas.listing import ListingCardResponse, ListingListResponse, ListingResponse, ListingSelectorResponse
from app.services.listing_service import get_listing_by_id
from app.services.recommendation_service import calculate_match_score, calculate_compatibility_score

def canonicalize_turkish(text: str) -> str:
    if not text:
        return ""
    # Replace capital Turkish letters first, then lowercase them, then replace lowercase Turkish letters
    replacements_upper = {
        'İ': 'i', 'I': 'i', 'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c'
    }
    replacements_lower = {
        'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c'
    }
    for k, v in replacements_upper.items():
        text = text.replace(k, v)
    text = text.lower()
    for k, v in replacements_lower.items():
        text = text.replace(k, v)
    # Remove combining dot above if any remained
    text = text.replace('\u0307', '')
    return text.strip()

router = APIRouter(prefix="/api", tags=["listings"])


@router.get("/listings", response_model=ListingListResponse)
def read_listings(
    page: int = 1,
    page_size: int = 10,
    city: str | None = Query(default=None),
    district: str | None = Query(default=None),
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    min_rooms: int | None = Query(default=None, ge=0),
    max_rooms: int | None = Query(default=None, ge=0),
    min_area: float | None = Query(default=None, ge=0),
    sort_by: str = Query(default="recent"),
    search: str | None = Query(default=None),
    keywords: str | None = Query(default=None),
    context: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 10

    query = db.query(Listing).filter(Listing.is_active.is_(True))

    user = None
    if user_id is not None:
        user = db.query(User).filter(User.id == user_id).first()

    # Apply user's preferred location filters if not overridden by explicit search parameters
    if not search and not district and not city and user:
        if user.district and user.district.strip():
            query = query.filter(Listing.district_canonical == canonicalize_turkish(user.district))
        elif user.province and user.province.strip():
            query = query.filter(Listing.city_canonical == canonicalize_turkish(user.province))

    if city:
        query = query.filter(Listing.city_canonical == city.lower())

    if search:
        s = search.strip()
        # Detect Turkish room-count pattern: "4+1", "3+1", "2+1", etc.
        # Only search in title to avoid false positives from descriptions.
        room_match = re.match(r'^(\d+)\+(\d+)$', s)
        if room_match:
            # Exact room-type match in title only (e.g. "4+1")
            query = query.filter(Listing.title.ilike(f"%{s}%"))
        else:
            # Location / project name search.
            # Intentionally exclude `description` so that an Ankara listing
            # mentioning "istanbul" in its description does NOT appear when
            # the user searches for Istanbul.
            term = f"%{s.lower()}%"
            query = query.filter(
                or_(
                    Listing.title.ilike(term),
                    Listing.city.ilike(term),
                    Listing.district.ilike(term),
                    Listing.neighborhood.ilike(term),
                )
            )
    if district:
        query = query.filter(Listing.district_canonical == district.lower())
    if min_price is not None:
        query = query.filter(Listing.price >= min_price)
    if max_price is not None:
        query = query.filter(Listing.price <= max_price)
    if min_rooms is not None:
        query = query.filter(Listing.room_count_total >= min_rooms)
    if max_rooms is not None:
        query = query.filter(Listing.room_count_total <= max_rooms)
    if min_area is not None:
        query = query.filter(Listing.area_m2 >= min_area)

    if user and sort_by == "personalized":
        # Load all matching listings to sort in memory
        all_listings = query.all()
        # Sort by match score descending
        all_listings.sort(key=lambda l: calculate_match_score(user, l, db), reverse=True)
        total = len(all_listings)
        listings = all_listings[(page - 1) * page_size : page * page_size]
    else:
        # Standard database sorting and pagination
        if sort_by == "price_asc":
            query = query.order_by(asc(Listing.price))
        elif sort_by == "price_desc":
            query = query.order_by(desc(Listing.price))
        elif sort_by == "lifestyle_score":
            query = query.order_by(desc(Listing.lifestyle_score).nullslast(), desc(Listing.id))
        else:
            query = query.order_by(Listing.published_at.desc().nullslast(), Listing.id.desc())

        total = query.count()
        listings = (
            query.offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

    filters = {
        "district": district,
        "min_price": min_price,
        "max_price": max_price,
        "min_rooms": min_rooms,
        "max_rooms": max_rooms,
        "min_area": min_area,
        "search": search,
        "keywords": keywords,
        "context": context,
    }

    items = [
        ListingCardResponse(
            id=listing.id,
            title=listing.title,
            price=listing.price,
            district=listing.district,
            area_m2=listing.area_m2,
            room_count_total=listing.room_count_total,
            lifestyle_score=listing.lifestyle_score,
            match_score=calculate_compatibility_score(listing, filters),
            price_verdict=listing.price_verdict,
            source=listing.source,
            latitude=listing.latitude,
            longitude=listing.longitude,
        )
        for listing in listings
    ]

    return ListingListResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/listings/search")
def search_listings(
    q: str = Query(default="", min_length=0),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    terms = [t.strip() for t in q.split() if t.strip()]
    query = db.query(Listing).filter(Listing.is_active.is_(True))
    for term in terms:
        pattern = f"%{term}%"
        query = query.filter(
            or_(
                Listing.title.ilike(pattern),
                Listing.city.ilike(pattern),
                Listing.district.ilike(pattern),
                Listing.neighborhood.ilike(pattern),
                Listing.room_layout_raw.ilike(pattern),
            )
        )
    listings = (
        query.order_by(desc(Listing.lifestyle_score).nullslast(), desc(Listing.id))
        .limit(limit)
        .all()
    )
    return [
        {
            "id": l.id,
            "title": l.title,
            "price": float(l.price) if l.price else None,
            "city": l.city,
            "district": l.district,
            "room_layout_raw": l.room_layout_raw,
            "lifestyle_score": l.lifestyle_score,
        }
        for l in listings
    ]


@router.get("/listings/selector", response_model=list[ListingSelectorResponse])
def get_listings_selector(db: Session = Depends(get_db)):
    """Get all active listings for selection dropdown."""
    listings = db.query(Listing).filter(Listing.is_active.is_(True)).order_by(Listing.title.asc()).all()
    return [{"id": l.id, "title": l.title} for l in listings]


@router.get("/listings/{listing_id}", response_model=ListingResponse)
def read_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = get_listing_by_id(db, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing
