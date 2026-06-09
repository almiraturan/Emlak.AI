"""Orchestrator Agent that coordinates all AI agents."""
import asyncio
import concurrent.futures
import logging
import time
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.agents.profile_agent import ProfileAgent
from app.agents.lifestyle_agent import LifestyleAgent
from app.agents.price_agent import PriceAgent
from app.agents.comparison_agent import ComparisonAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.models.listing import Listing

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """Orchestrator Agent that coordinates all AI agents."""

    def __init__(self):
        """Initialize all agents."""
        self.profile_agent = ProfileAgent()
        self.lifestyle_agent = LifestyleAgent()
        self.price_agent = PriceAgent()
        self.comparison_agent = ComparisonAgent()
        self.recommendation_agent = RecommendationAgent()

    def train_all_models(self, db: Session) -> Dict:
        """Train all ML models."""
        results = {
            "profile_agent": self.profile_agent.train(db),
            "price_agent": self.price_agent.train(db),
            "recommendation_agent": self.recommendation_agent.train(db),
        }
        return results

    async def analyze_user_listing(
        self, user_id: int, listing_id: int, db: Session
    ) -> Dict:
        """Comprehensive analysis of user and listing combination."""
        start_time = time.time()

        try:
            listing = db.query(Listing).filter(Listing.id == listing_id).first()
            if not listing:
                return {
                    "error": "Listing not found",
                    "total_duration_ms": (time.time() - start_time) * 1000,
                }

            loop = asyncio.get_event_loop()
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

            # Run all four agents truly in parallel via thread pool
            futures = await asyncio.gather(
                loop.run_in_executor(executor, self._sync_get_profile, user_id, db),
                loop.run_in_executor(executor, self._sync_get_lifestyle, listing),
                loop.run_in_executor(executor, self._sync_analyze_price, listing_id, db),
                loop.run_in_executor(executor, self._sync_get_recommendations, user_id, db),
                return_exceptions=True,
            )
            executor.shutdown(wait=False)

            profile     = futures[0] if not isinstance(futures[0], Exception) else None
            lifestyle   = futures[1] if not isinstance(futures[1], Exception) else None
            price       = futures[2] if not isinstance(futures[2], Exception) else None
            recommendation = futures[3] if not isinstance(futures[3], Exception) else None

            duration_ms = (time.time() - start_time) * 1000

            return {
                "listing": {
                    "id": listing.id,
                    "title": listing.title,
                    "price": float(listing.price) if listing.price is not None else 0.0,
                    "city": listing.city,
                    "district": listing.district,
                    "neighborhood": listing.neighborhood,
                },
                "profile": profile,
                "lifestyle": lifestyle,
                "price": price,
                "recommendation": recommendation,
                "total_duration_ms": duration_ms,
            }

        except Exception as e:
            logger.error(f"Error in orchestration: {e}")
            return {
                "error": str(e),
                "total_duration_ms": (time.time() - start_time) * 1000,
            }

    def _sync_get_profile(self, user_id: int, db: Session) -> Dict:
        try:
            return self.profile_agent.get_profile(user_id, db)
        except Exception as e:
            logger.error(f"Error getting profile: {e}")
            return None

    def _sync_get_lifestyle(self, listing: Listing) -> Dict:
        try:
            if not listing.latitude or not listing.longitude:
                return {
                    "score": listing.lifestyle_score or 5.0,
                    "description": "Konum verisi yok",
                    "poi_counts": {},
                    "nearest_distances_km": {},
                    "poi_names": {},
                    "search_radius_km": None,
                    "transit_search_radius_km": None,
                    "source": "error",
                }

            # Always run live POI analysis for detail cards.
            # Thread pool executor ensures this runs in parallel with other agents.
            result = self.lifestyle_agent.score_lifestyle(
                listing.latitude, listing.longitude
            )

            # If a DB-stored score exists, override only the numeric score
            # while keeping the fresh POI details for the UI.
            if listing.lifestyle_score is not None and isinstance(result, dict):
                result["score"] = float(listing.lifestyle_score)
                result["source"] = "db"
                result["description"] = "Kayıtlı yaşam skoru"

            return result
        except Exception as e:
            logger.error(f"Error getting lifestyle: {e}")
            return None

    def _sync_analyze_price(self, listing_id: int, db: Session) -> Dict:
        try:
            return self.price_agent.analyze_price(listing_id, db)
        except Exception as e:
            logger.error(f"Error analyzing price: {e}")
            return None

    def _sync_get_recommendations(self, user_id: int, db: Session) -> Dict:
        try:
            return self.recommendation_agent.get_recommendations(user_id, db)
        except Exception as e:
            logger.error(f"Error getting recommendations: {e}")
            return None
