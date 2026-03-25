from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import Utilisateur


class Command(BaseCommand):
    help = "Synchronise tous les comptes Django existants vers la table UTILISATEUR."

    def handle(self, *args, **options):
        User = get_user_model()
        created = 0
        updated = 0

        for user in User.objects.all():
            email = (user.email or "").strip().lower()
            if not email:
                username = (user.username or "user").strip().lower().replace(" ", "_")
                email = f"{username}@plagguard.local"
            email = email[:254]

            nom = (user.last_name or "").strip() or (user.username or "Inconnu")
            prenom = (user.first_name or "").strip() or "Utilisateur"
            role = "ADMIN" if user.is_superuser else ("STAFF" if user.is_staff else "USER")

            _, was_created = Utilisateur.objects.update_or_create(
                django_user=user,
                defaults={
                    "email": email,
                    "nom": nom,
                    "prenom": prenom,
                    "mot_de_passe": user.password,
                    "role": role,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Synchronisation terminée : {created} créés, {updated} mis à jour."
            )
        )

