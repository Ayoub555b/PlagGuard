"""Lien entre django.contrib.auth.User et la table UTILISATEUR."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser

from .models import Utilisateur


def resolve_email_for_user(user: AbstractBaseUser) -> str:
    email = (getattr(user, "email", None) or "").strip().lower()
    if email:
        return email
    username = (user.get_username() or "user").strip().lower().replace(" ", "_")
    return f"{username}@plagguard.local"


def get_utilisateur_for_user(user: AbstractBaseUser) -> Utilisateur:
    """
    Récupère ou crée l'enregistrement UTILISATEUR lié au compte Django (OneToOne).
    Ne pas indexer uniquement sur l'e-mail : plusieurs User peuvent partager la même adresse en base Django.
    """
    obj = Utilisateur.objects.filter(django_user=user).first()
    if obj:
        return obj
    email = resolve_email_for_user(user)
    nom = (user.last_name or "").strip() or "Inconnu"
    prenom = (user.first_name or "").strip() or (user.get_username() or "Utilisateur")
    role = "ADMIN" if user.is_superuser else ("STAFF" if user.is_staff else "USER")
    final_email = email[:254]
    if Utilisateur.objects.filter(email__iexact=final_email).exists():
        final_email = f"compte_{user.pk}@users.plagguard.local"[:254]
    return Utilisateur.objects.create(
        django_user=user,
        email=final_email,
        nom=nom[:150],
        prenom=prenom[:150],
        mot_de_passe=user.password,
        role=role,
    )
