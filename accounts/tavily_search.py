"""Client Tavily Search API (recherche web pour agents / LLM)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests
from django.conf import settings


TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def tavily_web_search(
    query: str,
    max_results: int = 10,
    include_domains: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Interroge l'API Tavily Search (POST /search).
    Retourne une liste de dicts : title, url, description (content Tavily).
    """
    key = getattr(settings, "TAVILY_API_KEY", "") or ""
    key = key.strip()
    if not key:
        raise ValueError(
            "Clé API Tavily absente. Définissez TAVILY_API_KEY dans l'environnement "
            "ou dans settings (voir .env.example)."
        )

    max_results = max(1, min(int(max_results), 20))
    payload = {
        "api_key": key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "topic": "general",
        "include_answer": False,
    }
    if include_domains:
        payload["include_domains"] = include_domains[:300]

    response = requests.post(
        TAVILY_SEARCH_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    results = data.get("results") or []
    out: list[dict[str, Any]] = []
    for item in results:
        url = (item.get("url") or "").strip()
        if not url or not _is_http_url(url):
            continue
        content = (item.get("content") or item.get("snippet") or "")[:5000]
        out.append(
            {
                "title": (item.get("title") or "Sans titre")[:500],
                "url": url[:1024],
                "description": content,
            }
        )
    return out


def _is_http_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False
