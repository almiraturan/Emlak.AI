from sqlalchemy import Boolean, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class UserInteraction(Base):
    __tablename__ = "user_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), nullable=False)
    liked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    viewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
