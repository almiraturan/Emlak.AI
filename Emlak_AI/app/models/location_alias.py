from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class LocationAlias(Base):
    __tablename__ = "location_aliases"
    __table_args__ = (
        UniqueConstraint(
            "city_canonical",
            "district_canonical",
            "neighborhood_canonical",
            name="uq_location_aliases_canonical_triplet",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True)

    city_canonical: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    district_canonical: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    neighborhood_canonical: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    alias_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
