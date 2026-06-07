from sqlalchemy import Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint(
            "city_canonical",
            "district_canonical",
            "neighborhood_canonical",
            name="uq_locations_canonical_triplet",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    city_name: Mapped[str] = mapped_column(String(100), nullable=False)
    district_name: Mapped[str] = mapped_column(String(100), nullable=False)
    neighborhood_name: Mapped[str] = mapped_column(String(100), nullable=False)

    city_canonical: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    district_canonical: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    neighborhood_canonical: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    city_code: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    district_code: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    neighborhood_code: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)

    centroid_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
