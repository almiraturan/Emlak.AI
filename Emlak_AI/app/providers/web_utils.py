from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def fetch_text(url: str, timeout_seconds: int = 20) -> str:
    req = urllib.request.Request(url=url, headers=DEFAULT_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="ignore")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Source request failed with HTTP {exc.code} for url={url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Source request failed for url={url}: {exc.reason}") from exc


def _extract_next_data_blocks(html: str) -> list[str]:
    return re.findall(
        r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _extract_preloaded_state_blocks(html: str) -> list[str]:
    return re.findall(
        r"window\.__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _extract_json_ld_blocks(html: str) -> list[str]:
    return re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )


def extract_json_blocks(html: str) -> list[dict[str, Any] | list[Any]]:
    parsed_blocks: list[dict[str, Any] | list[Any]] = []
    raw_blocks = [
        *_extract_next_data_blocks(html),
        *_extract_preloaded_state_blocks(html),
        *_extract_json_ld_blocks(html),
    ]

    for block in raw_blocks:
        stripped = block.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, (dict, list)):
                parsed_blocks.append(parsed)
        except json.JSONDecodeError:
            continue

    return parsed_blocks


def walk_dict_candidates(node: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            candidates.append(value)
            for child in value.values():
                _walk(child)
        elif isinstance(value, list):
            for child in value:
                _walk(child)

    _walk(node)
    return candidates


def first_present(mapping: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) not in (None, ""):
            return mapping.get(key)
    return None


def to_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
