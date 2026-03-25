"""Jaccard, TF-IDF et similarité cosinus entre deux textes."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Set


def jaccard_similarity_words(tokens_a: list[str], tokens_b: list[str]) -> float:
    """Similarité de Jaccard sur les ensembles de mots (déjà prétraités)."""
    sa: Set[str] = set(tokens_a)
    sb: Set[str] = set(tokens_b)
    if not sa and not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def cosine_similarity_tfidf(text_a: str, text_b: str) -> float:
    """
    TF-IDF + similarité cosinus entre deux documents (texte brut ou prétraité).
    Si scikit-learn est indisponible, fallback sur cosinus bag-of-words.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ModuleNotFoundError:
        return _cosine_similarity_bow(text_a, text_b)

    ta = (text_a or "").strip()
    tb = (text_b or "").strip()
    if not ta or not tb:
        return 0.0

    ta = ta[:50_000]
    tb = tb[:50_000]
    try:
        vectorizer = TfidfVectorizer(
            max_features=8000,
            ngram_range=(1, 2),
            strip_accents="unicode",
            lowercase=True,
            token_pattern=r"(?u)\b\w\w+\b",
            min_df=1,
        )
        mat = vectorizer.fit_transform([ta, tb])
        sim = cosine_similarity(mat[0:1], mat[1:2])[0, 0]
        return float(max(0.0, min(1.0, sim)))
    except ValueError:
        return 0.0


def _cosine_similarity_bow(text_a: str, text_b: str) -> float:
    ta = (text_a or "").lower()
    tb = (text_b or "").lower()
    toks_a = re.findall(r"\b\w\w+\b", ta)
    toks_b = re.findall(r"\b\w\w+\b", tb)
    if not toks_a or not toks_b:
        return 0.0

    ca = Counter(toks_a)
    cb = Counter(toks_b)
    common = set(ca) & set(cb)
    dot = sum(ca[t] * cb[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in ca.values()))
    norm_b = math.sqrt(sum(v * v for v in cb.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    sim = dot / (norm_a * norm_b)
    return float(max(0.0, min(1.0, sim)))


def combined_similarity_score(
    tokens_doc: list[str],
    tokens_source: list[str],
    raw_doc: str,
    raw_source: str,
    weight_jaccard: float = 0.35,
    weight_cosine: float = 0.65,
) -> tuple[float, float, float]:
    """Retourne (jaccard, cosinus, score combiné 0..1)."""
    j = jaccard_similarity_words(tokens_doc, tokens_source)
    c = cosine_similarity_tfidf(raw_doc, raw_source)
    combined = weight_jaccard * j + weight_cosine * c
    return j, c, max(0.0, min(1.0, combined))
