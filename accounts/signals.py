from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Utilisateur


def _resolve_role(user):
    if user.is_superuser:
        return "ADMIN"
    if user.is_staff:
        return "STAFF"
    return "USER"


def _resolve_identite(user):
    prenom = (user.first_name or "").strip()
    nom = (user.last_name or "").strip()
    if not prenom:
        prenom = "Utilisateur"
    if not nom:
        nom = user.username or "Inconnu"
    return nom, prenom


def _resolve_email(user):
    email = (user.email or "").strip().lower()
    if email:
        return email
    username = (user.username or "user").strip().lower().replace(" ", "_")
    return f"{username}@plagguard.local"


@receiver(post_save, sender=get_user_model())
def sync_django_user_to_utilisateur(sender, instance, **kwargs):
    """
    Synchronise automatiquement chaque compte Django vers la table UTILISATEUR.
    """
    nom, prenom = _resolve_identite(instance)
    email = _resolve_email(instance)
    role = _resolve_role(instance)

    Utilisateur.objects.update_or_create(
        django_user=instance,
        defaults={
            "email": email[:254],
            "nom": nom,
            "prenom": prenom,
            "mot_de_passe": instance.password,
            "role": role,
        },
    )

