from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app.models.listing import Listing
from app.schemas.listing import ListingQueryParams
from app.services.location_text import to_canonical_location


def get_all_listings(db: Session, params: ListingQueryParams):
    # Tum filtreler tek query uzerinde birlestirilir; boylece frontend gerekli listeyi dogrudan alir.
    query = db.query(Listing)

    if params.city:
        city_canonical = to_canonical_location(params.city)
        if city_canonical:
            if params.fuzzy_location:
                query = query.filter(
                    or_(
                        Listing.city_canonical == city_canonical,
                        func.similarity(Listing.city_canonical, city_canonical) >= params.location_similarity_threshold,
                    )
                )
            else:
                query = query.filter(Listing.city_canonical == city_canonical)
    if params.district:
        district_canonical = to_canonical_location(params.district)
        if district_canonical:
            if params.fuzzy_location:
                query = query.filter(
                    or_(
                        Listing.district_canonical == district_canonical,
                        func.similarity(Listing.district_canonical, district_canonical)
                        >= params.location_similarity_threshold,
                    )
                )
            else:
                query = query.filter(Listing.district_canonical == district_canonical)
    if params.neighborhood:
        neighborhood_canonical = to_canonical_location(params.neighborhood)
        if neighborhood_canonical:
            if params.fuzzy_location:
                query = query.filter(
                    or_(
                        Listing.neighborhood_canonical == neighborhood_canonical,
                        func.similarity(Listing.neighborhood_canonical, neighborhood_canonical)
                        >= params.location_similarity_threshold,
                    )
                )
            else:
                query = query.filter(Listing.neighborhood_canonical == neighborhood_canonical)

    if params.near_lat is not None and params.near_lng is not None and params.radius_km is not None:
        query = query.filter(
            text(
                """
                ST_DWithin(
                    ST_SetSRID(ST_MakePoint(listings.longitude, listings.latitude), 4326)::geography,
                    ST_SetSRID(ST_MakePoint(:near_lng, :near_lat), 4326)::geography,
                    :radius_m
                )
                """
            )
        ).params(near_lng=params.near_lng, near_lat=params.near_lat, radius_m=params.radius_km * 1000)
    if params.min_price is not None:
        query = query.filter(Listing.price >= params.min_price)
    if params.max_price is not None:
        query = query.filter(Listing.price <= params.max_price)
    if params.min_m2 is not None:
        query = query.filter(Listing.gross_m2 >= params.min_m2)
    if params.max_m2 is not None:
        query = query.filter(Listing.gross_m2 <= params.max_m2)
    if params.min_room_count_total is not None:
        query = query.filter(Listing.room_count_total >= params.min_room_count_total)
    if params.max_room_count_total is not None:
        query = query.filter(Listing.room_count_total <= params.max_room_count_total)
    if params.min_room_count_living is not None:
        query = query.filter(Listing.room_count_living >= params.min_room_count_living)
    if params.max_room_count_living is not None:
        query = query.filter(Listing.room_count_living <= params.max_room_count_living)
    if params.room_count_main is not None:
        query = query.filter(Listing.room_count_main == params.room_count_main)
    if params.room_count_living is not None:
        query = query.filter(Listing.room_count_living == params.room_count_living)
    if params.room_count_total is not None:
        query = query.filter(Listing.room_count_total == params.room_count_total)
    if params.room_layout_raw is not None:
        query = query.filter(Listing.room_layout_raw == params.room_layout_raw)
    if params.listing_type is not None:
        query = query.filter(Listing.listing_type == params.listing_type)
    if params.property_type is not None:
        query = query.filter(Listing.property_type == params.property_type)
    if params.is_active is not None:
        query = query.filter(Listing.is_active == params.is_active)

    sort_column = {
        "price": Listing.price,
        "published_at": Listing.published_at,
        "source_updated_at": Listing.source_updated_at,
    }[params.sort_by]

    if params.sort_order == "asc":
        query = query.order_by(sort_column.asc().nullslast(), Listing.id.asc())
    else:
        query = query.order_by(sort_column.desc().nullslast(), Listing.id.desc())

    total = query.order_by(None).count()
    offset = (params.page - 1) * params.page_size
    items = query.offset(offset).limit(params.page_size).all()

    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}


def get_listing_by_id(db: Session, listing_id: int):
    # Frontend veya detay sayfasi icin tek bir ilan kaydini getirir.
    return db.query(Listing).filter(Listing.id == listing_id).first()
