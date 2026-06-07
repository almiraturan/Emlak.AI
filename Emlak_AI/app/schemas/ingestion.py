from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IncomingListingPayload(BaseModel):
    # Dis kaynaktan gelen tek bir ilanin minimum gecerli veri yapisini tanimlar.
    model_config = ConfigDict(extra="ignore")

    source: str = Field(min_length=1, max_length=100)
    source_listing_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    listing_type: Literal["satilik", "kiralik"]
    property_type: Literal["daire", "villa", "arsa", "isyeri", "mustakil"]
    price: Decimal = Field(gt=0)
    currency: Literal["TRY", "USD", "EUR", "GBP"]
    area_m2: float = Field(gt=0)
    net_m2: float | None = Field(default=None, gt=0)
    gross_m2: float | None = Field(default=None, gt=0)
    room_layout_raw: str | None = Field(default=None, max_length=20)
    room_count_main: int | None = Field(default=None, ge=0, le=50)
    room_count_living: int | None = Field(default=None, ge=0, le=20)
    room_count_total: int = Field(ge=0, le=70)
    city: str = Field(min_length=1, max_length=100)
    district: str = Field(min_length=1, max_length=100)
    neighborhood: str = Field(min_length=1, max_length=100)
    city_canonical: str | None = Field(default=None, max_length=100)
    district_canonical: str | None = Field(default=None, max_length=100)
    neighborhood_canonical: str | None = Field(default=None, max_length=100)
    city_code: str | None = Field(default=None, max_length=16)
    district_code: str | None = Field(default=None, max_length=16)
    neighborhood_code: str | None = Field(default=None, max_length=16)
    location_id: int | None = Field(default=None, ge=1)
    location_match_confidence: float | None = Field(default=None, ge=0, le=1)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    building_age: int | None = Field(default=None, ge=0, le=250)
    floor: int | None = Field(default=None, ge=-10, le=300)
    heating_type: str | None = Field(default=None, min_length=1, max_length=100)
    image_count: int = Field(ge=0)
    images: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    source_updated_at: datetime | None = None
    is_active: bool = True
    source_url: str | None = Field(default=None, max_length=1000)

    @field_validator("price", mode="before")
    @classmethod
    def validate_price(cls, v: object) -> Decimal:
        # Para alani: Decimal'a parse et (string, float, int, Decimal'dan)
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(v))  # Float'i string uzerinden geç (hassasiyet icin)
        if isinstance(v, str):
            # Para formatlari: 2.500.000 TL, 2500000, 2,500.00, etc.
            text = v.strip().replace(" ", "")
            text = text.replace("TL", "").replace("TRY", "").replace("₺", "")
            text = text.replace("USD", "").replace("EUR", "").replace("GBP", "")
            text = text.replace("$", "").replace("€", "").replace("£", "")
            text = text.strip()

            # Virgül ve nokta kombinasyoni
            if "," in text and "." in text:
                # 2.500,00 veya 2,500.00 formatı
                if text.rindex(",") > text.rindex("."):
                    # 2.500,00 → virgül ondalık
                    text = text.replace(".", "").replace(",", ".")
                else:
                    # 2,500.00 → nokta ondalık
                    text = text.replace(",", "")
            elif "," in text:
                # 2,500 veya 2,5
                tekil_comma_idx = text.rfind(",")
                if tekil_comma_idx + 3 >= len(text):  # Sondan 2-3 karakter: ondalık
                    text = text.replace(",", ".")
                # else: 2,500 trilyon formatı (virgül binlik) → remove
                else:
                    text = text.replace(",", "")

            try:
                return Decimal(text)
            except (InvalidOperation, ValueError) as e:
                raise ValueError(f"price could not be parsed as Decimal: {text}") from e
        raise ValueError(f"price must be Decimal, int, float, or string, got {type(v)}")

    @model_validator(mode="after")
    def validate_media_and_sizes(self) -> "IncomingListingPayload":
        # net alanin gross alandan buyuk gelmesi veri hatasidir.
        if self.net_m2 is not None and self.gross_m2 is not None and self.net_m2 > self.gross_m2:
            raise ValueError("net_m2 gross_m2 degerinden buyuk olamaz")

        if self.room_count_main is not None and self.room_count_living is not None:
            expected_total = self.room_count_main + self.room_count_living
            if self.room_count_total != expected_total:
                raise ValueError("room_count_total, room_count_main + room_count_living ile ayni olmali")

        # image_count ile gercek resim listesi tutarli olmali.
        if self.image_count != len(self.images):
            raise ValueError("image_count images listesindeki eleman sayisi ile ayni olmali")

        return self



class IngestionItemReport(BaseModel):
    # invalid/skipped/error listelerinde tek bir kaydin nedenini gosteren rapor kalemi.
    source: str | None = None
    source_listing_id: str | None = None
    reason: str


class NormalizationReport(BaseModel):
    source: str | None = None
    source_listing_id: str | None = None
    quality_score: int = Field(ge=0, le=100)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ManualIngestionRequest(BaseModel):
    items: list[dict[str, object]] = Field(min_length=1, max_length=200)


class IngestionSyncResponse(BaseModel):
    # fetched: Adapterdan gelen toplam kayit sayisi.
    fetched: int
    # inserted: Ilk kez gorulen ve veritabanina eklenen kayit sayisi.
    inserted: int
    # updated: Daha once var olan ve alanlari guncellenen kayit sayisi.
    updated: int
    # reactivated: Daha once pasif olan ama bu run'da tekrar gorulup aktife alinan kayit sayisi.
    reactivated: int
    # deactivated: Bu run'da kaynakta gorulmeyen ve pasife cekilen kayit sayisi.
    deactivated: int
    # skipped: Kayit bulundu ama veri degismedigi icin yazilmayan kayit sayisi.
    skipped: int
    # invalid: Dogrulama kurallarini gecemeyen (zorunlu alan/tip/limit hatali) kayit sayisi.
    invalid: int
    # errors: Validation disinda calisma aninda hata alan kayit sayisi (DB/uygulama hatasi gibi).
    errors: int
    # skipped/invalid/error listeleri, hangi kaydin neden bu sonuca dustugunu aciklar.
    skipped_items: list[IngestionItemReport] = Field(default_factory=list)
    invalid_items: list[IngestionItemReport] = Field(default_factory=list)
    error_items: list[IngestionItemReport] = Field(default_factory=list)
    normalization_reports: list[NormalizationReport] = Field(default_factory=list)


class IngestionAsyncResponse(BaseModel):
    status: str
    message_id: str
