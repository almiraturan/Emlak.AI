from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.providers.registry import list_providers
from app.database.session import get_db
from app.schemas.ingestion import IngestionAsyncResponse, IngestionSyncResponse, ManualIngestionRequest
from app.services.background import ingest_demo_source_job
from app.services.ingestion import ingest_listings, ingest_provider_listings

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/demo-sync", response_model=IngestionSyncResponse)
def run_demo_ingestion_sync(
    provider_name: Annotated[
        str | None,
        Query(
            description="Calistirilacak provider adı (ornek: emlakjet)",
            example="emlakjet",
        ),
    ] = None,
    db: Session = Depends(get_db),
) -> IngestionSyncResponse:
    # Sync akista istek geldiginde ingestion hemen calisir ve sonucu aninda doner.
    try:
        return ingest_provider_listings(db, provider_name=provider_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/manual-sync", response_model=IngestionSyncResponse)
def run_manual_ingestion_sync(payload: ManualIngestionRequest, db: Session = Depends(get_db)) -> IngestionSyncResponse:
    # Kullanici tarafindan gelen ham verileri normalize ederek DB'ye yazar.
    return ingest_listings(
        db,
        incoming=payload.items,
        fallback_source="manual_input",
        source_id_prefix="MANUAL",
        full_sync=False,
    )


@router.post("/demo-async", response_model=IngestionAsyncResponse)
def run_demo_ingestion_async(
    provider_name: Annotated[
        str | None,
        Query(
            description=(
                "Kuyruga gonderilecek provider adi. Desteklenenler: "
                + ", ".join(list_providers())
            ),
            example="emlakjet",
        ),
    ] = None,
) -> IngestionAsyncResponse:
    # Async akista is kuyruğa atilir; worker arka planda islemi tamamlar.
    message = ingest_demo_source_job.send(provider_name)
    return {"status": "queued", "message_id": message.message_id}
