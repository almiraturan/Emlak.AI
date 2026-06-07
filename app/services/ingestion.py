from decimal import Decimal
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from sqlalchemy.orm import Session
from pydantic import ValidationError
from sqlalchemy import delete

from app.models.ingestion_record import IngestionRecord
from app.models.listing import Listing
from app.models.listing_image import ListingImage
from app.providers.base import RawListingPayload
from app.providers.registry import get_default_provider, get_provider
from app.schemas.ingestion import IncomingListingPayload
from app.services.location_resolver import resolve_location
from app.services.listing_normalizer import normalize_listing_payload

ListingNormalizer = Callable[..., tuple[dict[str, object], dict[str, object]]]


def _build_payload(item: IncomingListingPayload) -> dict[str, str | Decimal | float | int | None]:
    # Validation'dan gecen payload bu noktada Listing modelinin alanlarina map edilir.
    return {
        "title": item.title,
        "description": item.description,
        "listing_type": item.listing_type,
        "property_type": item.property_type,
        "price": item.price,
        "currency": item.currency,
        "area_m2": item.area_m2,
        "net_m2": item.net_m2,
        "gross_m2": item.gross_m2,
        "room_layout_raw": item.room_layout_raw,
        "room_count_main": item.room_count_main,
        "room_count_living": item.room_count_living,
        "room_count_total": item.room_count_total,
        "city": item.city,
        "district": item.district,
        "neighborhood": item.neighborhood,
        "city_canonical": item.city_canonical,
        "district_canonical": item.district_canonical,
        "neighborhood_canonical": item.neighborhood_canonical,
        "location_id": item.location_id,
        "city_code": item.city_code,
        "district_code": item.district_code,
        "neighborhood_code": item.neighborhood_code,
        "location_match_confidence": item.location_match_confidence,
        "latitude": item.latitude,
        "longitude": item.longitude,
        "building_age": item.building_age,
        "floor": item.floor,
        "heating_type": item.heating_type,
        "image_count": item.image_count,
        "images": item.images,
        "published_at": item.published_at,
        "source_updated_at": item.source_updated_at,
        "source": item.source,
        "source_listing_id": item.source_listing_id,
        "source_url": item.source_url,
    }


def _create_ingestion_record(
    db: Session,
    raw_payload: RawListingPayload,
    status: str,
    detail: str | None,
    source: str | None,
    source_listing_id: str | None,
    listing_id: int | None = None,
) -> None:
    db.add(
        IngestionRecord(
            source=source,
            source_listing_id=source_listing_id,
            status=status,
            detail=detail,
            raw_payload=raw_payload,
            listing_id=listing_id,
        )
    )


def _format_normalization_report(report: dict[str, object]) -> str:
    missing_fields = report.get("missing_fields")
    warnings = report.get("warnings")
    quality_score = report.get("quality_score")

    missing_count = len(missing_fields) if isinstance(missing_fields, list) else 0
    warning_count = len(warnings) if isinstance(warnings, list) else 0
    return f"quality={quality_score}; missing={missing_count}; warnings={warning_count}"


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        location = ".".join(str(item) for item in err["loc"])
        parts.append(f"{location}: {err['msg']}")
    return "; ".join(parts)


def _is_same_payload(existing: Listing, payload: dict[str, str | float | int | None]) -> bool:
    return all(getattr(existing, field) == value for field, value in payload.items())


def _sync_listing_images(db: Session, listing_id: int, images: list[str]) -> None:
    # JSON alanla uyumlu kalacak sekilde görsel satırlarını baştan kurar.
    db.execute(delete(ListingImage).where(ListingImage.listing_id == listing_id))
    for idx, url in enumerate(images):
        db.add(
            ListingImage(
                listing_id=listing_id,
                url=url,
                order_index=idx,
                is_cover=(idx == 0),
                status="active",
            )
        )


