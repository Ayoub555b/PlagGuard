from __future__ import annotations

import requests
from django.conf import settings


SAPLING_DETECT_URL = "https://api.sapling.ai/api/v1/aidetect"


def sapling_ai_detect(text: str) -> dict:
    """
    Appelle l'API Sapling (AI detector) et renvoie le JSON.

    Sapling renvoie un champ `score` dans [0,1] :
    - 0 = texte très probable humain
    - 1 = texte très probable IA
    """
    api_key = (getattr(settings, "SAPLING_API_KEY", "") or "").strip()
    if not api_key:
        raise ValueError("SAPLING_API_KEY non configuré dans le fichier .env.")

    payload = {
        "key": api_key,
        "text": text,
        "sent_scores": True,
        "score_string": False,
        "version": "20251027",
    }

    resp = requests.post(SAPLING_DETECT_URL, json=payload, timeout=40)
    resp.raise_for_status()
    return resp.json()

