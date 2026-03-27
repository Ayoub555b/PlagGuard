import json
import uuid
from datetime import timedelta
from html import escape
from urllib.parse import quote
import math

import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.http import JsonResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.db.models import Q
from .forms import LoginForm, RegisterForm, DocumentImportForm
from .models import AbonnementWaafi, Analyse, EmailVerificationToken, PassagePlagie, ResultatSimilarite
from . import text_extract
from .plagiarism_service import run_plagiarism_analysis
from .sapling_service import sapling_ai_detect
from .user_bridge import get_utilisateur_for_user
from .guest_session import (
    get_guest_utilisateur,
    guest_can_analyze,
    guest_increment_after_successful_analysis,
    guest_trials_remaining,
)

User = get_user_model()
PLAGIAT_ALERT_THRESHOLD_PCT = 30.0


def _verification_absolute_url(request, token: str) -> str:
    """Lien de confirmation : reverse() + SITE_URL (recommandé) ou URL dérivée de la requête."""
    path = reverse("accounts:verify_email", kwargs={"token": token})
    base = (getattr(settings, "SITE_URL", None) or "").strip().rstrip("/")
    if base:
        return f"{base}{path}"
    return request.build_absolute_uri(path)


def _send_verification_email(user, raw_code: str):
    """
    Envoie l'e-mail de confirmation (par code de vérification).
    """
    if not raw_code:
        # Fallback: si on n'a pas de code (cas non prévu), on ne fait rien.
        return

    subject = "Votre code de confirmation - PlagGuard"
    message_plain = (
        f"Bonjour {user.get_full_name() or user.email},\n\n"
        f"Votre code de confirmation PlagGuard est : {raw_code}\n\n"
        f"Ce code expire dans 24 heures.\n\n"
        f"Si vous n'avez pas créé de compte, ignorez cet e-mail.\n\n"
        f"— L'équipe PlagGuard"
    )
    html_message = render_to_string('email_verification_code.html', {
        'user': user,
        'code': raw_code,
    })
    send_mail(
        subject=subject,
        message=message_plain,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
        html_message=html_message,
    )


@ensure_csrf_cookie
def login_view(request):
    force_login = request.GET.get("force") == "1"
    next_url = request.GET.get("next") or request.POST.get("next")
    if request.user.is_authenticated and force_login:
        logout(request)
    if request.user.is_authenticated:
        if next_url:
            return redirect(next_url)
        return redirect('accounts:accueil')
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                user = None
            if user is not None:
                if not user.is_active:
                    messages.error(
                        request,
                        'Compte non activé. Vérifiez votre boîte mail et saisissez le code de confirmation, puis réessayez de vous connecter.'
                    )
                    return render(request, 'connexion.html', {'form': form})
                user = authenticate(request, username=user.username, password=password)
            else:
                user = None
            if user is not None:
                login(request, user)
                messages.success(request, 'Connexion réussie.')
                if next_url:
                    return redirect(next_url)
                if user.is_staff or user.is_superuser:
                    return redirect('/admin/')
                return redirect('accounts:accueil')
            messages.error(request, 'E-mail ou mot de passe incorrect.')
        else:
            messages.error(request, 'Veuillez corriger les erreurs ci-dessous.')
    else:
        form = LoginForm()
    return render(request, 'connexion.html', {'form': form, 'next_url': next_url or ''})


def register_view(request):
    force_register = request.GET.get("force") == "1"
    if request.user.is_authenticated and force_register:
        logout(request)
    if request.user.is_authenticated:
        return redirect('accounts:accueil')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Créer l'objet de vérification, générer un code et envoyer l'e-mail.
            token_obj = EmailVerificationToken.objects.create(user=user)
            raw_code = token_obj.regenerate_code(length=6)
            request.session["email_verification_token_id"] = token_obj.pk
            request.session.modified = True
            try:
                _send_verification_email(user, raw_code)
            except Exception as e:
                messages.error(
                    request,
                    'Votre compte a été créé mais l\'envoi de l\'e-mail de confirmation a échoué. '
                    'Contactez le support.'
                )
                return redirect('accounts:register')
            messages.success(
                request,
                "Compte créé. Un e-mail contenant un code de confirmation vous a été envoyé. "
                "Saisissez ce code pour activer votre compte."
            )
            return redirect('accounts:check_email')
        messages.error(request, 'Veuillez corriger les erreurs ci-dessous.')
    else:
        form = RegisterForm()
    return render(request, 'inscription.html', {'form': form})


def verify_email_view(request, token):
    """Vue appelée quand l'utilisateur clique sur le lien dans l'e-mail."""
    token_obj = EmailVerificationToken.objects.filter(token=token).select_related('user').first()
    if token_obj is None:
        messages.error(request, 'Lien de confirmation invalide ou déjà utilisé.')
        return redirect('accounts:login')
    if token_obj.is_expired():
        token_obj.delete()
        messages.error(request, 'Ce lien a expiré. Inscrivez-vous à nouveau pour recevoir un nouveau lien.')
        return redirect('accounts:register')
    user = token_obj.user
    user.is_active = True
    user.save(update_fields=['is_active'])
    token_obj.delete()
    messages.success(request, 'Votre adresse e-mail est confirmée. Vous pouvez maintenant vous connecter.')
    return redirect('accounts:login')


