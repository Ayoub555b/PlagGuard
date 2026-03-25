from datetime import timedelta

from django.contrib import admin, messages
from django.utils import timezone

from .models import AbonnementWaafi, Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(admin.ModelAdmin):
    list_display = ("id_utilisateur", "prenom", "nom", "email", "django_user")
    search_fields = ("email", "prenom", "nom")


@admin.register(AbonnementWaafi)
class AbonnementWaafiAdmin(admin.ModelAdmin):
    list_display = (
        "id_abonnement",
        "id_utilisateur",
        "plan",
        "statut",
        "date_debut",
        "date_fin",
        "reference_waafi",
    )
    list_filter = ("plan", "statut")
    search_fields = ("reference_waafi",)

    actions = ["action_activer_30j", "action_desactiver"]

    @admin.action(description="Activer (débloquer) - 30 jours")
    def action_activer_30j(self, request, queryset):
        now = timezone.now()
        for ab in queryset:
            ab.statut = AbonnementWaafi.STATUT_ACTIVE
            ab.date_debut = now
            ab.date_fin = now + timedelta(days=30)
            # transaction_id_waafi et raw_status optionnels pour manuel
            if not ab.raw_status:
                ab.raw_status = "MANUAL_ACTIVATION"
            ab.save(update_fields=["statut", "date_debut", "date_fin", "raw_status"])

        messages.success(request, "Abonnements activés pour 30 jours.")

    @admin.action(description="Désactiver (marquer expiré)")
    def action_desactiver(self, request, queryset):
        now = timezone.now()
        for ab in queryset:
            ab.statut = AbonnementWaafi.STATUT_EXPIRED
            ab.date_fin = ab.date_fin or now
            ab.raw_status = ab.raw_status or "MANUAL_DEACTIVATION"
            ab.save(update_fields=["statut", "date_fin", "raw_status"])

        messages.success(request, "Abonnements désactivés.")

