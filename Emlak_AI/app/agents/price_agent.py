"""Price Analysis Engine using XGBoost Regression."""
import os
import pickle
import logging
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.preprocessing import LabelEncoder
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.models.listing import Listing

logger = logging.getLogger(__name__)

MODEL_PATH = "app/ml_models/price_xgboost.pkl"
MIN_LISTINGS = 10  # Minimum listings for model training


class PriceAgent(BaseAgent):
    """Price Analysis Engine using XGBoost."""

    def __init__(self):
        """Initialize the agent."""
        super().__init__()
        self.model = None
        self.district_encoder = None
        self.load_model()

    def load_model(self) -> None:
        """Load the trained model from disk if it exists."""
        if os.path.exists(MODEL_PATH):
            try:
                with open(MODEL_PATH, "rb") as f:
                    data = pickle.load(f)
                    self.model = data["model"]
                    self.district_encoder = data["encoder"]
                    logger.info("Price model loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load price model: {e}")
                self.model = None
                self.district_encoder = None

    def save_model(self) -> None:
        """Save the trained model to disk."""
        try:
            os.makedirs("app/ml_models", exist_ok=True)
            with open(MODEL_PATH, "wb") as f:
                pickle.dump(
                    {"model": self.model, "encoder": self.district_encoder}, f
                )
            logger.info("Price model saved successfully")
        except Exception as e:
            logger.error(f"Failed to save price model: {e}")

    def train(self, db: Session) -> bool:
        """Train XGBoost model on listing data."""
        try:
            # Fetch active listings with required features
            listings = (
                db.query(Listing)
                .filter(
                    and_(
                        Listing.is_active == True,
                        Listing.area_m2.isnot(None),
                        Listing.room_count_total.isnot(None),
                        Listing.district.isnot(None),
                        Listing.price.isnot(None),
                    )
                )
                .all()
            )

            if len(listings) < MIN_LISTINGS:
                logger.warning(
                    f"Not enough listings ({len(listings)}) for price model training"
                )
                return False

            # Build dataframe
            data = []
            for listing in listings:
                data.append(
                    {
                        "area_m2": float(listing.area_m2),
                        "room_count_total": listing.room_count_total,
                        "district": listing.district,
                        "floor": listing.floor if listing.floor else 1,
                        "age": self._get_age(listing.building_age),
                        "price": float(listing.price),
                    }
                )

            df = pd.DataFrame(data)

            # Encode district
            self.district_encoder = LabelEncoder()
            df["district_encoded"] = self.district_encoder.fit_transform(
                df["district"]
            )

            # Features and target
            X = df[["area_m2", "room_count_total", "district_encoded", "floor", "age"]]
            y = df["price"]

            # Train/test split
            split_idx = int(len(X) * 0.8)
            X_train, X_test = X[:split_idx], X[split_idx:]
            y_train, y_test = y[:split_idx], y[split_idx:]

            # Train XGBoost
            self.model = xgb.XGBRegressor(
                n_estimators=50,
                max_depth=5,
                learning_rate=0.1,
                random_state=42,
            )
            self.model.fit(
                X_train, y_train, eval_set=[(X_test, y_test)], verbose=False
            )

            self.save_model()
            logger.info(f"Price model trained on {len(listings)} listings")
            return True

        except Exception as e:
            logger.error(f"Error training price model: {e}")
            return False

    def analyze_price(self, listing_id: int, db: Session) -> Dict:
        """
        Analyze price of a listing.

        Returns:
            {
                predicted_price,
                actual_price,
                verdict (overpriced/fair/underpriced),
                difference_pct,
                description
            }
        """
        try:
            listing = db.query(Listing).filter(Listing.id == listing_id).first()

            if not listing or listing.price is None:
                return {
                    "predicted_price": None,
                    "actual_price": None,
                    "verdict": "unknown",
                    "difference_pct": 0,
                    "description": "Listing not found or no price available",
                }

            actual_price = float(listing.price)

            # If model not trained, use fallback
            if self.model is None or listing.area_m2 is None:
                return self._fallback_analysis(listing, actual_price, db)

            # Prepare features
            try:
                district_encoded = self.district_encoder.transform([listing.district])[0]
            except ValueError:
                # District not in training data
                return self._fallback_analysis(listing, actual_price, db)

            features = pd.DataFrame(
                {
                    "area_m2": [float(listing.area_m2)],
                    "room_count_total": [listing.room_count_total],
                    "district_encoded": [district_encoded],
                    "floor": [listing.floor if listing.floor else 1],
                    "age": [self._get_age(listing.building_age)],
                }
            )

            # Predict price
            predicted_price = float(self.model.predict(features)[0])

            # Calculate verdict
            verdict, difference_pct = self._get_verdict(
                actual_price, predicted_price
            )

            description = f"Predicted: {predicted_price:.0f} TRY, Actual: {actual_price:.0f} TRY"

            return {
                "predicted_price": predicted_price,
                "actual_price": actual_price,
                "verdict": verdict,
                "difference_pct": difference_pct,
                "description": description,
            }

        except Exception as e:
            logger.error(f"Error analyzing price: {e}")
            return {
                "predicted_price": None,
                "actual_price": None,
                "verdict": "error",
                "difference_pct": 0,
                "description": "Error analyzing price",
            }

    def _fallback_analysis(
        self, listing: Listing, actual_price: float, db: Session
    ) -> Dict:
        """Use median-based fallback analysis."""
        try:
            # Get median price for similar listings (same district, similar area)
            similar = (
                db.query(Listing.price)
                .filter(
                    and_(
                        Listing.district == listing.district,
                        Listing.area_m2.isnot(None),
                        Listing.price.isnot(None),
                        Listing.is_active == True,
                    )
                )
                .all()
            )

            if not similar:
                return {
                    "predicted_price": actual_price,
                    "actual_price": actual_price,
                    "verdict": "fair",
                    "difference_pct": 0,
                    "description": "No comparables available",
                }

            prices = [float(p[0]) for p in similar]
            median_price = float(np.median(prices))

            verdict, difference_pct = self._get_verdict(actual_price, median_price)

            return {
                "predicted_price": median_price,
                "actual_price": actual_price,
                "verdict": verdict,
                "difference_pct": difference_pct,
                "description": f"Based on {len(prices)} similar properties",
            }

        except Exception as e:
            logger.error(f"Error in fallback analysis: {e}")
            return {
                "predicted_price": actual_price,
                "actual_price": actual_price,
                "verdict": "fair",
                "difference_pct": 0,
                "description": "Error in price analysis",
            }

    def _get_verdict(
        self, actual: float, predicted: float
    ) -> Tuple[str, float]:
        """Determine verdict and percentage difference."""
        if predicted == 0:
            return "fair", 0.0

        difference_pct = ((actual - predicted) / predicted) * 100

        if actual > predicted * 1.10:
            verdict = "overpriced"
        elif actual < predicted * 0.90:
            verdict = "underpriced"
        else:
            verdict = "fair"

        return verdict, difference_pct

    def _get_age(self, building_age: Optional[int]) -> int:
        """Calculate building age in years."""
        if building_age is None:
            return 10  # default

        return min(building_age, 100)  # cap at 100 years