def _upsert_listing(
    db: Session,
    item: IncomingListingPayload,
    raw_payload: RawListingPayload,
    run_id: str,
    seen_at: datetime,
) -> tuple[str, bool]:
    # Ayni ilani bulmak icin kaynak adi ve kaynaktaki ilan kimligi birlikte kullanilir.
    existing = (
        db.query(Listing)
        .filter(
            Listing.source == item.source,
            Listing.source_listing_id == item.source_listing_id,
        )
        .first()
    )

    resolved_location = resolve_location(
        db,
        city=item.city,
        district=item.district,
        neighborhood=item.neighborhood,
        city_canonical=item.city_canonical,
        district_canonical=item.district_canonical,
        neighborhood_canonical=item.neighborhood_canonical,
        city_code=item.city_code,
        district_code=item.district_code,
        neighborhood_code=item.neighborhood_code,
        latitude=item.latitude,
        longitude=item.longitude,
    )

    item = item.model_copy(
        update={
            "location_id": resolved_location.location_id,
            "city_canonical": resolved_location.city_canonical,
            "district_canonical": resolved_location.district_canonical,
            "neighborhood_canonical": resolved_location.neighborhood_canonical,
            "city_code": resolved_location.city_code,
            "district_code": resolved_location.district_code,
            "neighborhood_code": resolved_location.neighborhood_code,
            "location_match_confidence": resolved_location.location_match_confidence,
        }
    )

    payload = _build_payload(item)
    payload.pop("is_active", None)

    if existing is None:
        new_listing = Listing(
            **payload,
            is_active=True,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            deactivated_at=None,
            last_ingested_run_id=run_id,
        )
        db.add(new_listing)
        db.flush()
        _sync_listing_images(db, int(new_listing.id), item.images)
        _create_ingestion_record(
            db,
            raw_payload=raw_payload,
            status="inserted",
            detail="Yeni ilan eklendi.",
            source=item.source,
            source_listing_id=item.source_listing_id,
            listing_id=int(new_listing.id),
        )
        return "inserted", False

    was_reactivated = bool(existing.is_active is False)

    # Her gorulen ilan aktif kabul edilir; gorulmeme durumunda run sonunda pasife cekilir.
    existing.is_active = True

    if _is_same_payload(existing, payload):
        existing.last_seen_at = seen_at
        existing.last_ingested_run_id = run_id
        if existing.first_seen_at is None:
            existing.first_seen_at = seen_at
        if was_reactivated:
            existing.deactivated_at = None
        _create_ingestion_record(
            db,
            raw_payload=raw_payload,
            status="skipped",
            detail="Kayit degismedigi icin atlandi.",
            source=item.source,
            source_listing_id=item.source_listing_id,
            listing_id=existing.id,
        )
        return "skipped", was_reactivated

    # Kayit zaten varsa tum alanlar gelen veriyle guncellenir.
    for field, value in payload.items():
        setattr(existing, field, value)

    existing.last_seen_at = seen_at
    existing.last_ingested_run_id = run_id
    if existing.first_seen_at is None:
        existing.first_seen_at = seen_at
    if was_reactivated:
        existing.deactivated_at = None

    _create_ingestion_record(
        db,
        raw_payload=raw_payload,
        status="updated",
        detail="Mevcut ilan guncellendi.",
        source=item.source,
        source_listing_id=item.source_listing_id,
        listing_id=existing.id,
    )
    _sync_listing_images(db, int(existing.id), item.images)
    return "updated", was_reactivated


def _deactivate_missing_listings(
    db: Session,
    seen_source_listing_ids_by_source: dict[str, set[str]],
    run_id: str,
    deactivated_at: datetime,
) -> int:
    deactivated_count = 0

    for source, seen_ids in seen_source_listing_ids_by_source.items():
        if not seen_ids:
            continue

        to_deactivate = (
            db.query(Listing)
            .filter(
                Listing.source == source,
                Listing.is_active.is_(True),
                ~Listing.source_listing_id.in_(seen_ids),
            )
            .all()
        )

        for listing in to_deactivate:
            listing.is_active = False
            listing.deactivated_at = deactivated_at
            listing.last_ingested_run_id = run_id
            _create_ingestion_record(
                db,
                raw_payload={},
                status="deactivated",
                detail="Kaynakta gorulmedigi icin pasife cekildi.",
                source=listing.source,
                source_listing_id=listing.source_listing_id,
                listing_id=listing.id,
            )

        deactivated_count += len(to_deactivate)

    return deactivated_count


