"""Base agent class with Google Gemini LLM integration and Ollama fallback."""
import json
import re
import time
import urllib.request
from typing import Any, Dict, Optional
import logging

import google.generativeai as genai

from app.core.config import settings

logger = logging.getLogger(__name__)

LLM_RETRIES = 2
LLM_RETRY_DELAY = 1  # seconds

# Module-level cache: (result, checked_at_epoch)
_llm_available_cache: tuple[bool, float] = (False, 0.0)
_LLM_CACHE_TTL = 120  # seconds

# Ollama fallback config
_OLLAMA_URL = "http://ollama:11434"
_OLLAMA_MODEL = "gemma3:1b"

# Cache whether Gemini is currently quota-blocked (reset after TTL)
_gemini_quota_blocked: tuple[bool, float] = (False, 0.0)
_QUOTA_BLOCK_TTL = 300  # re-check Gemini after 5 min


def _call_ollama(prompt: str, timeout: int = 60) -> Optional[str]:
    """Call local Ollama as LLM fallback."""
    try:
        payload = json.dumps({
            "model": _OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{_OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()).get("response", "").strip() or None
    except Exception as e:
        logger.debug(f"Ollama fallback failed: {e}")
        return None


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
        """Check if Gemini LLM is available (cached for 120 s to avoid per-call network hits)."""
        global _llm_available_cache
        result, checked_at = _llm_available_cache
        if time.time() - checked_at < _LLM_CACHE_TTL:
            return result
        try:
            if not settings.gemini_api_key:
                _llm_available_cache = (False, time.time())
                return False
            models = genai.list_models()
            available = any(self.model_name in m.name for m in models)
            _llm_available_cache = (available, time.time())
            return available
        except Exception as e:
            logger.debug(f"Gemini availability check failed: {e}")
            _llm_available_cache = (False, time.time())
            return False

    def call_llm(self, prompt: str, fallback: Optional[str] = None) -> Optional[str]:
        """Call Gemini LLM; fall back to local Ollama on quota errors."""
        global _gemini_quota_blocked

        blocked, blocked_at = _gemini_quota_blocked
        gemini_skip = blocked and (time.time() - blocked_at < _QUOTA_BLOCK_TTL)

        if settings.gemini_api_key and not gemini_skip:
            for attempt in range(LLM_RETRIES):
                try:
                    model = genai.GenerativeModel(self.model_name)
                    response = model.generate_content(prompt)
                    # Successful call — clear quota block
                    _gemini_quota_blocked = (False, 0.0)
                    return response.text if response.text else fallback
                except Exception as e:
                    err = str(e)
                    if "429" in err or "quota" in err.lower() or "RESOURCE_EXHAUSTED" in err:
                        logger.warning("Gemini quota exhausted — switching to Ollama for %ds", _QUOTA_BLOCK_TTL)
                        _gemini_quota_blocked = (True, time.time())
                        break
                    logger.debug(f"Gemini call attempt {attempt + 1} failed: {e}")
                    if attempt < LLM_RETRIES - 1:
                        time.sleep(LLM_RETRY_DELAY)
                    else:
                        return fallback

        # Ollama fallback
        result = _call_ollama(prompt, timeout=60)
        if result:
            return result
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
