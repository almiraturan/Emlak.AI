"""Orchestrator Agent that coordinates all AI agents."""
import asyncio
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
        """
        Comprehensive analysis of user and listing combination.

        Returns:
            {
                profile: {...},
                lifestyle: {...},
                price: {...},
                recommendation: {...},
                total_duration_ms: ...
            }
        """
        start_time = time.time()

        try:
            # Fetch listing
            listing = db.query(Listing).filter(Listing.id == listing_id).first()
            if not listing:
                return {
                    "error": "Listing not found",
                    "total_duration_ms": (time.time() - start_time) * 1000,
                }

            # Run profile, lifestyle, and price agents in parallel
            profile_task = asyncio.create_task(
                self._async_get_profile(user_id, db)
            )
            lifestyle_task = asyncio.create_task(
                self._async_get_lifestyle(listing)
            )
            price_task = asyncio.create_task(
                self._async_analyze_price(listing_id, db)
            )

            # Wait for all to complete
            results = await asyncio.gather(
                profile_task, lifestyle_task, price_task,
                return_exceptions=True
            )

            profile = results[0] if not isinstance(results[0], Exception) else None
            lifestyle = results[1] if not isinstance(results[1], Exception) else None
            price = results[2] if not isinstance(results[2], Exception) else None

            # Get recommendations based on profile
            recommendation = None
            if profile:
                recommendation = await self._async_get_recommendations(
                    user_id, db
                )

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

    async def _async_get_profile(self, user_id: int, db: Session) -> Dict:
        """Get profile asynchronously."""
        try:
            return self.profile_agent.get_profile(user_id, db)
        except Exception as e:
            logger.error(f"Error getting profile: {e}")
            return None

    async def _async_get_lifestyle(self, listing: Listing) -> Dict:
        """Get lifestyle score asynchronously and preserve POI details.

        This will call the live lifestyle agent to obtain full POI details
        and then, if a DB-stored `lifestyle_score` exists for the listing,
        override only the numeric `score` while keeping POI details.
        """
        try:
            if not listing.latitude or not listing.longitude:
                # No coordinates -> return a neutral score
                return {
                    "score": 5.0,
                    "description": "No location data",
                    "poi_counts": {},
                    "nearest_distances_km": {},
                    "poi_names": {},
                    "search_radius_km": None,
                    "transit_search_radius_km": None,
                    "source": "error",
                }

            # Obtain full POI analysis from the lifestyle agent
            lifestyle_result = self.lifestyle_agent.score_lifestyle(
                listing.latitude, listing.longitude
            )

            # If we have a stored score in DB, override only the numeric score
            # but keep POI details so the analyze view remains informative.
            if listing.lifestyle_score is not None and isinstance(lifestyle_result, dict):
                try:
                    lifestyle_result["score"] = float(listing.lifestyle_score)
                except Exception:
                    # If conversion fails, leave live score intact
                    pass
                lifestyle_result["source"] = "db"
                lifestyle_result["description"] = "Stored score with current POI analysis"

            return lifestyle_result
        except Exception as e:
            logger.error(f"Error getting lifestyle: {e}")
            return None

    async def _async_analyze_price(
        self, listing_id: int, db: Session
    ) -> Dict:
        """Analyze price asynchronously."""
        try:
            return self.price_agent.analyze_price(listing_id, db)
        except Exception as e:
            logger.error(f"Error analyzing price: {e}")
            return None

    async def _async_get_recommendations(
        self, user_id: int, db: Session
    ) -> Dict:
        """Get recommendations asynchronously."""
        try:
            return self.recommendation_agent.get_recommendations(user_id, db)
        except Exception as e:
            logger.error(f"Error getting recommendations: {e}")
            return None
