"""Extraction de texte lisible depuis une page web (HTTP + fallback navigateur)."""

from __future__ import annotations

import re
from typing import Optional

import requests


def fetch_page_text(url: str, max_bytes: int = 400_000, timeout: int = 12) -> Optional[str]:
    """
    Télécharge l'URL et extrait le texte visible (script/style supprimés).
    Retourne None en cas d'échec.
    """
    try:
        headers = {
            "User-Agent": "PlagGuard/1.0 (analyse académique; +https://localhost)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=timeout, stream=True)
        r.raise_for_status()
        raw = b""
        for chunk in r.iter_content(chunk_size=65536):
            raw += chunk
            if len(raw) >= max_bytes:
                break
        html = raw.decode(r.encoding or "utf-8", errors="ignore")
        return html_to_text(html)
    except Exception:
        return None


def fetch_page_text_robust(url: str, max_bytes: int = 400_000, timeout: int = 12) -> tuple[Optional[str], str, float]:
    """
    Extraction robuste avec score de confiance.
    Retourne: (texte, methode, confiance[0..1]).
    """
    text = fetch_page_text(url, max_bytes=max_bytes, timeout=timeout)
    if text and len(text.strip()) >= 120:
        return text, "requests_html", 0.85

    rendered = _fetch_with_playwright(url, timeout=timeout)
    if rendered and len(rendered.strip()) >= 120:
        return rendered, "playwright_render", 0.95

    if text and len(text.strip()) >= 40:
        return text, "requests_html_short", 0.5
    return None, "failed", 0.0


def _fetch_with_playwright(url: str, timeout: int = 12) -> Optional[str]:
    """
    Fallback JS dynamique.
    Nécessite: pip install playwright + python -m playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=int(timeout * 1000))
            html = page.content()
            browser.close()
            return html_to_text(html)
    except Exception:
        return None


def html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
