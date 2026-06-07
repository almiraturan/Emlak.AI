from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.models.location import Location
from app.models.location_alias import LocationAlias
from app.services.location_text import to_canonical_location


@dataclass
class ResolvedLocation:
    location_id: int | None
    city_canonical: str | None
    district_canonical: str | None
    neighborhood_canonical: str | None
    city_code: str | None
    district_code: str | None
    neighborhood_code: str | None
    location_match_confidence: float | None


def _exact_location_match(
    db: Session,
    city_canonical: str,
    district_canonical: str,
    neighborhood_canonical: str,
) -> Location | None:
    return (
        db.query(Location)
        .filter(
            Location.city_canonical == city_canonical,
            Location.district_canonical == district_canonical,
            Location.neighborhood_canonical == neighborhood_canonical,
        )
        .first()
    )


def _alias_location_match(
    db: Session,
    city_canonical: str,
    district_canonical: str,
    neighborhood_canonical: str,
) -> Location | None:
    alias = (
        db.query(LocationAlias)
        .filter(
            LocationAlias.city_canonical == city_canonical,
            LocationAlias.district_canonical == district_canonical,
            LocationAlias.neighborhood_canonical == neighborhood_canonical,
        )
        .first()
    )
    if alias is None:
        return None

    return db.query(Location).filter(Location.id == alias.location_id).first()


def _fuzzy_location_match(
    db: Session,
    city_canonical: str,
    district_canonical: str,
    neighborhood_canonical: str,
    threshold: float,
) -> tuple[Location | None, float]:
    candidates = (
        db.query(Location)
        .filter(
            Location.city_canonical == city_canonical,
            Location.district_canonical == district_canonical,
        )
        .all()
    )
    if not candidates:
        return None, 0.0

    best_location: Location | None = None
    best_score = 0.0

    for candidate in candidates:
        score = SequenceMatcher(None, neighborhood_canonical, candidate.neighborhood_canonical).ratio()
        if score > best_score:
            best_location = candidate
            best_score = score

    if best_location is None or best_score < threshold:
        return None, best_score

    return best_location, best_score


def _ensure_alias(
    db: Session,
    *,
    location_id: int,
    city_canonical: str,
    district_canonical: str,
    neighborhood_canonical: str,
    alias_source: str,
) -> None:
    existing_alias = (
        db.query(LocationAlias)
        .filter(
            LocationAlias.city_canonical == city_canonical,
            LocationAlias.district_canonical == district_canonical,
            LocationAlias.neighborhood_canonical == neighborhood_canonical,
        )
        .first()
    )
    if existing_alias is not None:
        return

    db.add(
        LocationAlias(
            location_id=location_id,
            city_canonical=city_canonical,
            district_canonical=district_canonical,
            neighborhood_canonical=neighborhood_canonical,
            alias_source=alias_source,
        )
    )


def resolve_location(
    db: Session,
    *,
    city: str,
    district: str,
    neighborhood: str,
    city_canonical: str | None,
    district_canonical: str | None,
    neighborhood_canonical: str | None,
    city_code: str | None,
    district_code: str | None,
    neighborhood_code: str | None,
    latitude: float | None,
    longitude: float | None,
    fuzzy_threshold: float = 0.88,
) -> ResolvedLocation:
    city_norm = city_canonical or to_canonical_location(city)
    district_norm = district_canonical or to_canonical_location(district)
    neighborhood_norm = neighborhood_canonical or to_canonical_location(neighborhood)

    if city_norm is None or district_norm is None or neighborhood_norm is None:
        return ResolvedLocation(
            location_id=None,
            city_canonical=city_norm,
            district_canonical=district_norm,
            neighborhood_canonical=neighborhood_norm,
            city_code=city_code,
            district_code=district_code,
            neighborhood_code=neighborhood_code,
            location_match_confidence=None,
        )

    exact = _exact_location_match(db, city_norm, district_norm, neighborhood_norm)
    if exact is not None:
        return ResolvedLocation(
            location_id=exact.id,
            city_canonical=exact.city_canonical,
            district_canonical=exact.district_canonical,
            neighborhood_canonical=exact.neighborhood_canonical,
            city_code=exact.city_code or city_code,
            district_code=exact.district_code or district_code,
            neighborhood_code=exact.neighborhood_code or neighborhood_code,
            location_match_confidence=1.0,
        )

    alias_match = _alias_location_match(db, city_norm, district_norm, neighborhood_norm)
    if alias_match is not None:
        return ResolvedLocation(
            location_id=alias_match.id,
            city_canonical=alias_match.city_canonical,
            district_canonical=alias_match.district_canonical,
            neighborhood_canonical=alias_match.neighborhood_canonical,
            city_code=alias_match.city_code or city_code,
            district_code=alias_match.district_code or district_code,
            neighborhood_code=alias_match.neighborhood_code or neighborhood_code,
            location_match_confidence=0.98,
        )

    fuzzy_match, fuzzy_score = _fuzzy_location_match(
        db,
        city_canonical=city_norm,
        district_canonical=district_norm,
        neighborhood_canonical=neighborhood_norm,
        threshold=fuzzy_threshold,
    )
    if fuzzy_match is not None:
        _ensure_alias(
            db,
            location_id=fuzzy_match.id,
            city_canonical=city_norm,
            district_canonical=district_norm,
            neighborhood_canonical=neighborhood_norm,
            alias_source="fuzzy",
        )
        return ResolvedLocation(
            location_id=fuzzy_match.id,
            city_canonical=fuzzy_match.city_canonical,
            district_canonical=fuzzy_match.district_canonical,
            neighborhood_canonical=fuzzy_match.neighborhood_canonical,
            city_code=fuzzy_match.city_code or city_code,
            district_code=fuzzy_match.district_code or district_code,
            neighborhood_code=fuzzy_match.neighborhood_code or neighborhood_code,
            location_match_confidence=round(fuzzy_score, 4),
        )

    created = Location(
        city_name=city,
        district_name=district,
        neighborhood_name=neighborhood,
        city_canonical=city_norm,
        district_canonical=district_norm,
        neighborhood_canonical=neighborhood_norm,
        city_code=city_code,
        district_code=district_code,
        neighborhood_code=neighborhood_code,
        centroid_latitude=latitude,
        centroid_longitude=longitude,
    )
    db.add(created)
    db.flush()

    _ensure_alias(
        db,
        location_id=int(created.id),
        city_canonical=city_norm,
        district_canonical=district_norm,
        neighborhood_canonical=neighborhood_norm,
        alias_source="exact_new",
    )

    return ResolvedLocation(
        location_id=int(created.id),
        city_canonical=created.city_canonical,
        district_canonical=created.district_canonical,
        neighborhood_canonical=created.neighborhood_canonical,
        city_code=created.city_code,
        district_code=created.district_code,
        neighborhood_code=created.neighborhood_code,
        location_match_confidence=1.0,
    )
