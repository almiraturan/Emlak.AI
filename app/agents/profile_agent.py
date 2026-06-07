"""Profile Learning Engine using K-Means Clustering."""
import os
import pickle
import logging
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.models.user_behavior import UserBehavior
from app.models.listing import Listing

logger = logging.getLogger(__name__)

MODEL_PATH = "app/ml_models/profile_kmeans.pkl"
CLUSTER_LABELS = {
    0: "budget_conscious",
    1: "luxury_seeker",
    2: "location_first",
    3: "balanced",
}


class ProfileAgent(BaseAgent):
    """Profile Learning Engine that clusters users based on behavior."""

    def __init__(self):
        """Initialize the agent."""
        super().__init__()
        self.model = None
        self.scaler = None
        self.load_model()

    def load_model(self) -> None:
        """Load the trained model from disk if it exists."""
        if os.path.exists(MODEL_PATH):
            try:
                with open(MODEL_PATH, "rb") as f:
                    data = pickle.load(f)
                    self.model = data["model"]
                    self.scaler = data["scaler"]
                    logger.info("Profile model loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load profile model: {e}")
                self.model = None
                self.scaler = None

    def save_model(self) -> None:
        """Save the trained model to disk."""
        try:
            os.makedirs("app/ml_models", exist_ok=True)
            with open(MODEL_PATH, "wb") as f:
                pickle.dump({"model": self.model, "scaler": self.scaler}, f)
            logger.info("Profile model saved successfully")
        except Exception as e:
            logger.error(f"Failed to save profile model: {e}")

    def build_feature_vector(
        self, behaviors: list, listing_prices: list
    ) -> Tuple[np.ndarray, Dict]:
        """
        Build feature vector from user behavior.

        Features:
        - avg_saved_price: Average price of saved listings
        - avg_clicked_rooms: Average room count of clicked listings
        - skip_rate: Percentage of skip events
        - save_rate: Percentage of save events
        - search_budget_avg: Average search budget (from search metadata)
        """
        if not behaviors:
            return np.array([0, 0, 0, 0, 0]), {
                "total_events": 0,
                "click_count": 0,
                "save_count": 0,
                "skip_count": 0,
                "search_count": 0,
                "avg_saved_price": 0,
                "skip_rate": 0,
                "save_rate": 0,
            }

        df = pd.DataFrame(
            [
                {
                    "type": b.behavior_type,
                    "price": listing_prices.get(b.listing_id, 0),
                    "rooms": 1,  # Would need to fetch from listing
                }
                for b in behaviors
            ]
        )

        total_events = len(df)
        save_events = len(df[df["type"] == "save"])
        skip_events = len(df[df["type"] == "skip"])
        click_events = len(df[df["type"] == "click"])
        search_events = len(df[df["type"] == "search"])

        saved_prices = df[df["type"] == "save"]["price"].values
        avg_saved_price = float(np.mean(saved_prices)) if len(saved_prices) > 0 else 0

        save_rate = (save_events / total_events) if total_events > 0 else 0
        skip_rate = (skip_events / total_events) if total_events > 0 else 0

        feature_vector = np.array(
            [
                avg_saved_price / 1000 if avg_saved_price > 0 else 0,  # normalize
                1.0,  # avg_clicked_rooms placeholder
                skip_rate,
                save_rate,
                0.5,  # search_budget_avg placeholder
            ]
        )

        return feature_vector, {
            "total_events": int(total_events),
            "click_count": int(click_events),
            "save_count": int(save_events),
            "skip_count": int(skip_events),
            "search_count": int(search_events),
            "avg_saved_price": avg_saved_price,
            "skip_rate": skip_rate,
            "save_rate": save_rate,
        }

    def train(self, db: Session) -> bool:
        """Train K-Means model on user behavior data."""
        try:
            # Fetch all user behaviors
            behaviors_data = []

            # Group by user
            users = (
                db.query(UserBehavior.user_id).distinct().all()
            )

            if len(users) < 4:  # Not enough data for 4 clusters
                logger.warning("Not enough users for profile clustering")
                return False

            # Get all listing prices for normalization
            listing_prices = {}
            listings = db.query(Listing.id, Listing.price).all()
            for lid, price in listings:
                listing_prices[lid] = float(price)

            # Build feature vectors for each user
            X = []
            for (user_id,) in users:
                user_behaviors = (
                    db.query(UserBehavior)
                    .filter(UserBehavior.user_id == user_id)
                    .all()
                )

                features, _ = self.build_feature_vector(
                    user_behaviors, listing_prices
                )
                X.append(features)

            X = np.array(X)

            # Train K-Means
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X)

            self.model = KMeans(n_clusters=4, random_state=42, n_init=10)
            self.model.fit(X_scaled)

            self.save_model()
            logger.info(f"Profile model trained on {len(users)} users")
            return True

        except Exception as e:
            logger.error(f"Error training profile model: {e}")
            return False

    def get_profile(
        self, user_id: int, db: Session
    ) -> Dict:
        """Get user profile with cluster assignment."""
        try:
            # Fetch user behaviors from last 30 days
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            behaviors = (
                db.query(UserBehavior)
                .filter(
                    UserBehavior.user_id == user_id,
                    UserBehavior.timestamp >= thirty_days_ago,
                )
                .all()
            )

            # Get listing prices
            listing_prices = {}
            if behaviors:
                listing_ids = [b.listing_id for b in behaviors if b.listing_id]
                if listing_ids:
                    listings = (
                        db.query(Listing.id, Listing.price)
                        .filter(Listing.id.in_(listing_ids))
                        .all()
                    )
                    for lid, price in listings:
                        listing_prices[lid] = float(price)

            features, metadata = self.build_feature_vector(
                behaviors, listing_prices
            )

            # If no trained model, fall back to a simple rule-based cluster
            # using the metadata we just computed so the UI still shows data.
            if self.model is None:
                cluster = self._heuristic_cluster(metadata)
                return {
                    "cluster": cluster,
                    "cluster_label": CLUSTER_LABELS.get(cluster, "balanced"),
                    "feature_vector": features.tolist(),
                    "description": self._get_profile_description(cluster, metadata),
                    "metadata": metadata,
                }

            if len(behaviors) == 0:
                return {
                    "cluster": 3,
                    "cluster_label": "balanced",
                    "feature_vector": [0, 0, 0, 0, 0],
                    "description": "Henuz etkilesim yok — varsayilan dengeli profil",
                    "metadata": metadata,
                }

            # Assign to cluster
            features_scaled = self.scaler.transform([features])[0]
            cluster = int(self.model.predict([features_scaled])[0])

            # Get LLM description if available
            description = self._get_profile_description(
                cluster, metadata
            )

            return {
                "cluster": cluster,
                "cluster_label": CLUSTER_LABELS.get(cluster, "unknown"),
                "feature_vector": features.tolist(),
                "description": description,
                "metadata": metadata,
            }

        except Exception as e:
            logger.error(f"Error getting profile for user {user_id}: {e}")
            return {
                "cluster": 3,
                "cluster_label": "balanced",
                "feature_vector": [0, 0, 0, 0, 0],
                "description": "Error determining profile",
                "metadata": {},
            }

    def _heuristic_cluster(self, metadata: Dict) -> int:
        """Pick a cluster from metadata when no trained model is available."""
        avg_saved = metadata.get("avg_saved_price", 0) or 0
        save_rate = metadata.get("save_rate", 0) or 0
        skip_rate = metadata.get("skip_rate", 0) or 0
        if avg_saved >= 5_000_000:
            return 1  # luxury_seeker
        if save_rate >= 0.4 and avg_saved and avg_saved <= 3_000_000:
            return 0  # budget_conscious
        if skip_rate >= 0.4:
            return 2  # location_first
        return 3  # balanced

    def _get_profile_description(
        self, cluster: int, metadata: Dict
    ) -> str:
        """Get description from LLM or use rule-based description."""
        if cluster == 0:
            return "Budget-conscious buyer: prioritizes price and value"
        elif cluster == 1:
            return "Luxury seeker: focuses on premium properties"
        elif cluster == 2:
            return "Location-first buyer: prioritizes neighborhood"
        else:
            return "Balanced buyer: considers all factors equally"