def check_email_view(request):
    """Page affichée après inscription : « Vérifiez votre boîte mail »."""
    return render(request, 'check_email.html')


@require_POST
def verify_email_code_view(request):
    """Vérifie le code saisi sur la page check_email.html et active le compte."""
    token_id = request.session.get("email_verification_token_id")
    raw_code = (request.POST.get("code") or "").strip()

    if not token_id:
        messages.error(request, "Session expirée. Veuillez vous réinscrire.")
        return redirect('accounts:register')

    token_obj = get_object_or_404(
        EmailVerificationToken.objects.select_related("user"),
        pk=token_id,
    )

    # Expiration (24h par défaut)
    if token_obj.is_expired(max_hours=24):
        token_obj.delete()
        request.session.pop("email_verification_token_id", None)
        messages.error(request, "Le code a expiré. Renvoyez un nouveau code.")
        return redirect('accounts:check_email')

    if not token_obj.check_code(raw_code):
        token_obj.attempts = (token_obj.attempts or 0) + 1
        token_obj.save(update_fields=["attempts"])

        if token_obj.attempts >= 5:
            token_obj.delete()
            request.session.pop("email_verification_token_id", None)
            messages.error(request, "Code invalide (trop de tentatives). Réinscrivez-vous.")
            return redirect('accounts:register')

        messages.error(request, "Code incorrect. Réessayez.")
        return redirect('accounts:check_email')

    user = token_obj.user
    user.is_active = True
    user.save(update_fields=["is_active"])
    token_obj.delete()
    request.session.pop("email_verification_token_id", None)

    messages.success(request, "Compte activé. Vous pouvez maintenant vous connecter.")
    return redirect('accounts:login')


@require_POST
def resend_email_code_view(request):
    """Renvoyer un nouveau code de vérification par e-mail."""
    token_id = request.session.get("email_verification_token_id")

    if not token_id:
        messages.error(request, "Session expirée. Veuillez vous réinscrire.")
        return redirect('accounts:register')

    token_obj = get_object_or_404(
        EmailVerificationToken.objects.select_related("user"),
        pk=token_id,
    )
    raw_code = token_obj.regenerate_code(length=6)

    try:
        _send_verification_email(token_obj.user, raw_code)
    except Exception:
        messages.error(
            request,
            "Impossible d'envoyer le nouveau code. Contactez le support."
        )
        return redirect('accounts:check_email')

    messages.success(request, "Nouveau code envoyé. Vérifiez votre boîte mail.")
    return redirect('accounts:check_email')


def logout_view(request):
    logout(request)
    messages.success(request, 'Vous avez été déconnecté.')
    return redirect('accounts:login')


def _first_form_error(form):
    for errs in form.errors.values():
        if errs:
            return str(errs[0])
    return "Données invalides."


@ensure_csrf_cookie
def accueil_view(request):
    context = {}
    if not request.user.is_authenticated:
        context["guest_trials_remaining"] = guest_trials_remaining(request)
    return render(request, "accueil.html", context)


@require_POST
def import_document_view(request):
    """
    Reçoit un PDF ou Word (.docx), extrait le texte et le renvoie en JSON
    pour remplir la zone d'analyse sur la page d'accueil.
    """
    form = DocumentImportForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"ok": False, "error": _first_form_error(form)}, status=400)

    upload = form.cleaned_data["document"]
    if hasattr(upload, "seek"):
        upload.seek(0)
    try:
        text = text_extract.extract_text_from_upload(upload)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except ModuleNotFoundError:
        return JsonResponse(
            {
                "ok": False,
                "error": "Modules d’extraction absents. Installez-les avec : pip install pypdf python-docx",
            },
            status=503,
        )
    except Exception:
        return JsonResponse(
            {"ok": False, "error": "Impossible de lire ce fichier. Vérifiez qu'il n'est pas corrompu ou protégé."},
            status=400,
        )

    text = (text or "").strip()
    if not text:
        return JsonResponse(
            {
                "ok": False,
                "error": "Aucun texte extrait (document vide, scan image uniquement, ou mise en page non prise en charge).",
            },
            status=400,
        )

    max_chars = 100_000
    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    return JsonResponse({"ok": True, "text": text, "truncated": truncated})


def _utilisateur_for_request(request):
    if request.user.is_authenticated:
        return get_utilisateur_for_user(request.user)
    return get_guest_utilisateur(request)


def _analyses_for_request(request):
    """Historique / rapports : strictement lié au compte Django ou à la session invité."""
    if request.user.is_authenticated:
        return (
            Analyse.objects.filter(id_document__id_utilisateur__django_user=request.user)
            .select_related("id_document")
            .order_by("-date_analyse")
        )
    util = get_guest_utilisateur(request)
    return (
        Analyse.objects.filter(id_document__id_utilisateur=util)
        .select_related("id_document")
        .order_by("-date_analyse")
    )


