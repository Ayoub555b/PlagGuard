"""Prétraitement : normalisation, ponctuation, stop words (français)."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Set

# Stop words français (liste réduite mais représentative ; extensible)
_STOP_WORDS_FR: Set[str] = {
    "a", "ai", "aie", "aient", "ais", "ait", "alors", "as", "au", "aucun", "aura", "aurait", "aux",
    "avec", "avoir", "c", "ce", "ceci", "cela", "celle", "celles", "celui", "cependant", "ces", "cet",
    "cette", "ceux", "chez", "comme", "comment", "d", "dans", "de", "dedans", "dehors", "depuis", "des",
    "deux", "devoir", "doit", "donc", "dont", "du", "durant", "elle", "elles", "en", "encore", "entre",
    "es", "est", "et", "eu", "eue", "eues", "eurent", "eus", "eusse", "eussent", "eusses", "eut", "eux",
    "furent", "fus", "fut", "fût", "hormis", "hors", "ici", "il", "ils", "j", "je", "jusqu", "l", "la",
    "le", "les", "leur", "leurs", "lui", "là", "m", "ma", "mais", "me", "mes", "moi", "moins", "mon",
    "même", "n", "ne", "ni", "non", "nos", "notre", "nous", "on", "ont", "ou", "où", "par", "parmi",
    "pas", "pendant", "peu", "peut", "plus", "plusieurs", "pour", "pourquoi", "pouvoir", "qu", "que",
    "quel", "quelle", "quelles", "quels", "qui", "quoi", "s", "sa", "sans", "se", "sera", "serait", "ses",
    "si", "sinon", "soi", "soit", "sommes", "son", "sont", "sous", "soyez", "suis", "sur", "t", "ta",
    "te", "tes", "toi", "ton", "tous", "tout", "toute", "toutes", "tu", "un", "une", "unes", "uns", "vers",
    "voici", "voilà", "vos", "votre", "vous", "y", "à", "ça", "été", "être",
}


def normalize_text(text: str) -> str:
    """Minuscules, suppression accents pour comparaison stable."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def tokenize(text: str) -> List[str]:
    """Découpe en mots (lettres/chiffres), après normalisation."""
    t = normalize_text(text)
    return re.findall(r"[a-z0-9àâäéèêëïîôùûüçœæ]{2,}", t)


def remove_stopwords(tokens: Iterable[str]) -> List[str]:
    return [w for w in tokens if w not in _STOP_WORDS_FR]


def preprocess_for_similarity(text: str) -> List[str]:
    """Tokens utiles pour Jaccard / n-grams (sans stop words)."""
    return remove_stopwords(tokenize(text))


def word_ngrams(tokens: List[str], n: int) -> List[str]:
    """N-grams de mots (chaînes séparées par espace, pour requêtes web)."""
    if len(tokens) < n:
        if tokens:
            return [" ".join(tokens)]
        return []
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def pick_search_queries(tokens: List[str], n: int = 5, max_queries: int = 4) -> List[str]:
    """
    Choisit quelques n-grams représentatifs à différents endroits du document
    pour interroger Tavily Search.
    """
    grams = word_ngrams(tokens, n)
    if not grams:
        return []
    L = len(grams)
    indices = [0]
    if L > 1:
        indices.append(L // 4)
    if L > 2:
        indices.append(L // 2)
    if L > 3:
        indices.append((3 * L) // 4)
    seen = set()
    out: List[str] = []
    for i in indices:
        g = grams[min(i, L - 1)]
        if g not in seen and len(g) >= 8:
            seen.add(g)
            out.append(g)
        if len(out) >= max_queries:
            break
    for g in grams:
        if len(out) >= max_queries:
            break
        if g not in seen and len(g) >= 10:
            seen.add(g)
            out.append(g)
    return out[:max_queries]
