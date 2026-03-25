import re

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Q
from django.urls import NoReverseMatch, reverse

from .models import AbonnementWaafi
from .user_bridge import get_utilisateur_for_user


def admin_dashboard_context(request):
    """Contexte léger pour le dashboard admin personnalisé."""
    users_admin_url = ""
    recent_users = []

    user_model = get_user_model()
    app_label = user_model._meta.app_label
    model_name = user_model._meta.model_name
    try:
        users_admin_url = reverse(f"admin:{app_label}_{model_name}_changelist")
    except NoReverseMatch:
        users_admin_url = ""

    try:
        recent_users = user_model.objects.order_by("-date_joined")[:6]
    except Exception:
        recent_users = []

    return {
        "users_admin_url": users_admin_url,
        "recent_users": recent_users,
    }


def device_context(request):
    """
    Détecte si l'utilisateur est sur un mobile via le User-Agent.
    Objectif: activer une classe CSS sur les pages d'auth, sans dupliquer toute la UI.
    """
    ua = (request.META.get("HTTP_USER_AGENT") or "").lower()
    # Heuristique volontairement simple.
    is_mobile = bool(re.search(r"(iphone|android|ipad|ipod|windows phone|blackberry|mobile)", ua))
    return {"is_mobile": is_mobile}


def subscription_context(request):
    """
    Rend un indicateur pour activer les liens premium dans le sidebar.
    """
    has_abonnement_actif = False
    abonnement_plan = None

    if request.user.is_authenticated:
        # Table UTILISATEUR liée au compte Django via OneToOne.
        util = None
        try:
            util = request.user.plagguard_utilisateur
        except Exception:
            util = None

        if util is not None:
            now = timezone.now()
            ab = (
                AbonnementWaafi.objects.filter(
                    id_utilisateur=util,
                    statut=AbonnementWaafi.STATUT_ACTIVE,
                )
                    .filter(Q(date_fin__gt=now) | Q(date_fin__isnull=True))
                .order_by("-id_abonnement")
                .first()
            )
            if ab:
                has_abonnement_actif = True
                abonnement_plan = ab.plan
        else:
            # Fallback : créer / récupérer l'enregistrement UTILISATEUR si l'OneToOne
            # n'est pas encore présent (cas limite).
            try:
                util_fallback = get_utilisateur_for_user(request.user)
            except Exception:
                util_fallback = None
            if util_fallback is not None:
                now = timezone.now()
                ab = (
                    AbonnementWaafi.objects.filter(
                        id_utilisateur=util_fallback,
                        statut=AbonnementWaafi.STATUT_ACTIVE,
                        date_fin__gt=now,
                    )
                    .order_by("-id_abonnement")
                    .first()
                )
                if ab:
                    has_abonnement_actif = True
                    abonnement_plan = ab.plan

    return {
        "has_abonnement_actif": has_abonnement_actif,
        "abonnement_plan": abonnement_plan,
    }
