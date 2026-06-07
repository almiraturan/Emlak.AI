from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.ingestion_record import IngestionRecord
from app.models.listing import Listing

router = APIRouter(prefix="/qa", tags=["qa"])

_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "qa_dashboard.html"


@lru_cache(maxsize=1)
def _load_dashboard_html() -> str:
  return _TEMPLATE_PATH.read_text(encoding="utf-8")


@router.get("", response_class=HTMLResponse)
def qa_dashboard() -> str:
    return _load_dashboard_html()


def _get_ingestion_counts_since(db: Session, since: datetime) -> dict[str, int]:
    rows = (
        db.query(IngestionRecord.status, func.count(IngestionRecord.id))
        .filter(IngestionRecord.created_at >= since)
        .group_by(IngestionRecord.status)
        .all()
    )
    return {status: int(count) for status, count in rows}


@router.get("/api/summary")
def qa_summary(db: Session = Depends(get_db)) -> dict[str, object]:
    total_listings = int(db.query(func.count(Listing.id)).scalar() or 0)
    active_listings = int(db.query(func.count(Listing.id)).filter(Listing.is_active.is_(True)).scalar() or 0)
    with_geo = int(
        db.query(func.count(Listing.id))
        .filter(Listing.latitude.is_not(None), Listing.longitude.is_not(None))
        .scalar()
        or 0
    )
    missing_price = int(db.query(func.count(Listing.id)).filter(Listing.price.is_(None)).scalar() or 0)

    dup_query = text(
        """
        SELECT COALESCE(SUM(cnt - 1), 0) AS duplicate_count
        FROM (
            SELECT COUNT(*) AS cnt
            FROM listings
            GROUP BY source, source_listing_id
            HAVING COUNT(*) > 1
        ) grouped
        """
    )
    duplicate_source_records = int(db.execute(dup_query).scalar() or 0)

    by_source_rows = db.query(Listing.source, func.count(Listing.id)).group_by(Listing.source).all()
    by_source = {source: int(count) for source, count in by_source_rows}

    now = datetime.now(timezone.utc)
    last_24h = _get_ingestion_counts_since(db, now - timedelta(hours=24))

    payload = {
        "total_listings": total_listings,
        "active_listings": active_listings,
        "inactive_listings": max(total_listings - active_listings, 0),
        "with_geo": with_geo,
        "missing_price": missing_price,
        "duplicate_source_records": duplicate_source_records,
        "by_source": by_source,
        "ingestion_last_24h": last_24h,
    }
    return jsonable_encoder(payload)


@router.get("/api/ingestion-records")
def qa_ingestion_records(
    limit: int = Query(default=40, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    records = (
        db.query(IngestionRecord)
        .order_by(IngestionRecord.created_at.desc(), IngestionRecord.id.desc())
        .limit(limit)
        .all()
    )

    items = [
        {
            "id": r.id,
            "created_at": r.created_at,
            "status": r.status,
            "source": r.source,
            "source_listing_id": r.source_listing_id,
            "listing_id": r.listing_id,
            "detail": r.detail,
        }
        for r in records
    ]
    return jsonable_encoder({"items": items, "count": len(items)})


@router.get("/api/listing-sample")
def qa_listing_sample(
    limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    listings = (
        db.query(Listing)
        .order_by(Listing.source_updated_at.desc().nullslast(), Listing.id.desc())
        .limit(limit)
        .all()
    )

    items = [
        {
            "id": listing.id,
            "title": listing.title,
            "city": listing.city,
            "district": listing.district,
            "neighborhood": listing.neighborhood,
            "price": listing.price,
            "currency": listing.currency,
            "source": listing.source,
            "source_listing_id": listing.source_listing_id,
            "is_active": listing.is_active,
            "source_updated_at": listing.source_updated_at,
        }
        for listing in listings
    ]
    return jsonable_encoder({"items": items, "count": len(items)})
