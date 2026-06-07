from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Listing(Base):
    # Uygulamadaki ana ilan tablosu; hem seed veriler hem de dis kaynak verileri burada tutulur.
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # description, ilanin detayli metnini tutar; arama ve analiz icin faydalidir.
    description: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    # listing_type ve property_type, filtreleme ve urun kurgusu icin temel kategorilerdir.
    listing_type: Mapped[str] = mapped_column(String(50), nullable=False, default="satilik")
    property_type: Mapped[str] = mapped_column(String(50), nullable=False, default="daire")
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # currency farkli kaynaklardan gelen fiyatlari anlamlandirmak icin tutulur.
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="TRY")
    area_m2: Mapped[float] = mapped_column(Float, nullable=False)
    # net_m2/gross_m2 ayrimi filtreleme ve karsilastirma kalitesini artirir.
    net_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Oda plani bilgisini kaybetmemek icin hem ham ifade hem de parcali alanlar tutulur.
    room_layout_raw: Mapped[str | None] = mapped_column(String(20), nullable=True)
    room_count_main: Mapped[int | None] = mapped_column(Integer, nullable=True)
    room_count_living: Mapped[int | None] = mapped_column(Integer, nullable=True)
    room_count_total: Mapped[int] = mapped_column(Integer, nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    district: Mapped[str] = mapped_column(String(100), nullable=False)
    neighborhood: Mapped[str] = mapped_column(String(100), nullable=False)
    city_canonical: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district_canonical: Mapped[str | None] = mapped_column(String(100), nullable=True)
    neighborhood_canonical: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    city_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    district_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    neighborhood_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    location_match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    building_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heating_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Gorsel sayisi ve gorsel linkleri kalite puani, UI ve filtreleme icin saklanir.
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    images: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Ilanin yayin ve kaynak guncellenme tarihleri zaman bazli analizlerde kullanilir.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Ilanin kaynakta gorulme yasam dongusu alanlari.
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ingested_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # is_active, ilanin yayinda olup olmadigini gosterir.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Lifestyle score for the listing (1-10 scale)
    lifestyle_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Price analysis fields
    price_market_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 'overpriced', 'fair', 'underpriced'
    price_trend_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 'up', 'down', 'stable'
    price_comparables_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # source alanlari, ilanin hangi sistemden geldiginin izlenmesini ve tekrarlarin engellenmesini saglar.
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_listing_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    location = relationship("Location", lazy="joined")
