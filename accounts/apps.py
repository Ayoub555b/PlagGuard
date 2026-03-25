from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    verbose_name = 'Comptes utilisateurs'

    def ready(self):
        # Activer les signaux de synchronisation vers la table UTILISATEUR.
        from . import signals  # noqa: F401
