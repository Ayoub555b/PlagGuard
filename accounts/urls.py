from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('connexion/', views.login_view, name='login'),
    path('inscription/', views.register_view, name='register'),
    path('confirmer-email/<str:token>/', views.verify_email_view, name='verify_email'),
    path('verifiez-votre-email/', views.check_email_view, name='check_email'),
    path('deconnexion/', views.logout_view, name='logout'),
    path('accueil/', views.accueil_view, name='accueil'),
    path('api/importer-document/', views.import_document_view, name='import_document'),
    path('api/analyser/', views.analyze_plagiarism_view, name='analyze'),
    path('historique/', views.historique_view, name='historique'),
    path('rapport/', views.rapport_redirect_view, name='rapport'),
    path('rapport/<int:analyse_id>/', views.rapport_detail_view, name='rapport_detail'),
    path('reglages/', views.reglages_view, name='reglages'),
    path('reglages/plagiat/', views.reglages_plagiat_view, name='reglages_plagiat'),
    path('abonnement/', views.abonnement_view, name='abonnement'),

    # Abonnement : WaafiPay (HPP)
    path('abonnement/gratuit/', views.abonnement_gratuit_view, name='abonnement_gratuit'),
    path('abonnement/waafi/<str:plan>/start/', views.waafi_abonnement_start_view, name='waafi_abonnement_start'),
    path('abonnement/waafi/hpp/success/', views.waafi_hpp_success_view, name='waafi_abonnement_success'),
    path('abonnement/waafi/hpp/failure/', views.waafi_hpp_failure_view, name='waafi_abonnement_failure'),

    # Détecteurs premium
    path('detecteur-ia/', views.detecteur_ia_view, name='detecteur_ia'),
    path('detecteur-plagiat/', views.detecteur_plagiat_view, name='detecteur_plagiat'),

    # API Sapling (détection contenu)
    path(
        'api/detecteur-plagiat/sapling/',
        views.sapling_plagiat_api_view,
        name='sapling_plagiat_api',
    ),

    # Rapports Sapling (Détecteur IA)
    path('rapport-ia/', views.rapport_ia_view, name='rapport_ia'),
]
