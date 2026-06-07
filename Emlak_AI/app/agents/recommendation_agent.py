"""AI Recommendation Engine using Collaborative Filtering + LLM."""
import os
import pickle
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.agents.profile_agent import ProfileAgent
from app.models.listing import Listing
from app.models.user_behavior import UserBehavior

logger = logging.getLogger(__name__)

MODEL_PATH = "app/ml_models/recommendation_svd.pkl"
MIN_USERS_FOR_CF = 5  # Minimum users for collaborative filtering
TOP_N = 10  # Top recommendations to return

# Behavior weights for collaborative filtering
BEHAVIOR_WEIGHTS = {
    "save": 3,
    "click": 1,
    "skip": -1,
}


class RecommendationAgent(BaseAgent):
    """AI Recommendation Engine using Collaborative Filtering + LLM."""

    def __init__(self):
        """Initialize the agent."""
        super().__init__()
        self.model = None
        self.user_encoder = None
        self.listing_encoder = None
        self.load_model()
        self.profile_agent = ProfileAgent()

    def load_model(self) -> None:
        """Load the trained model from disk if it exists."""
        if os.path.exists(MODEL_PATH):
            try:
                with open(MODEL_PATH, "rb") as f:
                    data = pickle.load(f)
                    self.model = data["model"]
                    self.user_encoder = data["user_encoder"]
                    self.listing_encoder = data["listing_encoder"]
                    logger.info("Recommendation model loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load recommendation model: {e}")
                self.model = None

    def save_model(self) -> None:
        """Save the trained model to disk."""
        try:
            os.makedirs("app/ml_models", exist_ok=True)
            with open(MODEL_PATH, "wb") as f:
                pickle.dump(
                    {
                        "model": self.model,
                        "user_encoder": self.user_encoder,
                        "listing_encoder": self.listing_encoder,
                    },
                    f,
                )
            logger.info("Recommendation model saved successfully")
        except Exception as e:
            logger.error(f"Failed to save recommendation model: {e}")

    def train(self, db: Session) -> bool:
        """Train collaborative filtering model on user behavior."""
        try:
            # Fetch all user-listing interactions from last 90 days
            ninety_days_ago = datetime.utcnow() - timedelta(days=90)
            behaviors = (
                db.query(UserBehavior)
                .filter(
                    and_(
                        UserBehavior.listing_id.isnot(None),
                        UserBehavior.timestamp >= ninety_days_ago,
                    )
                )
                .all()
            )

            if not behaviors:
                logger.warning("No user behavior data for recommendation training")
                return False

            # Build user-item matrix
            data = []
            for behavior in behaviors:
                weight = BEHAVIOR_WEIGHTS.get(behavior.behavior_type, 0)
                if weight != 0:
                    data.append(
                        {
                            "user_id": behavior.user_id,
                            "listing_id": behavior.listing_id,
                            "weight": weight,
                        }
                    )

            if not data:
                logger.warning("No weighted interactions for recommendation training")
                return False

            df = pd.DataFrame(data)

            # Get unique users and listings
            unique_users = df["user_id"].unique()
            unique_listings = df["listing_id"].unique()

            if len(unique_users) < MIN_USERS_FOR_CF:
                logger.warning(
                    f"Not enough users ({len(unique_users)}) for collaborative filtering"
                )
                return False

            # Create encoders
            self.user_encoder = {uid: idx for idx, uid in enumerate(unique_users)}
            self.listing_encoder = {lid: idx for idx, lid in enumerate(unique_listings)}

            reverse_user_encoder = {v: k for k, v in self.user_encoder.items()}
            reverse_listing_encoder = {v: k for k, v in self.listing_encoder.items()}

            # Build user-item matrix
            user_indices = df["user_id"].map(self.user_encoder)
            listing_indices = df["listing_id"].map(self.listing_encoder)

            matrix = np.zeros(
                (len(self.user_encoder), len(self.listing_encoder))
            )
            for user_idx, listing_idx, weight in zip(
                user_indices, listing_indices, df["weight"]
            ):
                matrix[user_idx, listing_idx] += weight

            # Train SVD
            self.model = TruncatedSVD(
                n_components=min(10, len(self.user_encoder) - 1),
                random_state=42,
            )
            self.model.fit(matrix)

            self.save_model()
            logger.info(
                f"Recommendation model trained on {len(unique_users)} users and {len(unique_listings)} listings"
            )
            return True

        except Exception as e:
            logger.error(f"Error training recommendation model: {e}")
            return False

    def get_recommendations(self, user_id: int, db: Session) -> Dict:
        """
        Get top recommendations for a user.

        Returns:
            {
                top_10: [{listing_id, match_score, description}, ...],
                method: 'collaborative_filtering' or 'cold_start',
                user_profile: {...}
            }
        """
        try:
            # Get user profile
            profile = self.profile_agent.get_profile(user_id, db)

            # Check if we have model and user is in training set
            if self.model is not None and user_id in self.user_encoder:
                recommendations = self._cf_recommendations(user_id, db)
                method = "collaborative_filtering"
            else:
                recommendations = self._cold_start_recommendations(user_id, db)
                method = "cold_start"

            # Get LLM descriptions for recommendations
            if recommendations:
                recommendations = self._get_recommendations_descriptions(
                    recommendations, profile
                )

            return {
                "top_10": recommendations,
                "method": method,
                "user_profile": profile,
            }

        except Exception as e:
            logger.error(f"Error getting recommendations: {e}")
            return {
                "top_10": [],
                "method": "error",
                "user_profile": {},
            }

    def _cf_recommendations(
        self, user_id: int, db: Session
    ) -> List[Dict]:
        """Get recommendations using collaborative filtering."""
        try:
            user_idx = self.user_encoder.get(user_id)
            if user_idx is None:
                return []

            # Get all recommended listings
            all_listings = db.query(Listing.id).filter(
                Listing.is_active == True
            ).all()
            all_listing_ids = [l[0] for l in all_listings]

            # Get user's already saved/clicked listings
            user_behaviors = (
                db.query(UserBehavior.listing_id)
                .filter(
                    and_(
                        UserBehavior.user_id == user_id,
                        UserBehavior.behavior_type.in_(["save", "click"]),
                    )
                )
                .all()
            )
            interacted = set([b[0] for b in user_behaviors if b[0]])

            recommendations = []
            for listing_id in all_listing_ids:
                if listing_id in interacted:
                    continue

                if listing_id not in self.listing_encoder:
                    continue

                listing_idx = self.listing_encoder[listing_id]

                # Calculate similarity score
                score = self._calculate_similarity_score(
                    user_idx, listing_idx
                )

                recommendations.append(
                    {"listing_id": listing_id, "match_score": score}
                )

            # Sort by score and return top N
            recommendations.sort(
                key=lambda x: x["match_score"], reverse=True
            )
            return recommendations[:TOP_N]

        except Exception as e:
            logger.error(f"Error in CF recommendations: {e}")
            return []

    def _cold_start_recommendations(
        self, user_id: int, db: Session
    ) -> List[Dict]:
        """Get recommendations for new user (no behavior data)."""
        try:
            # Get high-scored listings
            listings = (
                db.query(
                    Listing.id,
                    Listing.lifestyle_score,
                    Listing.price_verdict,
                )
                .filter(Listing.is_active == True)
                .all()
            )

            recommendations = []
            for listing_id, lifestyle_score, price_verdict in listings:
                lifestyle = float(lifestyle_score) if lifestyle_score else 5.0
                price_score = (
                    10 if price_verdict == "fair"
                    else 5 if price_verdict == "underpriced"
                    else 0
                )

                total_score = lifestyle * 0.6 + price_score * 0.4
                recommendations.append(
                    {"listing_id": listing_id, "match_score": total_score}
                )

            # Sort and return top N
            recommendations.sort(
                key=lambda x: x["match_score"], reverse=True
            )
            return recommendations[:TOP_N]

        except Exception as e:
            logger.error(f"Error in cold-start recommendations: {e}")
            return []

    def _calculate_similarity_score(
        self, user_idx: int, listing_idx: int
    ) -> float:
        """Calculate similarity score using SVD model."""
        try:
            # Get user and listing latent factors
            U = self.model.components_.T  # (n_listings, n_components)
            
            if listing_idx >= U.shape[0]:
                return 0.0

            listing_vector = U[listing_idx]

            # Calculate score as dot product
            score = np.dot(listing_vector, listing_vector) * 5.0
            return float(min(10.0, max(0.0, score)))

        except Exception as e:
            logger.debug(f"Error calculating similarity: {e}")
            return 5.0

    def _get_recommendations_descriptions(
        self, recommendations: List[Dict], profile: Dict
    ) -> List[Dict]:
        """Get LLM descriptions for recommendations."""
        try:
            if not recommendations or not self.is_ollama_available():
                # Use default descriptions
                for rec in recommendations:
                    rec["description"] = "Recommended based on your profile and preferences"
                return recommendations

            # Prepare prompt for LLM
            listings_str = "\n".join(
                [f"- Listing {r['listing_id']}: score {r['match_score']:.1f}/10"
                 for r in recommendations]
            )

            prompt = f"""For each of the following properties, write a single short sentence
explaining why it matches this user profile. Be specific about scores.
Return only JSON, no extra text:
[{{listing_id: int, description: str}}]
User profile: {profile.get('cluster_label', 'balanced')} - {profile.get('description', '')}
Listings:
{listings_str}"""

            response = self.call_llm(prompt)
            if response:
                result = self.parse_json(response, [])
                if isinstance(result, list) and result:
                    # Map descriptions to recommendations
                    desc_map = {r["listing_id"]: r.get("description", "")
                                for r in result if "listing_id" in r}
                    for rec in recommendations:
                        rec["description"] = desc_map.get(
                            rec["listing_id"],
                            "Recommended based on your profile"
                        )
                    return recommendations

        except Exception as e:
            logger.debug(f"Error getting LLM descriptions: {e}")

        # Fallback descriptions
        for rec in recommendations:
            rec["description"] = "Recommended based on your profile"
        return recommendations
