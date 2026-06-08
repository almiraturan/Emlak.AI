"""Base agent class with Google Gemini LLM integration."""
import json
import os
import re
import time
from typing import Any, Dict, Optional
import logging

import google.generativeai as genai

from app.core.config import settings

logger = logging.getLogger(__name__)

LLM_RETRIES = 3
LLM_RETRY_DELAY = 2  # seconds


class BaseAgent:
    """Base class for all AI agents with Google Gemini integration."""

    def __init__(self):
        """Initialize the agent."""
        self.model_name = settings.gemini_model
        self.timeout = settings.llm_timeout_seconds
        
        # Configure Gemini API
        if settings.gemini_api_key:
            genai.configure(api_key=settings.gemini_api_key)
        else:
            logger.warning("GEMINI_API_KEY not configured")

    def is_llm_available(self) -> bool:
        """Check if Gemini LLM is available."""
        try:
            if not settings.gemini_api_key:
                return False
            # Try to list models to verify API key works
            models = genai.list_models()
            return any(self.model_name in m.name for m in models)
        except Exception as e:
            logger.debug(f"Gemini availability check failed: {e}")
            return False

    def call_llm(self, prompt: str, fallback: Optional[str] = None) -> Optional[str]:
        """
        Call Google Gemini LLM with retry logic.

        Args:
            prompt: The prompt to send to the LLM
            fallback: Fallback value if LLM call fails

        Returns:
            LLM response text or fallback value
        """
        if not settings.gemini_api_key:
            logger.debug("Gemini API key not configured, using fallback")
            return fallback

        for attempt in range(LLM_RETRIES):
            try:
                model = genai.GenerativeModel(self.model_name)
                response = model.generate_content(prompt)
                return response.text if response.text else fallback
            except Exception as e:
                logger.debug(f"Gemini call attempt {attempt + 1} failed: {e}")
                if attempt < LLM_RETRIES - 1:
                    time.sleep(LLM_RETRY_DELAY)
                else:
                    return fallback

        return fallback

    def parse_json(
        self, text: str, fallback: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Parse JSON from text, handling markdown code blocks.

        Args:
            text: Text potentially containing JSON
            fallback: Fallback value if parsing fails

        Returns:
            Parsed JSON dict or fallback
        """
        if fallback is None:
            fallback = {}

        try:
            # Strip markdown code blocks
            cleaned = re.sub(r"```json\s*", "", text)
            cleaned = re.sub(r"```\s*", "", cleaned)
            cleaned = cleaned.strip()

            # Try to parse JSON
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.debug(f"JSON parse error: {e}. Using fallback.")
            return fallback
        except Exception as e:
            logger.debug(f"Unexpected parse error: {e}. Using fallback.")
            return fallback