def ingest_listings(
    db: Session,
    incoming: list[RawListingPayload],
    fallback_source: str,
    source_id_prefix: str,
    full_sync: bool = True,
    normalize_item: ListingNormalizer | None = None,
) -> dict[str, int | list[dict[str, str | int | None]]]:
    run_id = uuid4().hex
    seen_at = datetime.now(timezone.utc)

    # Sonuc raporu: Gercek kaynaklarda operasyonu izlemek icin metrikler birlikte tutulur.
    result: dict[str, int | list[dict[str, str | int | None]]] = {
        "fetched": len(incoming),
        "inserted": 0,
        "updated": 0,
        "reactivated": 0,
        "deactivated": 0,
        "skipped": 0,
        "invalid": 0,
        "errors": 0,
        "skipped_items": [],
        "invalid_items": [],
        "error_items": [],
        "normalization_reports": [],
    }

    seen_source_listing_ids_by_source: dict[str, set[str]] = {}

    for idx, raw_payload in enumerate(incoming, start=1):
        fallback_source_listing_id = f"{source_id_prefix}-{idx}"
        if normalize_item is None:
            normalized_payload, normalization_report = normalize_listing_payload(
                raw_payload=raw_payload,
                fallback_source=fallback_source,
                fallback_source_listing_id=fallback_source_listing_id,
            )
        else:
            normalized_payload, normalization_report = normalize_item(
                raw_payload,
                fallback_source_listing_id=fallback_source_listing_id,
            )

        normalization_reports = result["normalization_reports"]
        if isinstance(normalization_reports, list):
            normalization_reports.append(normalization_report)

        # Validation oncesinde temel kimlik alanlari ayrica cikarilir.
        # Boylece gecersiz kayitlarda bile hangi ilanin sorunlu oldugu raporlanabilir.
        source = str(normalized_payload.get("source")) if normalized_payload.get("source") is not None else None
        source_listing_id = (
            str(normalized_payload.get("source_listing_id"))
            if normalized_payload.get("source_listing_id") is not None
            else None
        )

        try:
            item = IncomingListingPayload.model_validate(normalized_payload)
        except ValidationError as exc:
            # Validation hatasinda kayit topluca dusurulmez; invalid olarak isaretlenip devam edilir.
            reason = f"{_format_validation_error(exc)} | {_format_normalization_report(normalization_report)}"
            _create_ingestion_record(
                db,
                raw_payload=raw_payload,
                status="invalid",
                detail=reason,
                source=source,
                source_listing_id=source_listing_id,
            )
            db.commit()
            result["invalid"] = int(result["invalid"]) + 1
            invalid_items = result["invalid_items"]
            if isinstance(invalid_items, list):
                invalid_items.append(
                    {
                        "source": source,
                        "source_listing_id": source_listing_id,
                        "reason": reason,
                    }
                )
            continue

        seen_source_listing_ids_by_source.setdefault(item.source, set()).add(item.source_listing_id)

        try:
            action, was_reactivated = _upsert_listing(db, item, raw_payload, run_id=run_id, seen_at=seen_at)
            db.commit()
            result[action] = int(result[action]) + 1
            if was_reactivated:
                result["reactivated"] = int(result["reactivated"]) + 1
            if action == "skipped":
                # skipped listesi, kayit neden yazilmadi sorusuna net cevap verir.
                skipped_items = result["skipped_items"]
                if isinstance(skipped_items, list):
                    skipped_items.append(
                        {
                            "source": item.source,
                            "source_listing_id": item.source_listing_id,
                            "reason": "Kayit degismedigi icin atlandi.",
                        }
                    )
        except Exception as exc:
            # Validation disi teknik hatalar errors hanesine yazilir ve bir sonraki kayda gecilir.
            db.rollback()
            reason = str(exc)
            try:
                _create_ingestion_record(
                    db,
                    raw_payload=raw_payload,
                    status="error",
                    detail=f"{reason} | {_format_normalization_report(normalization_report)}",
                    source=item.source,
                    source_listing_id=item.source_listing_id,
                )
                db.commit()
            except Exception:
                db.rollback()

            result["errors"] = int(result["errors"]) + 1
            error_items = result["error_items"]
            if isinstance(error_items, list):
                error_items.append(
                    {
                        "source": item.source,
                        "source_listing_id": item.source_listing_id,
                        "reason": reason,
                    }
                )

    if full_sync:
        try:
            deactivated_count = _deactivate_missing_listings(
                db,
                seen_source_listing_ids_by_source=seen_source_listing_ids_by_source,
                run_id=run_id,
                deactivated_at=seen_at,
            )
            db.commit()
            result["deactivated"] = int(result["deactivated"]) + deactivated_count
        except Exception:
            db.rollback()

    return result


def ingest_external_listings(db: Session) -> dict[str, int | list[dict[str, str | int | None]]]:
    return ingest_provider_listings(db)


def ingest_provider_listings(
    db: Session,
    provider_name: str | None = None,
) -> dict[str, int | list[dict[str, str | int | None]]]:
    # Ingestion orkestrasyonu artik veri kaynaginin API/crawl detayini bilmez.
    provider = get_default_provider() if provider_name is None else get_provider(provider_name)
    try:
        incoming = provider.fetch_listings()
    except Exception as exc:
        return {
            "fetched": 0,
            "inserted": 0,
            "updated": 0,
            "reactivated": 0,
            "deactivated": 0,
            "skipped": 0,
            "invalid": 0,
            "errors": 1,
            "skipped_items": [],
            "invalid_items": [],
            "error_items": [
                {
                    "source": provider.name,
                    "source_listing_id": None,
                    "reason": str(exc),
                }
            ],
            "normalization_reports": [],
        }

    capabilities = provider.capabilities()
    source_id_prefix = provider.name.upper().replace("-", "_")

    return ingest_listings(
        db,
        incoming,
        fallback_source=provider.name,
        source_id_prefix=source_id_prefix,
        full_sync=capabilities.full_sync,
        normalize_item=provider.normalize,
    )