def _choose_non_overlapping_passages(passages_qs):
    """
    Construit une liste d'intervalles non chevauchants en conservant les passages
    les plus pertinents (taux le plus élevé) ; chaque intervalle garde sa source.
    """
    rows = []
    for p in passages_qs:
        s, e = int(p.position_debut), int(p.position_fin)
        if e <= s:
            continue
        rows.append(
            {
                "start": s,
                "end": e,
                "score": float(p.taux_similarite_passage or 0.0),
                "source_url": (p.id_resultat.id_source.url_source or "").strip(),
                "source_title": (p.id_resultat.id_source.titre_source or "Source web").strip(),
            }
        )
    if not rows:
        return []

    rows.sort(key=lambda x: (-x["score"], -(x["end"] - x["start"])))
    selected = []
    for row in rows:
        overlap = False
        for keep in selected:
            if not (row["end"] <= keep["start"] or row["start"] >= keep["end"]):
                overlap = True
                break
        if not overlap:
            selected.append(row)

    selected.sort(key=lambda x: x["start"])
    return selected


def _rapport_html_body(full_text: str, intervals: list[dict]) -> str:
    if not full_text:
        return ""
    n = len(full_text)
    parts = []
    pos = 0
    for item in intervals:
        s, e = item["start"], item["end"]
        s = max(0, min(s, n))
        e = max(0, min(e, n))
        if s >= e:
            continue
        if pos < s:
            parts.append(escape(full_text[pos:s]))
        source_url = escape(item.get("source_url", ""))
        source_title = escape(item.get("source_title", "Source web"))
        title_attr = f"Source: {source_title} ({source_url})" if source_url else f"Source: {source_title}"
        parts.append(
            f'<span class="plagiat" title="{title_attr}" data-source-url="{source_url}">{escape(full_text[s:e])}</span>'
        )
        pos = max(pos, e)
    if pos < n:
        parts.append(escape(full_text[pos:]))
    raw = "".join(parts)
    return mark_safe(raw.replace("\n", "<br>\n"))


