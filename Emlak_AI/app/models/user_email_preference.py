from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class UserEmailPreference(Base):
    __tablename__ = "user_email_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    subscribed: Mapped[bool] = mapped_column(Boolean, default=True)
    min_lifestyle_score: Mapped[int] = mapped_column(Integer, default=8)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_notification_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ListingNotificationSent(Base):
    __tablename__ = "listing_notifications_sent"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    listing_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
