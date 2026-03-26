import secrets
import uuid
import hashlib
from django.db import models
from django.conf import settings
from django.utils import timezone


def generate_token():
    return secrets.token_urlsafe(32)


def generate_verification_code(length: int = 6) -> str:
    """Code numérique court (ex: 6 chiffres) envoyé par e-mail."""
    return "".join(secrets.choice("0123456789") for _ in range(length))


def hash_code(code: str) -> str:
    """Hash du code pour éviter de le stocker en clair."""
    return hashlib.sha256((code or "").encode("utf-8")).hexdigest()


class EmailVerificationToken(models.Model):
    """Token envoyé par e-mail pour confirmer l'adresse à l'inscription."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='email_verification_token',
    )
    token = models.CharField(max_length=64, unique=True, default=generate_token)
    # Code court à saisir (en complément/alternative au lien).
    # Stocké en hash pour limiter l'exposition.
    code_hash = models.CharField(max_length=64, blank=True, default="")
    code_created_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    # Lien expiré après 24 h
    def is_expired(self, max_hours=24):
        from datetime import timedelta
        return timezone.now() > self.created_at + timedelta(hours=max_hours)

    def regenerate_code(self, length: int = 6) -> str:
        """
        Génère un nouveau code, le stocke (hash) et réinitialise les tentatives.
        Retourne le code en clair pour l'envoyer par e-mail.
        """
        code = generate_verification_code(length=length)
        self.code_hash = hash_code(code)
        self.code_created_at = timezone.now()
        self.attempts = 0
        self.created_at = self.code_created_at
        self.save(update_fields=["code_hash", "code_created_at", "attempts", "created_at"])
        return code

    def is_code_expired(self, max_hours: int = 24) -> bool:
        """Expiration du code (même durée que created_at par défaut)."""
        from datetime import timedelta
        return (
            self.code_created_at is None
            or timezone.now() > self.code_created_at + timedelta(hours=max_hours)
        )

    def check_code(self, raw_code: str) -> bool:
        if not raw_code:
            return False
        if not self.code_hash:
            return False
        return self.code_hash == hash_code(raw_code.strip())

    def __str__(self):
        return f"Vérification {self.user.email}"


class Utilisateur(models.Model):
    id_utilisateur = models.BigAutoField(primary_key=True)
    # Un compte Django = un profil métier (historique isolé). Les invités sans compte : null.
    django_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='plagguard_utilisateur',
    )
    nom = models.CharField(max_length=150)
    prenom = models.CharField(max_length=150)
    # Plus unique : plusieurs profils techniques peuvent exister (invités, comptes distincts).
    email = models.EmailField()
    # Stockage du hash du mot de passe (Django Auth hash si vous l'utilisez plus tard)
    mot_de_passe = models.CharField(max_length=255)
    role = models.CharField(max_length=50, default='USER')
    date_creation = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'UTILISATEUR'

    def __str__(self):
        return f"{self.prenom} {self.nom} ({self.email})"


class AbonnementWaafi(models.Model):
    """
    Abonnement basé sur un paiement WaafiPay (HPP + callbacks).
    Sert à activer/désactiver les fonctionnalités premium (ex: détecteurs).
    """

    PLAN_FREE = "FREE"
    PLAN_PRO = "PRO"
    PLAN_PROPLUS = "PROPLUS"
    PLAN_CHOICES = [
        (PLAN_FREE, "Forfait Gratuit"),
        (PLAN_PRO, "Pro"),
        (PLAN_PROPLUS, "Pro+"),
    ]

    STATUT_PENDING = "EN_ATTENTE"
    STATUT_ACTIVE = "ACTIF"
    STATUT_FAILED = "ECHOUER"
    STATUT_EXPIRED = "EXPIRE"
    STATUT_CHOICES = [
        (STATUT_PENDING, "En attente"),
        (STATUT_ACTIVE, "Actif"),
        (STATUT_FAILED, "Échoué"),
        (STATUT_EXPIRED, "Expiré"),
    ]

    id_abonnement = models.BigAutoField(primary_key=True)
    id_utilisateur = models.ForeignKey(
        Utilisateur,
        on_delete=models.CASCADE,
        related_name="abonnements",
    )

    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default=PLAN_FREE)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default=STATUT_PENDING)

    # Quand le paiement est validé
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)

    # Identifiant WaafiPay côté merchant (transactionInfo.referenceId)
    def _generate_reference_waafi():
        return f"MANUAL-{uuid.uuid4().hex[:18]}"

    reference_waafi = models.CharField(max_length=64, unique=True, default=_generate_reference_waafi)
    transaction_id_waafi = models.CharField(max_length=64, blank=True, default="")
    raw_status = models.CharField(max_length=64, blank=True, default="")

    date_creation = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "ABONNEMENT_WAAFIPAY"

    def __str__(self):
        return f"{self.id_abonnement} ({self.plan}) - {self.statut}"


class Document(models.Model):
    id_document = models.BigAutoField(primary_key=True)
    titre = models.CharField(max_length=255)
    nom_fichier = models.CharField(max_length=255)
    chemin_fichier = models.CharField(max_length=1024)
    contenu_texte = models.TextField()
    date_soumission = models.DateTimeField(default=timezone.now)
    statut_analyse = models.CharField(max_length=50, default='EN_ATTENTE')
    id_utilisateur = models.ForeignKey(
        Utilisateur,
        on_delete=models.CASCADE,
        related_name='documents',
    )

    class Meta:
        db_table = 'DOCUMENT'

    def __str__(self):
        return self.titre


class SourceComparaison(models.Model):
    id_source = models.BigAutoField(primary_key=True)
    type_source = models.CharField(max_length=50)
    titre_source = models.CharField(max_length=255)
    auteur_source = models.CharField(max_length=255, blank=True, default='')
    url_source = models.URLField(max_length=1024)
    contenu_source = models.TextField()
    date_ajout = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'SOURCE_COMPARAISON'

    def __str__(self):
        return self.titre_source


class Analyse(models.Model):
    id_analyse = models.BigAutoField(primary_key=True)
    id_document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='analyses',
    )
    date_analyse = models.DateTimeField(default=timezone.now)
    score_global = models.FloatField()
    nombre_sources_trouvees = models.IntegerField(default=0)
    etat_analyse = models.CharField(max_length=50, default='EN_ATTENTE')

    class Meta:
        db_table = 'ANALYSE'

    def __str__(self):
        return str(self.id_analyse)


class ResultatSimilarite(models.Model):
    id_resultat = models.BigAutoField(primary_key=True)
    id_analyse = models.ForeignKey(
        Analyse,
        on_delete=models.CASCADE,
        related_name='resultats',
    )
    id_source = models.ForeignKey(
        SourceComparaison,
        on_delete=models.CASCADE,
        related_name='resultats',
    )
    score_similarite = models.FloatField()
    pourcentage_correspondance = models.FloatField()

    class Meta:
        db_table = 'RESULTAT_SIMILARITE'

    def __str__(self):
        return str(self.id_resultat)


class PassagePlagie(models.Model):
    id_passage = models.BigAutoField(primary_key=True)
    id_resultat = models.ForeignKey(
        ResultatSimilarite,
        on_delete=models.CASCADE,
        related_name='passages',
    )
    texte_document = models.TextField()
    texte_source = models.TextField()
    position_debut = models.IntegerField()
    position_fin = models.IntegerField()
    taux_similarite_passage = models.FloatField()

    class Meta:
        db_table = 'PASSAGE_PLAGIE'

    def __str__(self):
        return str(self.id_passage)