@require_POST
def analyze_plagiarism_view(request):
    """Lance N-grams + Tavily + Jaccard / TF-IDF / cosinus et enregistre en base."""
    try:
        payload = json.loads(request.body.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Corps JSON invalide."}, status=400)

    text = (payload.get("text") or "").strip()
    urls_text = payload.get("urls_text") or ""

    if not request.user.is_authenticated and not guest_can_analyze(request):
        accueil_path = reverse("accounts:accueil")
        login_url = request.build_absolute_uri(
            f"{reverse('accounts:login')}?next={quote(accueil_path, safe='')}"
        )
        return JsonResponse(
            {
                "ok": False,
                "error": "Vous avez utilisé vos 3 essais gratuits. Connectez-vous ou créez un compte pour continuer.",
                "redirect_to_login": True,
                "login_url": login_url,
            }
        )

    try:
        util = _utilisateur_for_request(request)
        analyse = run_plagiarism_analysis(util, text, urls_text)
        if not request.user.is_authenticated:
            guest_increment_after_successful_analysis(request)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except requests.RequestException as exc:
        return JsonResponse(
            {"ok": False, "error": f"Erreur réseau ou API Tavily : {exc}"},
            status=502,
        )
    except ModuleNotFoundError:
        return JsonResponse(
            {
                "ok": False,
                "error": "Dépendances manquantes : pip install scikit-learn beautifulsoup4 requests",
            },
            status=503,
        )

    url = reverse("accounts:rapport_detail", kwargs={"analyse_id": analyse.pk})
    return JsonResponse({"ok": True, "analyse_id": analyse.pk, "redirect": url})


@login_required(login_url="accounts:login")
def historique_view(request):
    analyses = _analyses_for_request(request)[:50]
    items = []
    for a in analyses:
        doc = a.id_document
        wc = len((doc.contenu_texte or "").split())
        orig = max(0.0, min(100.0, 100.0 - float(a.score_global or 0)))
        items.append(
            {
                "analyse": a,
                "word_count": wc,
                "original_pct": round(orig, 1),
            }
        )
    return render(request, "historique.html", {"historique_items": items})


def rapport_redirect_view(request):
    analyses = _analyses_for_request(request)
    first = analyses.first()
    if not first:
        messages.info(request, "Aucune analyse pour le moment. Lancez une vérification depuis l’accueil.")
        return redirect("accounts:accueil")
    return HttpResponseRedirect(reverse("accounts:rapport_detail", kwargs={"analyse_id": first.pk}))


def rapport_detail_view(request, analyse_id: int):
    if request.user.is_authenticated:
        analyse = get_object_or_404(
            Analyse.objects.select_related("id_document"),
            pk=analyse_id,
            id_document__id_utilisateur__django_user=request.user,
        )
    else:
        util = get_guest_utilisateur(request)
        analyse = get_object_or_404(
            Analyse.objects.select_related("id_document"),
            pk=analyse_id,
            id_document__id_utilisateur=util,
        )
    doc = analyse.id_document
    full_text = doc.contenu_texte or ""

    # Même filtre pour surlignage, liste des sources et score perçu : on n'affiche
    # pas de lien « source » sur des correspondances trop faibles (faux positifs).
    _strong_passage_filter = {
        "id_resultat__id_analyse": analyse,
        "id_resultat__pourcentage_correspondance__gte": 20.0,
        "taux_similarite_passage__gte": 25.0,
    }
    passage_qs = (
        PassagePlagie.objects.filter(**_strong_passage_filter)
        .select_related("id_resultat__id_source")
        .order_by("position_debut")
    )
    intervals = _choose_non_overlapping_passages(passage_qs)
    rapport_body_html = _rapport_html_body(full_text, intervals)

    passage_result_ids = set(
        PassagePlagie.objects.filter(**_strong_passage_filter).values_list("id_resultat", flat=True)
    )
    resultats = (
        ResultatSimilarite.objects.filter(id_analyse=analyse, pk__in=passage_result_ids)
        .select_related("id_source")
        .order_by("-pourcentage_correspondance")
    )

    plagiat_pct = float(analyse.score_global or 0)
    plagiat_pct = max(0.0, min(100.0, plagiat_pct))
    original_pct = max(0.0, min(100.0, 100.0 - plagiat_pct))
    word_count = len(full_text.split())
    similar_words_est = int(round(word_count * plagiat_pct / 100.0))

    sources_list = []
    for r in resultats[:5]:
        src = r.id_source
        sources_list.append(
            {
                "url": src.url_source,
                "title": src.titre_source,
                "match_pct": r.pourcentage_correspondance,
            }
        )

    if plagiat_pct >= PLAGIAT_ALERT_THRESHOLD_PCT:
        rapport_advice = (
            "Attention : votre rapport est proche d'un plagiat. "
            "Nous vous conseillons de reformuler et de citer correctement vos sources."
        )
        rapport_advice_level = "warning"
    elif round(plagiat_pct, 1) <= 0:
        rapport_advice = (
            "Aucune similarité significative n'a été trouvée avec les pages web consultées pour cette analyse. "
            "Cela ne garantit pas l'absence totale de chevauchement ailleurs sur Internet."
        )
        rapport_advice_level = "ok"
    else:
        rapport_advice = (
            "Le score reste sous le seuil d'alerte plagiat. "
            "Continuez à reformuler et à citer vos sources pour un travail clairement original."
        )
        rapport_advice_level = "ok"

    context = {
        "analyse": analyse,
        "document": doc,
        "rapport_body_html": rapport_body_html,
        "original_pct": round(original_pct, 1),
        "plagiat_pct": round(plagiat_pct, 1),
        "word_count": word_count,
        "similar_words_est": similar_words_est,
        "sources_list": sources_list,
        "plagiat_threshold_pct": round(PLAGIAT_ALERT_THRESHOLD_PCT, 1),
        "rapport_advice": rapport_advice,
        "rapport_advice_level": rapport_advice_level,
        "diagramme_original_width": round(original_pct, 2),
        "diagramme_plagiat_width": round(plagiat_pct, 2),
        "aucune_similarite_significative": round(plagiat_pct, 1) <= 0,
    }
    return render(request, "rapport.html", context)


@login_required(login_url="accounts:login")
def reglages_view(request):
    return render(request, "reglages.html")


@login_required(login_url="accounts:login")
def reglages_plagiat_view(request):
    return render(
        request,
        "reglages_plagiat.html",
        {"plagiat_threshold_pct": round(PLAGIAT_ALERT_THRESHOLD_PCT, 1)},
    )


@login_required(login_url="accounts:login")
def abonnement_view(request):
    return render(request, "abonnement.html")


def _waafi_amount_for_plan_djf(plan: str) -> int | None:
    if plan == AbonnementWaafi.PLAN_PRO:
        return 3557
    if plan == AbonnementWaafi.PLAN_PROPLUS:
        return 10670
    return None


def _waafi_duration_days_for_plan(plan: str) -> int:
    # Hypothèse simple : 30 jours pour chaque plan payant / gratuit.
    return 30


def _get_utilisateur_for_request(request):
    if not request.user.is_authenticated:
        return None
    # L’extension OneToOne devrait déjà exister, mais on préfère rester robuste.
    util = getattr(request.user, "plagguard_utilisateur", None)
    if util is not None:
        return util
    return get_utilisateur_for_user(request.user)


def _get_abonnement_actif(utilisateur) -> AbonnementWaafi | None:
    now = timezone.now()
    return (
        AbonnementWaafi.objects.filter(
            id_utilisateur=utilisateur,
            statut=AbonnementWaafi.STATUT_ACTIVE,
        )
        .filter(Q(date_fin__gt=now) | Q(date_fin__isnull=True))
        .order_by("-id_abonnement")
        .first()
    )


def _extract_reference_id_from_callback(request) -> str | None:
    candidates = []
    for k in ("referenceId", "reference_id", "referenceID", "ref", "merchantReferenceId", "merchant_reference_id"):
        if k in request.GET:
            candidates.append(request.GET.get(k))
        if k in request.POST:
            candidates.append(request.POST.get(k))
    for v in candidates:
        if isinstance(v, str) and v.strip():
            return v.strip()

    # Fallback : première valeur qui ressemble à une ref
    for data in (request.GET, request.POST):
        for key, value in data.items():
            if "ref" in key.lower() or "reference" in key.lower():
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return None


def _get_waafi_config():
    merchant_uid = (getattr(settings, "WAAFI_MERCHANT_UID", "") or "").strip()
    store_id = (getattr(settings, "WAAFI_STORE_ID", "") or "").strip()
    hpp_key = (getattr(settings, "WAAFI_HPP_KEY", "") or "").strip()

    # Auth API (nécessaire pour /asm)
    api_user_id = (getattr(settings, "WAAFI_API_USER_ID", "") or "").strip()
    api_key = (getattr(settings, "WAAFI_API_KEY", "") or "").strip()
    fixed_payer_phone = (getattr(settings, "WAAFI_PAYER_PHONE", "") or "").strip()

    use_sandbox = str(getattr(settings, "WAAFI_USE_SANDBOX", "1")).lower() in ("1", "true", "yes", "on")
    base_url = (
        getattr(settings, "WAAFI_BASE_URL", None)
        or ("https://sandbox.waafipay.net/asm" if use_sandbox else "https://api.waafipay.com/asm")
    )

    missing = [name for name, val in (
        ("WAAFI_MERCHANT_UID", merchant_uid),
        ("WAAFI_STORE_ID", store_id),
        ("WAAFI_HPP_KEY", hpp_key),
        ("WAAFI_API_USER_ID", api_user_id),
        ("WAAFI_API_KEY", api_key),
    ) if not val]

    return {
        "merchant_uid": merchant_uid,
        "store_id": store_id,
        "hpp_key": hpp_key,
        "api_user_id": api_user_id,
        "api_key": api_key,
        "base_url": base_url,
        "fixed_payer_phone": fixed_payer_phone,
        "missing": missing,
    }


def _waafi_now_timestamp() -> str:
    # Ex: 2024-11-05 09:19:10.131 (au milliseconde)
    return timezone.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


@login_required(login_url="accounts:login")
def abonnement_gratuit_view(request):
    """
    Active instantanément un abonnement gratuit (sans paiement WaafiPay).
    Sert uniquement à débloquer les détecteurs.
    """
    util = _get_utilisateur_for_request(request)
    if not util:
        return redirect("accounts:login")

    existing = _get_abonnement_actif(util)
    if existing and existing.plan == AbonnementWaafi.PLAN_FREE:
        return redirect("accounts:detecteur_plagiat")

    now = timezone.now()
    end_at = now + timedelta(days=_waafi_duration_days_for_plan(AbonnementWaafi.PLAN_FREE))

    ref = f"FREE-{util.id_utilisateur}-{uuid.uuid4().hex[:10]}"

    AbonnementWaafi.objects.update_or_create(
        reference_waafi=ref,
        defaults={
            "id_utilisateur": util,
            "plan": AbonnementWaafi.PLAN_FREE,
            "statut": AbonnementWaafi.STATUT_ACTIVE,
            "date_debut": now,
            "date_fin": end_at,
            "transaction_id_waafi": "",
            "raw_status": "FREE_ACTIVATED",
        },
    )

    messages.success(request, "Forfait gratuit activé. Les détecteurs sont débloqués.")
    return redirect("accounts:detecteur_plagiat")


@login_required(login_url="accounts:login")
@require_POST
def waafi_abonnement_start_view(request, plan: str):
    """
    Lance un paiement WaafiPay via HPP_PURCHASE.
    Nécessite : payer_phone (mobile complet, ex: 2526XXXXXXXX sans '+').
    """
    util = _get_utilisateur_for_request(request)
    if not util:
        return redirect("accounts:login")

    plan = (plan or "").upper().strip()
    amount_djf = _waafi_amount_for_plan_djf(plan)
    if not amount_djf:
        messages.error(request, "Plan invalide.")
        return redirect("accounts:abonnement")

    cfg = _get_waafi_config()
    if cfg["missing"]:
        messages.error(
            request,
            "Configuration WaafiPay incomplète. "
            f"Il manque : {', '.join(cfg['missing'])}.",
        )
        return redirect("accounts:abonnement")

    payer_phone = (request.POST.get("payer_phone") or "").strip()
    cfg_phone = (cfg.get("fixed_payer_phone") or "").strip()
    # Si un téléphone de payeur fixe est défini dans le .env, on l'utilise (mode test / paiement unique).
    if cfg_phone:
        payer_phone = cfg_phone

    # Tolère +253... => on retire le '+'
    payer_phone = payer_phone.replace("+", "").strip()
    if not payer_phone.isdigit() or len(payer_phone) < 8:
        messages.error(request, "Numéro Waafi invalide. Exemple : 2526XXXXXXXX (sans '+').")
        return redirect("accounts:abonnement")

    reference_id = f"PG-{plan}-{util.id_utilisateur}-{uuid.uuid4().hex[:10]}"
    reference_id = reference_id[:50]

    # Enregistre d’abord une ligne pending : le callback va confirmer.
    pending = AbonnementWaafi.objects.create(
        id_utilisateur=util,
        plan=plan,
        statut=AbonnementWaafi.STATUT_PENDING,
        reference_waafi=reference_id,
        transaction_id_waafi="",
        raw_status="",
    )

    success_url = f"{(getattr(settings, 'SITE_URL', '') or '').strip().rstrip('/')}{reverse('accounts:waafi_abonnement_success')}"
    failure_url = f"{(getattr(settings, 'SITE_URL', '') or '').strip().rstrip('/')}{reverse('accounts:waafi_abonnement_failure')}"

    if not success_url or not failure_url:
        messages.error(request, "SITE_URL manquant pour les callbacks WaafiPay.")
        return redirect("accounts:abonnement")

    payload = {
        "schemaVersion": "1.0",
        "requestId": str(uuid.uuid4()),
        "timestamp": _waafi_now_timestamp(),
        "channelName": "WEB",
        "serviceName": "HPP_PURCHASE",
        "serviceParams": {
            "merchantUid": cfg["merchant_uid"],
            "storeId": int(cfg["store_id"]) if str(cfg["store_id"]).isdigit() else cfg["store_id"],
            "hppKey": cfg["hpp_key"],
            "paymentMethod": "MWALLET_ACCOUNT",
            "hppSuccessCallbackUrl": success_url,
            "hppFailureCallbackUrl": failure_url,
            "hppRespDataFormat": 2,  # 2 = GET
            "payerInfo": {"subscriptionId": payer_phone},
            "transactionInfo": {
                "referenceId": pending.reference_waafi,
                "amount": f"{amount_djf:.2f}",
                "currency": "DJF",
                "description": f"Abonnement {plan}",
            },
            # Champs API requis côté HPP (selon configuration du merchant)
            "apiUserId": cfg["api_user_id"],
            "apiKey": cfg["api_key"],
        },
    }

    try:
        resp = requests.post(cfg["base_url"], json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        pending.statut = AbonnementWaafi.STATUT_FAILED
        pending.raw_status = "WAAFI_REQUEST_ERROR"
        pending.save(update_fields=["statut", "raw_status"])
        messages.error(request, "Erreur lors du lancement du paiement WaafiPay.")
        return redirect("accounts:abonnement")

    hpp_url = (data.get("params") or {}).get("hppUrl")
    if not hpp_url:
        pending.statut = AbonnementWaafi.STATUT_FAILED
        pending.raw_status = f"WAAFI_NO_HPP_URL:{data.get('responseCode')}"
        pending.save(update_fields=["statut", "raw_status"])
        messages.error(request, "Paiement WaafiPay refusé (hppUrl introuvable).")
        return redirect("accounts:abonnement")

    messages.info(request, "Redirection vers WaafiPay pour finaliser le paiement...")
    return redirect(hpp_url)


def _waafi_gettraninfo(reference_id: str) -> tuple[str, str]:
    """
    Retourne (statut, transactionId).
    """
    cfg = _get_waafi_config()
    if cfg["missing"]:
        return ("CONFIG_INCOMPLETE", "")

    payload = {
        "schemaVersion": "1.0",
        "requestId": str(uuid.uuid4()),
        "timestamp": _waafi_now_timestamp(),
        "channelName": "WEB",
        "serviceName": "HPP_GETTRANINFO",
        "serviceParams": {
            "merchantUid": cfg["merchant_uid"],
            "storeId": int(cfg["store_id"]) if str(cfg["store_id"]).isdigit() else cfg["store_id"],
            "hppKey": cfg["hpp_key"],
            "referenceId": reference_id,
            "apiUserId": cfg["api_user_id"],
            "apiKey": cfg["api_key"],
        },
    }

    resp = requests.post(cfg["base_url"], json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    params = data.get("params") or {}
    status = str(params.get("status") or params.get("tranStatusDesc") or params.get("tranStatusId") or "").strip()
    txid = str(params.get("transactionId") or "").strip()
    return (status, txid)


@csrf_exempt
def waafi_hpp_success_view(request):
    return _waafi_hpp_callback_view(request, ok=True)


@csrf_exempt
def waafi_hpp_failure_view(request):
    return _waafi_hpp_callback_view(request, ok=False)


def _waafi_hpp_callback_view(request, ok: bool):
    reference_id = _extract_reference_id_from_callback(request)
    if not reference_id:
        return redirect("accounts:abonnement")

    try:
        abonnement = AbonnementWaafi.objects.get(reference_waafi=reference_id)
    except AbonnementWaafi.DoesNotExist:
        return redirect("accounts:abonnement")

    try:
        status, txid = _waafi_gettraninfo(reference_id)
    except Exception:
        status = "WAAFI_QUERY_ERROR"
        txid = ""

    status_norm = (status or "").lower()

    now = timezone.now()
    if "approved" in status_norm or status_norm == "approved" or "r_c_s_success" in status_norm:
        abonnement.statut = AbonnementWaafi.STATUT_ACTIVE
        abonnement.transaction_id_waafi = txid
        abonnement.raw_status = status
        abonnement.date_debut = now
        abonnement.date_fin = now + timedelta(days=_waafi_duration_days_for_plan(abonnement.plan))
        abonnement.save(
            update_fields=["statut", "transaction_id_waafi", "raw_status", "date_debut", "date_fin"]
        )
        # On redirige vers le détecteur plagiat (celui que tu as déjà)
        messages.success(request, "Paiement validé. Les détecteurs premium sont débloqués.")
        return redirect("accounts:detecteur_plagiat")

    if "expired" in status_norm:
        abonnement.statut = AbonnementWaafi.STATUT_EXPIRED
    else:
        abonnement.statut = AbonnementWaafi.STATUT_FAILED

    abonnement.transaction_id_waafi = txid
    abonnement.raw_status = status or ("WAAFI_HPP_OK" if ok else "WAAFI_HPP_FAILED")
    abonnement.save(update_fields=["statut", "transaction_id_waafi", "raw_status"])

    messages.error(request, "Paiement non confirmé. Réessayez ou vérifiez le statut dans WaafiPay.")
    return redirect("accounts:abonnement")


@login_required(login_url="accounts:login")
def detecteur_ia_view(request):
    util = _get_utilisateur_for_request(request)
    if not util:
        return redirect("accounts:login")

    ab = _get_abonnement_actif(util)
    if not ab:
        messages.warning(request, "Abonnement requis pour accéder au détecteur IA.")
        return redirect("accounts:abonnement")

    return render(request, "detecteur_ia.html", {"abonnement_plan": ab.plan})


@login_required(login_url="accounts:login")
def detecteur_plagiat_view(request):
    util = _get_utilisateur_for_request(request)
    if not util:
        return redirect("accounts:login")

    ab = _get_abonnement_actif(util)
    if not ab:
        messages.warning(request, "Abonnement requis pour accéder au détecteur plagiat.")
        return redirect("accounts:abonnement")

    return render(request, "detecteur_plagiat.html", {"abonnement_plan": ab.plan})


@login_required(login_url="accounts:login")
def rapport_ia_view(request):
    """Affiche le rapport du détecteur IA basé sur la dernière analyse stockée en session."""
    util = _get_utilisateur_for_request(request)
    if not util:
        return redirect("accounts:login")

    ab = _get_abonnement_actif(util)
    if not ab:
        messages.warning(request, "Abonnement requis pour accéder au rapport IA.")
        return redirect("accounts:abonnement")

    last = request.session.get("sapling_last_result")
    if not last:
        messages.info(request, "Aucune analyse IA récente. Lancez une détection depuis le détecteur IA.")
        return redirect("accounts:detecteur_ia")

    # Nettoyage : évite d’avoir une session qui grossit inutilement
    # (ici, on conserve juste les infos utiles).
    IA_ALERT_THRESHOLD_PCT = 50.0

    score_pct = float(last.get("score_pct") or 0.0)
    score_pct = max(0.0, min(100.0, score_pct))
    score = float(last.get("score") or (score_pct / 100.0))

    top_sentences = last.get("top_sentences") or []
    stability_std = last.get("stability_std")
    prepared_top_sentences = []
    for item in top_sentences:
        try:
            sentence = (item.get("sentence") or "").strip()
            sc = float(item.get("score") or 0.0)
            sc = max(0.0, min(1.0, sc))
            prepared_top_sentences.append(
                {
                    "sentence": sentence,
                    "score_pct": round(sc * 100.0, 1),
                }
            )
        except Exception:
            continue

    ia_pct = score_pct
    original_pct = max(0.0, min(100.0, 100.0 - ia_pct))

    diagramme_original_width = round(original_pct, 2)
    diagramme_plagiat_width = round(ia_pct, 2)

    aucun_indice_fort = round(ia_pct, 1) <= 0.0

    if ia_pct >= IA_ALERT_THRESHOLD_PCT:
        rapport_advice = (
            "Attention : le score IA est élevé, ce qui suggère une probabilité importante de contenu généré automatiquement. "
            "Nous vous conseillons de relire, reformuler et d'ajouter vos sources et votre analyse personnelle."
        )
        rapport_advice_level = "warning"
    else:
        rapport_advice = (
            "Le score IA reste sous le seuil d'alerte. Cela ne garantit pas l'absence totale de contenu généré automatiquement, "
            "mais l'indication est moins forte. Continuez à reformuler et à citer correctement vos sources."
        )
        rapport_advice_level = "ok"

    # Si le score varie beaucoup selon les segments, on le signale.
    try:
        stability_val = float(stability_std) if stability_std is not None else None
    except Exception:
        stability_val = None
    if stability_val is not None and stability_val >= 0.18:
        rapport_advice += " Note : le résultat est relativement instable selon les parties du texte (stabilité faible)."

    return render(
        request,
        "rapport_ia.html",
        {
            "abonnement_plan": ab.plan,
            "score_pct": round(score_pct, 1),
            "score": score,
            "ia_pct": round(ia_pct, 1),
            "original_pct": round(original_pct, 1),
            "diagramme_original_width": diagramme_original_width,
            "diagramme_plagiat_width": diagramme_plagiat_width,
            "aucune_similarite_significative": aucun_indice_fort,
            "ia_threshold_pct": round(IA_ALERT_THRESHOLD_PCT, 1),
            "rapport_advice": rapport_advice,
            "rapport_advice_level": rapport_advice_level,
            "top_sentences": prepared_top_sentences,
        },
    )


def _chunk_words(text: str, max_chunks: int = 3) -> list[str]:
    """
    Découpe en chunks de taille similaire (en mots) pour rendre la détection
    plus robuste : une partie peut être marquée IA, pas forcément tout le texte.
    """
    words = (text or "").strip().split()
    n = len(words)
    if n == 0:
        return []

    if n <= 170:
        k = 1
    elif n <= 340:
        k = 2
    else:
        k = 3
    k = min(k, max_chunks)

    size = int(math.ceil(n / k))
    chunks: list[str] = []
    for i in range(0, n, size):
        c = " ".join(words[i : i + size]).strip()
        if c:
            chunks.append(c)
    return chunks[:max_chunks]


def _compute_perplexity_proxy_from_token_probs(token_probs: list) -> float | None:
    """Indicateur interne agrégé à partir des probabilités par jeton (optionnel)."""
    eps = 1e-12
    if not isinstance(token_probs, list) or not token_probs:
        return None

    entropies = []
    for tprob in token_probs:
        try:
            p_ai = float(tprob)
            p_ai = max(eps, min(1.0 - eps, p_ai))
            # Entropie binaire H(p) = -[p ln p + (1-p) ln (1-p)]
            h = -(p_ai * math.log(p_ai) + (1.0 - p_ai) * math.log(1.0 - p_ai))
            entropies.append(h)
        except Exception:
            continue

    if not entropies:
        return None
    avg_h = sum(entropies) / len(entropies)
    return float(math.exp(avg_h))


@login_required(login_url="accounts:login")
@require_POST
def sapling_plagiat_api_view(request):
    """
    API JSON du détecteur IA (score 0..1 : 0 = humain probable, 1 = IA probable).
    """
    util = _get_utilisateur_for_request(request)
    if not util:
        return JsonResponse({"ok": False, "error": "Non authentifié."}, status=401)

    ab = _get_abonnement_actif(util)
    if not ab:
        return JsonResponse({"ok": False, "error": "Abonnement requis."}, status=403)

    try:
        payload = json.loads(request.body.decode())
    except Exception:
        return JsonResponse({"ok": False, "error": "Corps JSON invalide."}, status=400)

    text = (payload.get("text") or "").strip()
    if not text:
        return JsonResponse({"ok": False, "error": "Texte manquant."}, status=400)

    # Cohérent avec l'UI de l'accueil
    MIN_WORDS_ANALYSIS = 80
    MAX_WORDS_ANALYSIS = 500
    words_count = len(text.split())
    if words_count < MIN_WORDS_ANALYSIS:
        return JsonResponse(
            {"ok": False, "error": f"Le texte doit contenir au moins {MIN_WORDS_ANALYSIS} mots."},
            status=400,
        )
    if words_count > MAX_WORDS_ANALYSIS:
        return JsonResponse(
            {"ok": False, "error": f"Le texte ne doit pas dépasser {MAX_WORDS_ANALYSIS} mots."},
            status=400,
        )

    chunks = _chunk_words(text, max_chunks=3)
    if not chunks:
        return JsonResponse({"ok": False, "error": "Impossible de découper le texte."}, status=400)

    chunk_scores: list[float] = []
    perplexities: list[float] = []
    merged_ranked: list[dict] = []

    for chunk in chunks:
        try:
            data = sapling_ai_detect(chunk)
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=503)
        except requests.RequestException as exc:
            return JsonResponse({"ok": False, "error": f"Erreur réseau du service de détection IA : {exc}"}, status=502)

        score_i = float(data.get("score") or 0.0)
        score_i = max(0.0, min(1.0, score_i))
        chunk_scores.append(score_i)

        # Perplexité proxy sur ce chunk
        token_probs = data.get("token_probs") or []
        p_i = _compute_perplexity_proxy_from_token_probs(token_probs)
        if p_i is not None:
            perplexities.append(p_i)

        # Extraits (phrases) les plus IA-probables du chunk
        sentence_scores = data.get("sentence_scores") or []
        ranked = []
        for s in sentence_scores:
            try:
                sent = (s.get("sentence") or "").strip()
                if not sent:
                    continue
                sent_score = float(s.get("score") or 0.0)
                sent_score = max(0.0, min(1.0, sent_score))
                ranked.append({"sentence": sent, "score": sent_score})
            except Exception:
                continue
        ranked.sort(key=lambda x: x["score"], reverse=True)
        merged_ranked.extend(ranked[:5])

    # Agrégation : moyenne (plus conservatrice) + stabilité (écart-type)
    avg_score = sum(chunk_scores) / len(chunk_scores) if chunk_scores else 0.0
    max_score = max(chunk_scores) if chunk_scores else avg_score

    mean = avg_score
    var = sum((s - mean) ** 2 for s in chunk_scores) / max(1, len(chunk_scores))
    stability_std = float(math.sqrt(var))

    score = max(0.0, min(1.0, avg_score))
    score_pct = round(score * 100.0, 1)
    max_score_pct = round(max_score * 100.0, 1)

    perplexity_proxy = None
    if perplexities:
        perplexity_proxy = float(sum(perplexities) / len(perplexities))

    merged_ranked.sort(key=lambda x: x["score"], reverse=True)
    top_sentences = merged_ranked[:5]

    result = {
        "score": score,
        "score_pct": score_pct,
        "top_sentences": top_sentences,
        "perplexity_proxy": perplexity_proxy,
        "max_score_pct": max_score_pct,
        "stability_std": stability_std,
    }

    # Stockage session pour générer un "rapport" après analyse.
    request.session["sapling_last_result"] = result
    request.session.modified = True

    redirect_url = reverse("accounts:rapport_ia")
    return JsonResponse(
        {
            "ok": True,
            "score": score,
            "score_pct": score_pct,
            "top_sentences": top_sentences,
            "perplexity_proxy": perplexity_proxy,
            "max_score_pct": max_score_pct,
            "stability_std": stability_std,
            "redirect": redirect_url,
        }
    )
