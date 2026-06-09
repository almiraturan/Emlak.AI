from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    budget_min: Mapped[float] = mapped_column(Float, nullable=False)
    budget_max: Mapped[float] = mapped_column(Float, nullable=False)
    preferred_rooms: Mapped[int] = mapped_column(Integer, nullable=False)
    prefers_quiet: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prefers_central: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    password: Mapped[str] = mapped_column(String(100), nullable=False, default="12345")
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
