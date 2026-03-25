"""Fingerprinting textuel (n-grams + hashes) pour renforcer la similarité."""

from __future__ import annotations

import hashlib
from typing import Iterable, List, Set


def _stable_hash(token: str) -> int:
    h = hashlib.sha1(token.encode("utf-8", errors="ignore")).hexdigest()
    return int(h[:12], 16)


def _word_shingles(tokens: List[str], n: int) -> List[str]:
    if not tokens:
        return []
    if len(tokens) < n:
        return [" ".join(tokens)]
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def fingerprint_hashes(tokens: Iterable[str], ngram_size: int = 5, window_size: int = 4) -> Set[int]:
    """
    Construit des fingerprints via la logique de "winnowing" :
    - n-grams de mots
    - hash de chaque n-gram
    - minimum glissant sur une fenêtre
    """
    toks = list(tokens)
    shingles = _word_shingles(toks, ngram_size)
    if not shingles:
        return set()

    hashes = [_stable_hash(s) for s in shingles]
    if window_size <= 1 or len(hashes) <= window_size:
        return set(hashes)

    picks: Set[int] = set()
    for i in range(0, len(hashes) - window_size + 1):
        window = hashes[i : i + window_size]
        picks.add(min(window))
    return picks


def fingerprint_similarity(tokens_a: Iterable[str], tokens_b: Iterable[str]) -> float:
    """Jaccard entre ensembles de fingerprints."""
    fa = fingerprint_hashes(tokens_a)
    fb = fingerprint_hashes(tokens_b)
    if not fa and not fb:
        return 0.0
    union = fa | fb
    if not union:
        return 0.0
    return len(fa & fb) / len(union)


def fingerprint_containment(doc_tokens: Iterable[str], source_tokens: Iterable[str]) -> float:
    """
    Mesure de couverture du document par la source :
    |FP(doc) ∩ FP(source)| / |FP(doc)|
    Très utile quand le texte soumis est copié depuis une source plus grande.
    """
    fd = fingerprint_hashes(doc_tokens)
    fs = fingerprint_hashes(source_tokens)
    if not fd:
        return 0.0
    return len(fd & fs) / len(fd)

