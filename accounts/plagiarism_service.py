"""
Pipeline : N-grams → Tavily Search (et/ou URLs utilisateur) → extraction web →
Jaccard + TF-IDF + cosinus → enregistrement DOCUMENT, SOURCE_COMPARAISON, ANALYSE, etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import html_text, tavily_search, text_preprocessing
from .fingerprinting import fingerprint_containment, fingerprint_similarity
from .models import Analyse, Document, PassagePlagie, ResultatSimilarite, SourceComparaison, Utilisateur
from .similarity_algorithms import (
    combined_similarity_score,
    cosine_similarity_tfidf,
    jaccard_similarity_words,
)

# Seuil minimal de mots pour une analyse fiable (aligné sur les outils courants).
MIN_WORDS_FOR_ANALYSIS = 80
# Limite maximale côté interface (cohérente avec la page d'accueil).
MAX_WORDS_FOR_ANALYSIS = 500

# Seuils stricts pour limiter les faux positifs (pages peu liées au texte).
# Un score global trop bas ne doit pas afficher de « sources » forcées.
MIN_SOURCE_MATCH_PCT = 24.0
# Correspond au filtre d’affichage du rapport (passages surlignés).
MIN_PASSAGE_STRENGTH = 0.25  # max(Jaccard, cosinus phrase) sur [0, 1]
PASSAGE_MIN_JACCARD = 0.24
PASSAGE_MIN_COSINE = 0.30


def _count_words(text: str) -> int:
    return len((text or "").split())


@dataclass
class SourceCandidate:
    url: str
    title: str
    snippet: str
    origin: str  # "TAVILY" | "UTILISATEUR"


def parse_user_urls(urls_block: str) -> list[str]:
    lines = (urls_block or "").strip().splitlines()
    out: list[str] = []
    for line in lines:
        u = line.strip()
        if not u or u.startswith("#"):
            continue
        if not re.match(r"^https?://", u, re.I):
            continue
        try:
            p = urlparse(u)
            if p.scheme in ("http", "https") and p.netloc:
                out.append(u[:1024])
        except Exception:
            continue
    return list(dict.fromkeys(out))


def collect_source_candidates(
    queries: list[str],
    user_urls: list[str],
    tavily_enabled: bool,
    per_query_count: int = 5,
    max_total: int = 14,
) -> list[SourceCandidate]:
    seen: set[str] = set()
    candidates: list[SourceCandidate] = []

    for u in user_urls:
        key = _norm_url(u)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(SourceCandidate(url=u, title=u, snippet="", origin="UTILISATEUR"))
        if len(candidates) >= max_total:
            return candidates

    # Si l'utilisateur fournit explicitement des URLs,
    # on respecte ce mode "ciblé" et on n'ajoute pas d'autres sources web.
    if user_urls:
        return candidates

    if tavily_enabled:
        for q in queries:
            if len(candidates) >= max_total:
                break
            try:
                # Requête entre guillemets pour privilégier les correspondances
                # textuelles proches et limiter les résultats hors sujet.
                strict_q = f"\"{q}\"" if " " in q else q
                results = tavily_search.tavily_web_search(strict_q, max_results=per_query_count)
            except Exception:
                continue
            for r in results:
                u = r["url"]
                key = _norm_url(u)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    SourceCandidate(
                        url=u,
                        title=r.get("title") or u,
                        snippet=r.get("description") or "",
                        origin="TAVILY",
                    )
                )
                if len(candidates) >= max_total:
                    return candidates

    return candidates


def _norm_url(url: str) -> str:
    u = url.strip().lower().rstrip("/")
    if u.startswith("http://"):
        u = "https://" + u[7:]
    return u


def _domains_from_urls(urls: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        try:
            host = (urlparse(u).netloc or "").strip().lower()
            if host.startswith("www."):
                host = host[4:]
            if host and host not in seen:
                seen.add(host)
                out.append(host)
        except Exception:
            continue
    return out


def _cached_source_text(url: str, max_age_days: int = 30) -> tuple[str, float] | None:
    """
    Cache local : réutilise le contenu déjà stocké en base pour cette URL.
    """
    cutoff = timezone.now() - timedelta(days=max_age_days)
    src = (
        SourceComparaison.objects.filter(url_source=url[:1024], date_ajout__gte=cutoff)
        .exclude(contenu_source="")
        .order_by("-date_ajout")
        .first()
    )
    if not src:
        return None
    body = (src.contenu_source or "").strip()
    if len(body) < 120:
        return None
    return body[:80_000], 0.72


def split_sentences_with_spans(text: str) -> list[tuple[str, int, int]]:
    text = text or ""
    out: list[tuple[str, int, int]] = []
    for m in re.finditer(r"[^\n.!?]+[.!?]?", text):
        chunk = m.group().strip()
        if len(chunk.split()) >= 5:
            out.append((chunk, m.start(), m.end()))
    if not out and text.strip():
        out.append((text.strip(), 0, len(text.strip())))
    return out


def passages_for_source(
    doc_text: str,
    source_text: str,
    source_tokens: list[str],
    min_jaccard: float = PASSAGE_MIN_JACCARD,
    min_cosine_sentence: float = PASSAGE_MIN_COSINE,
) -> list[tuple[int, int, str, str, float]]:
    """(debut, fin, extrait_doc, extrait_source, score)."""
    found: list[tuple[int, int, str, str, float]] = []
    src_for_sentence_cos = source_text[:50_000]
    for sent, start, end in split_sentences_with_spans(doc_text):
        st = text_preprocessing.preprocess_for_similarity(sent)
        if len(st) < 4:
            continue
        j = jaccard_similarity_words(st, source_tokens)
        c_sent = cosine_similarity_tfidf(sent, src_for_sentence_cos)
        if j < min_jaccard and c_sent < min_cosine_sentence:
            continue
        src_excerpt = (source_text[:1200] + "…") if len(source_text) > 1200 else source_text
        # Score passage : max(Jaccard, cosinus phrase) pour éviter de manquer
        # des reformulations lexicalement proches mais avec vocabulaire différent.
        passage_score = max(float(j), float(c_sent))
        found.append((start, end, sent[:2000], src_excerpt[:2000], passage_score))
    return found


def _persist_analysis(
    utilisateur: Utilisateur,
    raw_text: str,
    resolved: list[tuple[SourceCandidate, str, float]],
) -> Analyse:
    titre = raw_text.split("\n", 1)[0].strip()[:200] or "Analyse PlagGuard"
    tokens_doc = text_preprocessing.preprocess_for_similarity(raw_text)

    with transaction.atomic():
        doc = Document.objects.create(
            titre=titre,
            nom_fichier="soumission_interface_web.txt",
            chemin_fichier="-",
            contenu_texte=raw_text[:200_000],
            statut_analyse="EN_COURS",
            id_utilisateur=utilisateur,
        )

        source_objects: list[tuple[SourceComparaison, str, list[str], float]] = []
        for c, body, quality in resolved:
            stoks = text_preprocessing.preprocess_for_similarity(body)
            src_type = "WEB_TAVILY" if c.origin in ("TAVILY", "TAVILY_DOMAIN") else "WEB_UTILISATEUR"
            src = SourceComparaison.objects.create(
                type_source=src_type,
                titre_source=c.title[:255],
                auteur_source=f"quality={quality:.2f}",
                url_source=c.url[:1024],
                contenu_source=body[:100_000],
            )
            source_objects.append((src, body, stoks, quality))

        pourcentages: list[float] = []
        result_rows: list[tuple[ResultatSimilarite, SourceComparaison, str, list[str]]] = []

        analyse = Analyse.objects.create(
            id_document=doc,
            score_global=0.0,
            nombre_sources_trouvees=0,
            etat_analyse="EN_COURS",
        )

        for src, body, stoks, quality in source_objects:
            j, cos_sim, comb = combined_similarity_score(
                tokens_doc, stoks, raw_text[:50_000], body[:50_000]
            )
            fp_sim = fingerprint_similarity(tokens_doc, stoks)
            fp_cont = fingerprint_containment(tokens_doc, stoks)
            # Score renforcé :
            # - similarité globale (Jaccard + cosinus + fingerprints)
            # - ET couverture du document par la source (containment),
            #   pour mieux détecter le copier-coller direct.
            base_score = (0.20 * j) + (0.45 * cos_sim) + (0.35 * fp_sim)
            final_score = max(base_score, fp_cont)
            # Pénalise légèrement les sources de faible qualité d'extraction.
            final_score = final_score * (0.78 + (0.22 * max(0.0, min(1.0, quality))))
            pct = round(final_score * 100, 2)
            if pct < MIN_SOURCE_MATCH_PCT:
                continue
            pourcentages.append(pct)
            res = ResultatSimilarite.objects.create(
                id_analyse=analyse,
                id_source=src,
                score_similarite=float(cos_sim),
                pourcentage_correspondance=pct,
            )
            result_rows.append((res, src, body, stoks))

        # Si aucune source ne passe le seuil, on garde une analyse valide
        # mais sans résultat "suspect" pour éviter des liens hors sujet.

        # Limite le nombre de segments surlignés pour éviter un rapport visuellement saturé.
        passage_budget = 80
        per_result_ranges: dict[int, list[tuple[int, int]]] = {}
        for res, _src, body, stoks in result_rows:
            if passage_budget <= 0:
                break
            for start, end, tdoc, tsrc, taux in passages_for_source(raw_text, body, stoks):
                if passage_budget <= 0:
                    break
                if float(taux) < MIN_PASSAGE_STRENGTH:
                    continue
                PassagePlagie.objects.create(
                    id_resultat=res,
                    texte_document=tdoc,
                    texte_source=tsrc[:5000],
                    position_debut=start,
                    position_fin=end,
                    taux_similarite_passage=round(taux * 100, 2),
                )
                per_result_ranges.setdefault(int(res.id_resultat), []).append((int(start), int(end)))
                passage_budget -= 1

        # Recalcule un score global plus fidèle à la couverture réelle du texte suspect.
        # On prend le max entre :
        # - score source (algorithmes)
        # - couverture texte surligné (par meilleure source)
        max_pct = max(pourcentages) if pourcentages else 0.0
        max_coverage_pct = 0.0
        doc_len = max(1, len(raw_text))
        for ranges in per_result_ranges.values():
            if not ranges:
                continue
            ranges.sort(key=lambda x: x[0])
            merged: list[list[int]] = [[ranges[0][0], ranges[0][1]]]
            for s, e in ranges[1:]:
                if s <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], e)
                else:
                    merged.append([s, e])
            covered = sum(max(0, e - s) for s, e in merged)
            coverage_pct = (covered / doc_len) * 100.0
            if coverage_pct > max_coverage_pct:
                max_coverage_pct = coverage_pct

        # Si aucun passage n'est retenu, on considère qu'il n'y a pas de plagiat
        # exploitable dans le rapport utilisateur.
        if not per_result_ranges:
            final_global_pct = 0.0
            sources_retained = 0
        else:
            final_global_pct = float(min(100.0, max(max_pct, max_coverage_pct)))
            sources_retained = len(per_result_ranges)

        analyse.score_global = final_global_pct
        analyse.nombre_sources_trouvees = sources_retained
        analyse.etat_analyse = "TERMINEE"
        analyse.save(update_fields=["score_global", "nombre_sources_trouvees", "etat_analyse"])

        doc.statut_analyse = "TERMINE"
        doc.save(update_fields=["statut_analyse"])

    analyse.refresh_from_db()
    return analyse


def run_plagiarism_analysis(
    utilisateur: Utilisateur,
    raw_text: str,
    urls_text: str = "",
) -> Analyse:
    """Exécute l'analyse complète et persiste les tables DOCUMENT, SOURCE_COMPARAISON, ANALYSE, etc."""
    raw_text = (raw_text or "").strip()
    wc = _count_words(raw_text)
    if wc < MIN_WORDS_FOR_ANALYSIS:
        raise ValueError(
            f"Texte trop court : saisissez au moins {MIN_WORDS_FOR_ANALYSIS} mots pour lancer l'analyse."
        )
    if wc > MAX_WORDS_FOR_ANALYSIS:
        raise ValueError(
            f"Texte trop long : la limite est de {MAX_WORDS_FOR_ANALYSIS} mots pour une analyse."
        )

    tavily_key = (getattr(settings, "TAVILY_API_KEY", None) or "").strip()
    user_urls = parse_user_urls(urls_text)

    if not tavily_key and not user_urls:
        raise ValueError(
            "Configurez TAVILY_API_KEY pour la recherche web, ou indiquez au moins une URL "
            "à comparer dans le champ prévu."
        )

    tokens_doc = text_preprocessing.preprocess_for_similarity(raw_text)
    queries = _build_precise_queries(raw_text, tokens_doc)
    if not queries and tavily_key:
        fallback = " ".join(tokens_doc[:12])
        queries = [fallback[:200]] if len(fallback) >= 6 else [raw_text[:120].replace("\n", " ")]

    candidates = collect_source_candidates(
        queries=queries,
        user_urls=user_urls,
        tavily_enabled=bool(tavily_key),
        max_total=10,
    )
    if not candidates:
        raise ValueError("Aucune source trouvée (recherche web vide ou URLs invalides).")

    resolved: list[tuple[SourceCandidate, str, float]] = []
    for c in candidates:
        cached = _cached_source_text(c.url)
        if cached:
            body, quality = cached
            resolved.append((c, body[:80_000], quality))
            continue

        page, method, quality = html_text.fetch_page_text_robust(c.url)
        body = page or ""
        if not body and c.snippet:
            body = c.snippet
            quality = max(quality, 0.45)
        if len(body.strip()) < 40:
            continue
        # On garde une trace de qualité : requests_html / playwright_render / snippet.
        if method == "playwright_render":
            quality = max(quality, 0.95)
        elif method == "requests_html":
            quality = max(quality, 0.85)
        resolved.append((c, body[:80_000], quality))

    # Fallback robuste :
    # en mode URLs ciblées, certains sites bloquent l'extraction HTML directe.
    # On tente alors des extraits Tavily, limités strictement au(x) domaine(s)
    # fournis par l'utilisateur.
    if not resolved and user_urls and tavily_key:
        domains = _domains_from_urls(user_urls)
        if domains:
            fallback_queries = queries[:2] if queries else [raw_text[:180].replace("\n", " ")]
            seen_urls: set[str] = set()
            for q in fallback_queries:
                try:
                    results = tavily_search.tavily_web_search(
                        query=q,
                        max_results=6,
                        include_domains=domains,
                    )
                except Exception:
                    continue
                for r in results:
                    u = (r.get("url") or "").strip()
                    if not u or u in seen_urls:
                        continue
                    snippet = (r.get("description") or "").strip()
                    if len(snippet) < 40:
                        continue
                    seen_urls.add(u)
                    cand = SourceCandidate(
                        url=u[:1024],
                        title=(r.get("title") or u)[:255],
                        snippet=snippet,
                        origin="TAVILY_DOMAIN",
                    )
                    resolved.append((cand, snippet[:80_000], 0.55))
                    if len(resolved) >= 8:
                        break
                if len(resolved) >= 8:
                    break

    if not resolved:
        if user_urls:
            raise ValueError(
                "Impossible d'extraire du texte depuis l'URL fournie (site protégé, contenu dynamique "
                "ou non textuel). Essayez une autre URL de ce site (article/page texte), ou laissez la "
                "zone URL vide pour une recherche web élargie."
            )
        raise ValueError(
            "Impossible d'extraire suffisamment de texte depuis les pages trouvées "
            "(sites bloqués, pages vides ou non textuelles)."
        )

    return _persist_analysis(utilisateur, raw_text, resolved)


def _build_precise_queries(raw_text: str, tokens_doc: list[str]) -> list[str]:
    """
    Fabrique des requêtes plus pertinentes :
    - 2-3 phrases longues du texte brut
    - + n-grams nettoyés en secours
    """
    sentence_candidates: list[str] = []
    for sent, _s, _e in split_sentences_with_spans(raw_text):
        words = sent.split()
        if 8 <= len(words) <= 30:
            sentence_candidates.append(" ".join(words[:20]))

    # Garder les phrases les plus informatives (les plus longues)
    sentence_candidates = sorted(sentence_candidates, key=len, reverse=True)
    picked = sentence_candidates[:3]

    grams = text_preprocessing.pick_search_queries(tokens_doc, n=5, max_queries=3)
    out: list[str] = []
    seen = set()
    for q in picked + grams:
        q = (q or "").strip()
        if len(q) < 12:
            continue
        if q in seen:
            continue
        seen.add(q)
        out.append(q[:220])
        if len(out) >= 5:
            break
    return out
