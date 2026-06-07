from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class IngestionRecord(Base):
    # Her ingestion denemesinde gelen ham veriyi ve sonucun ne oldugunu saklar.
    __tablename__ = "ingestion_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_listing_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # status degeri: inserted | updated | skipped | invalid | error | deactivated
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    # detail, ilgili kaydin neden o status'u aldigini metin olarak aciklar.
    detail: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # raw_payload, kaynaktan gelen ham verinin birebir saklanan halidir (debug/audit icin kritik).
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    # listing_id sadece kayit DB'deki bir listing ile eslestiyse doldurulur.
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
