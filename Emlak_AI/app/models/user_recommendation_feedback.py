from sqlalchemy import Boolean, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class UserRecommendationFeedback(Base):
    __tablename__ = "user_recommendation_feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), nullable=False)
    liked: Mapped[bool] = mapped_column(Boolean, nullable=False)  # True for liked, False for disliked