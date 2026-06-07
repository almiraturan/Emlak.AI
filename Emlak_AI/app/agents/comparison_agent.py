"""Smart Comparison Agent using LLM."""
import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.lifestyle_agent import LifestyleAgent
from app.agents.price_agent import PriceAgent
from app.models.listing import Listing

logger = logging.getLogger(__name__)


class ComparisonAgent(BaseAgent):
    """Smart Comparison using LLM-based analysis."""

    def __init__(self):
        """Initialize the agent."""
        super().__init__()
        self.profile_agent = ProfileAgent()
        self.lifestyle_agent = LifestyleAgent()
        self.price_agent = PriceAgent()

    def compare_listings(
        self, listing_ids: List[int], user_id: int, db: Session
    ) -> Dict:
        """
        Compare multiple listings based on user profile.

        Args:
            listing_ids: IDs of listings to compare
            user_id: ID of user making comparison
            db: Database session

        Returns:
            {
                ranking: [listing_ids in order],
                trade_offs: [descriptions],
                scores: {listing_id: {lifestyle, price, ...}}
            }
        """
        try:
            # Fetch user profile
            profile = self.profile_agent.get_profile(user_id, db)

            # Fetch and score listings
            listing_scores = {}
            for listing_id in listing_ids:
                listing = db.query(Listing).filter(Listing.id == listing_id).first()
                if not listing:
                    continue

                scores = {
                    "id": listing_id,
                    "title": listing.title,
                    "price": float(listing.price),
                    "area_m2": listing.area_m2,
                    "rooms": listing.room_count_total,
                }

                # Get lifestyle score
                if listing.latitude and listing.longitude:
                    lifestyle = self.lifestyle_agent.score_lifestyle(
                        listing.latitude, listing.longitude
                    )
                    scores["lifestyle_score"] = lifestyle["score"]
                else:
                    scores["lifestyle_score"] = 5.0

                # Get price analysis
                price_analysis = self.price_agent.analyze_price(listing_id, db)
                scores["price_verdict"] = price_analysis["verdict"]
                scores["price_diff_pct"] = price_analysis["difference_pct"]

                # Calculate total score
                total = (
                    scores["lifestyle_score"] * 0.3 +
                    (10 if scores["price_verdict"] == "fair" else
                     5 if scores["price_verdict"] == "underpriced" else 0) * 0.4 +
                    (10 - (abs(scores["area_m2"] - 100) / 10)) * 0.3  # area preference
                )
                scores["total_score"] = max(0, min(10, total))

                listing_scores[listing_id] = scores

            # If Ollama available, use LLM for intelligent ranking
            if self.is_ollama_available() and listing_scores:
                ranking, trade_offs = self._get_llm_comparison(
                    profile, listing_scores
                )
            else:
                # Fallback: rank by total score
                ranking = sorted(
                    listing_ids,
                    key=lambda x: listing_scores.get(x, {}).get("total_score", 0),
                    reverse=True,
                )
                trade_offs = []

            return {
                "ranking": ranking,
                "trade_offs": trade_offs,
                "scores": listing_scores,
                "user_profile": profile,
            }

        except Exception as e:
            logger.error(f"Error comparing listings: {e}")
            return {
                "ranking": listing_ids,
                "trade_offs": [],
                "scores": {},
                "user_profile": {},
            }

    def _get_llm_comparison(
        self, profile: Dict, listing_scores: Dict
    ) -> tuple:
        """Get LLM-based comparison and ranking."""
        try:
            # Format data for LLM
            profile_str = f"""
User Profile:
- Type: {profile.get('cluster_label', 'unknown')}
- Description: {profile.get('description', '')}
- Features: {profile.get('metadata', {})}
"""

            listings_str = "Listings:\n"
            for lid, scores in listing_scores.items():
                listings_str += f"""
- ID: {lid}, Title: {scores.get('title', 'Unknown')}
  Price: {scores.get('price', 'N/A')} TRY
  Area: {scores.get('area_m2', 'N/A')} m²
  Rooms: {scores.get('rooms', 'N/A')}
  Lifestyle Score: {scores.get('lifestyle_score', 5.0)}/10
  Price Verdict: {scores.get('price_verdict', 'N/A')}
  Total Score: {scores.get('total_score', 5.0)}/10
"""

            prompt = f"""Compare the following property listings based on the user profile.
Identify strengths and weaknesses for each listing.
Return only JSON, no extra text:
{{ranking: [listing_ids in order], trade_offs: [description list]}}

{profile_str}

{listings_str}"""

            response = self.call_llm(prompt)

            if response:
                result = self.parse_json(response)
                if result and "ranking" in result:
                    return result.get("ranking", []), result.get("trade_offs", [])

        except Exception as e:
            logger.debug(f"LLM comparison failed: {e}")

        return [], []
