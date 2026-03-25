"""Visiteurs anonymes : essais limités, Utilisateur technique lié à la session."""

from __future__ import annotations

from django.contrib.sessions.backends.base import SessionBase

from .models import Utilisateur

# Nombre d'analyses gratuites sans compte (puis redirection vers connexion / inscription).
GUEST_TRIAL_MAX = 3
SESSION_KEY_ANALYSIS_COUNT = "guest_analysis_count"


def _ensure_session(request) -> SessionBase:
    if not request.session.session_key:
        request.session.save()
    return request.session


def get_guest_utilisateur(request) -> Utilisateur:
    """Un enregistrement UTILISATEUR par session navigateur (e-mail dérivé de la clé de session)."""
    session = _ensure_session(request)
    sid = session.session_key or ""
    email = f"guest_{sid}@guest.plagguard.local"[:254]
    obj, _ = Utilisateur.objects.get_or_create(
        email=email,
        defaults={
            "nom": "Visiteur",
            "prenom": "Essai",
            "mot_de_passe": "!",
            "role": "USER",
        },
    )
    return obj


def guest_analysis_count(request) -> int:
    return int(request.session.get(SESSION_KEY_ANALYSIS_COUNT, 0) or 0)


def guest_can_analyze(request) -> bool:
    return guest_analysis_count(request) < GUEST_TRIAL_MAX


def guest_increment_after_successful_analysis(request) -> None:
    session = _ensure_session(request)
    n = guest_analysis_count(request) + 1
    session[SESSION_KEY_ANALYSIS_COUNT] = n
    session.modified = True


def guest_trials_remaining(request) -> int:
    return max(0, GUEST_TRIAL_MAX - guest_analysis_count(request))
