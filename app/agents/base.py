"""Base agent class with Ollama LLM integration."""
import json
import os
import re
import time
from typing import Any, Dict, Optional
import httpx
import logging

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
LLM_TIMEOUT = 60  # seconds
LLM_RETRIES = 3
LLM_RETRY_DELAY = 2  # seconds


class BaseAgent:
    """Base class for all AI agents with Ollama integration."""

    def __init__(self):
        """Initialize the agent."""
        self.model = OLLAMA_MODEL
        self.base_url = OLLAMA_BASE_URL

    def is_ollama_available(self) -> bool:
        """Check if Ollama service is available."""
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Ollama check failed: {e}")
            return False

    def call_llm(self, prompt: str, fallback: Optional[str] = None) -> Optional[str]:
        """
        Call Ollama LLM with retry logic.

        Args:
            prompt: The prompt to send to the LLM
            fallback: Fallback value if LLM call fails

        Returns:
            LLM response text or fallback value
        """
        if not self.is_ollama_available():
            logger.debug("Ollama not available, using fallback")
            return fallback

        for attempt in range(LLM_RETRIES):
            try:
                with httpx.Client(timeout=LLM_TIMEOUT) as client:
                    response = client.post(
                        f"{self.base_url}/api/generate",
                        json={
                            "model": self.model,
                            "prompt": prompt,
                            "stream": False,
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                    return result.get("response", fallback)
            except Exception as e:
                logger.debug(f"LLM call attempt {attempt + 1} failed: {e}")
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
