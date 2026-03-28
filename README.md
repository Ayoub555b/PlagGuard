# PlagGuard — Détection de plagiat et de contenu généré par IA

Application web développée dans le cadre d’un projet de **génie logiciel**. Ce document présente le projet, l’équipe, les technologies et un guide technique pour installer et faire tourner l’application.

---

## Table des matières

1. [Description du projet](#description-du-projet)
2. [Objectifs](#objectifs)
3. [Présentation de l’équipe](#présentation-de-léquipe)
4. [Technologies utilisées](#technologies-utilisées)
5. [Fonctionnalités](#fonctionnalités-côté-client-et-administrateur)
6. [Structure du projet](#structure-du-projet)
7. [Tests réalisés](#tests-réalisés)
8. [Licence](#licence)
9. [Remerciements](#remerciements)
10. [Annexe — Guide d’installation et d’exploitation](#annexe--guide-dinstallation-et-dexploitation)

---

## 📌 Description du projet

**PlagGuard** permet aux utilisateurs de soumettre des textes académiques ou professionnels, d’estimer le risque de **plagiat** par comparaison avec des sources en ligne, et d’utiliser un **détecteur de contenu potentiellement généré par IA** (service externe via clé API). Le projet inclut une **gestion des comptes** (inscription, confirmation par code e-mail, réinitialisation du mot de passe), un **historique des analyses**, des **rapports détaillés**, une **page de tarification** (Francs djiboutiens) et un module d’**abonnement** (WaafiPay en mode intégration, avec possibilité d’activation manuelle côté administrateur pour les tests).

---

## 🎯 Objectifs

- Offrir une interface claire pour **analyser l’originalité** d’un texte à partir de sources web (recherche Tavily, métriques de similarité).
- Proposer, pour les abonnés, un **indicateur de probabilité « texte généré par IA** » et des rapports associés.
- Assurer un **parcours utilisateur complet** : inscription sécurisée, réglages (dont seuil de plagiat), historique et abonnements adaptés au contexte (Fdj, WaafiPay).
- Fournir une **base technique maintenable** (Django, PostgreSQL, APIs documentées) pour la démonstration, le rapport et la soutenance.

---

## 👥 Présentation de l’équipe

| Rôle | Nom |
|------|-----|
| **Chef de projet** | Doualeh Mohamed |
| **Backend** | Ayoub Atteyeh Abib |
| **Frontend** | Hassan Ismael Hassan |
| **Rédacteur** | Gouro Hassan Loita |

---

## ⚙️ Technologies utilisées

| Domaine | Détail |
|--------|--------|
| **Framework** | [Django](https://www.djangoproject.com/) 5.x (Python 3.10+) |
| **Base de données** | PostgreSQL (configuration par défaut dans `config/settings.py`) |
| **Interface** | Templates Django, HTML/CSS, JavaScript (Fetch API pour les appels AJAX) |
| **APIs externes** | **Tavily** (recherche web) ; service de **détection IA** (ex. Sapling, variable `SAPLING_API_KEY`) ; **WaafiPay** (paiement HPP + API transaction) |
| **Traitement texte / ML** | scikit-learn, numpy ; extraction PDF/Word : pypdf, python-docx |

Les dépendances Python sont listées dans `requirements.txt`.

---

## 🚀 Fonctionnalités (côté client et administrateur)

### Côté client (utilisateur)

| Domaine | Description |
|--------|-------------|
| **Authentification** | Inscription, connexion, déconnexion, confirmation de compte par **code à 6 chiffres** par e-mail, renvoi de code, réinitialisation du mot de passe (lien par e-mail). |
| **Analyse de plagiat** | Saisie de texte (bornes de mots), import PDF/Word optionnel, recherche web, pipeline de similarité (Jaccard, TF-IDF, cosinus, etc.), rapport avec sources et seuil configurable. |
| **Détecteur IA (premium)** | Accès avec abonnement actif : score de probabilité IA, analyse par segments, rapport dédié. |
| **Détecteur plagiat (page dédiée)** | Même pipeline que l’accueil, interface simplifiée pour les abonnés. |
| **Historique & rapports** | Liste des analyses passées, détail par rapport. |
| **Réglages** | Seuil de plagiat et préférences liées au module plagiat. |
| **Abonnement** | Page tarifaire en Fdj, forfait gratuit, paiement WaafiPay pour les offres payantes, callbacks succès/échec. |
| **Interface** | Pages responsive, menu latéral, navigation mobile (bottom nav), thème cohérent. |

### Côté administrateur

| Domaine | Description |
|--------|-------------|
| **Administration Django** | Accès à `/admin/` : gestion des utilisateurs, modèles métier. |
| **Abonnements** | Activation ou désactivation manuelle des abonnements (simulation sans compte marchand réel), suivi des références Waafi. |

---

## 🗂️ Structure du projet

### Arborescence principale

| Élément | Rôle |
|--------|------|
| `manage.py` | Point d’entrée Django |
| `config/` | Projet Django (settings, urls, wsgi) |
| `accounts/` | Application métier (vues, modèles, migrations, services) |
| `templates/` | Pages HTML (accueil, connexion, rapports, etc.) |
| `static/` | Feuilles de style, images |
| `requirements.txt` | Dépendances pip |
| `.env.example` | Modèle de variables d’environnement (à copier en `.env`) |
| `venv/` | Environnement virtuel Python (local, en général non versionné) |

### Architecture logicielle (aperçu)

```
┌─────────────────────────────────────────────────────────────┐
│                     Navigateur (templates + JS)              │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP / JSON
┌───────────────────────────▼─────────────────────────────────┐
│              Django — app `accounts` (vues, URLs)             │
│  • Vues pages (accueil, historique, rapports, réglages…)      │
│  • API JSON (analyse plagiat, import document, détecteur IA)  │
│  • Auth, sessions, messages                                   │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────┐   ┌─────────────────┐   ┌──────────────┐
│ PostgreSQL   │   │ Services métier │   │ APIs externes│
│ (modèles)    │   │ plagiat,        │   │ Tavily,      │
│              │   │ tavily_search,  │   │ détecteur IA,│
│              │   │ sapling_service │   │ WaafiPay     │
└──────────────┘   └─────────────────┘   └──────────────┘
```

**Applications Django** : principalement `accounts` (modèles, vues, formulaires, context processors, admin). **Configuration** : `config/settings.py`, `config/urls.py`, `manage.py`.

---

## 🧪 Tests réalisés

Les vérifications ont été menées de façon **manuelle** sur les parcours principaux :

- **Authentification** : inscription, réception du code e-mail, validation du compte, connexion/déconnexion, mot de passe oublié.
- **Analyse de plagiat** : textes de longueurs variées, import de fichiers, cohérence du rapport et des sources affichées.
- **Abonnement et premium** : affichage des offres, flux de paiement ou activation admin, visibilité des détecteurs selon le statut d’abonnement.
- **Interface** : navigation desktop et mobile, formulaires et messages d’erreur.

Des **tests automatisés** (unitaires ou d’intégration Django) peuvent être ajoutés dans une évolution future du projet.

---

## 📄 Licence

Ce projet est réalisé dans un cadre **pédagogique** (maquette / projet de génie logiciel). L’usage commercial ou la redistribution nécessitent une validation juridique et le respect des conditions d’utilisation des services tiers (Tavily, détecteur IA, WaafiPay, etc.).

---

## 🙏 Remerciements

Tout d’abord, nous remercions à Allah, le très haut qui nous a donné le courage et la volonté de réaliser ce modeste travail.

Nous remercions nos très chers parents, qui ont toujours été là pour nous.

Nous remercions nos frères et nos sœurs, pour leurs encouragements.

Nos remerciements s’adressent aussi à Dr. MOUBAREK BARRE pour ses précieux conseils, sa disponibilité, sa compréhension, sa gentillesse, les encouragements et son orientation tout au long de notre recherche.

Nous tenons à remercier très sincèrement l’ensemble des membres du jury qui nous font le grand honneur d’accepter de juger notre travail.

Enfin, nous adressons nos plus sincères remerciements à tous nos amis, qui nous ont toujours soutenu et encouragé au cours de la réalisation de ce projet.

---

# Annexe — Guide d’installation et d’exploitation

*Les sections suivantes complètent le README pour les développeurs et la reprise du projet.*

## Table des matières (annexe)

1. [Prérequis](#prérequis)
2. [Installation](#installation)
3. [Configuration (variables d’environnement)](#configuration-variables-denvironnement)
4. [Base de données](#base-de-données)
5. [Lancement de l’application](#lancement-de-lapplication)
6. [Routes et URLs utiles](#routes-et-urls-utiles)
7. [Fonctionnalités détaillées](#fonctionnalités-détaillées)
8. [Sécurité et bonnes pratiques](#sécurité-et-bonnes-pratiques)
9. [Dépannage](#dépannage)
10. [Annexes pour le rapport](#annexes-pour-le-rapport)

---

## Prérequis

- **Python** 3.10 ou supérieur
- **PostgreSQL** (instance locale avec base et utilisateur configurés)
- **pip** et idéalement **venv**
- Clés / comptes selon l’usage : **Tavily**, **détecteur IA** (`SAPLING_API_KEY`), optionnellement **WaafiPay**
- **SMTP** pour l’envoi des e-mails (ex. Gmail avec mot de passe d’application)

---

## Installation

### 1. Placer le projet

Cloner ou copier le dépôt sur la machine de développement.

### 2. Environnement virtuel

**Windows (PowerShell)** :

```powershell
cd "chemin\vers\Maquette genie logiciel"
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Linux / macOS** :

```bash
cd chemin/vers/Maquette\ genie\ logiciel
python3 -m venv venv
source venv/bin/activate
```

### 3. Dépendances

```bash
pip install -r requirements.txt
```

### 4. Fichier `.env`

Copier `.env.example` vers `.env` et renseigner les clés (voir ci-dessous).

### 5. Migrations et superutilisateur

```bash
python manage.py migrate
python manage.py createsuperuser
```

Le superutilisateur permet d’accéder à `/admin/`.

---

## Configuration (variables d’environnement)

Le fichier **`.env`** (non versionné) complète les réglages. Variables typiques (voir `.env.example`) :

| Variable | Usage |
|----------|--------|
| `TAVILY_API_KEY` | Recherche web pour l’analyse de plagiat |
| `SAPLING_API_KEY` | Détecteur IA |
| `SITE_URL` | URL publique **sans slash final** (liens dans les e-mails). Ex. `http://127.0.0.1:8000` ou URL ngrok |
| `WAAFI_*` | Identifiants WaafiPay pour les abonnements payants |

Ne jamais commiter `.env`. La configuration SMTP est définie dans `config/settings.py` ; en production, privilégier les variables d’environnement.

---

## Base de données

Par défaut : **PostgreSQL** (`NAME`, `USER`, `PASSWORD`, `HOST`, `PORT` dans `config/settings.py`).

Avant le premier `migrate` : créer la base (ex. `plagiat`) et adapter `DATABASES` si besoin.

Pour des essais locaux uniquement, SQLite peut être utilisée temporairement — à mentionner dans le rapport si c’est le cas pour la démo.

---

## Lancement de l’application

```bash
python manage.py runserver
```

Ouvrir `http://127.0.0.1:8000/`.

Pour **ngrok** : tunnel vers le port 8000, puis renseigner `SITE_URL` avec l’URL HTTPS ngrok. `CSRF_TRUSTED_ORIGINS` dans `settings.py` peut inclure les domaines ngrok.

---

## Routes et URLs utiles

| URL | Description |
|-----|-------------|
| `/` | Landing marketing |
| `/connexion/` | Connexion |
| `/inscription/` | Inscription (`?force=1` pour forcer l’écran si déjà connecté) |
| `/verifiez-votre-email/` | Code de confirmation |
| `/accueil/` | Tableau de bord / analyse plagiat |
| `/historique/` | Historique |
| `/rapport/<id>/` | Détail d’un rapport |
| `/reglages/`, `/reglages/plagiat/` | Réglages |
| `/abonnement/` | Tarification et abonnement |
| `/detecteur-ia/`, `/detecteur-plagiat/` | Détecteurs (premium) |
| `/rapport-ia/` | Rapport détecteur IA |
| `/mot-de-passe-oublie/` | Réinitialisation du mot de passe |
| `/admin/` | Administration Django |

API notamment : `/api/analyser/` (plagiat), `/api/detecteur-plagiat/sapling/` (IA).

---

## Fonctionnalités détaillées

### Analyse de plagiat

Contraintes de longueur côté client et serveur, URLs cibles optionnelles, pipeline dans `accounts/plagiarism_service.py`, recherche via `accounts/tavily_search.py`.

### Détecteur IA

Appels dans `accounts/sapling_service.py`, analyse par segments et indicateurs dans le rapport.

### Abonnement

Modèle `AbonnementWaafi` ; context processor `subscription_context` (`has_abonnement_actif`) pour les menus premium.

### E-mails

Confirmation avec **code numérique** ; mot de passe oublié via flux Django (`templates/registration/`).

---

## Sécurité et bonnes pratiques

- **`SECRET_KEY`** : régénérer en production, ne pas publier.
- **Clés API** : uniquement dans `.env` ou un gestionnaire de secrets.
- **`DEBUG=False`** en production ; `ALLOWED_HOSTS` et HTTPS.
- **CSRF** : activé ; les appels AJAX envoient le token CSRF.
- **Mots de passe** : hachage Django ; reset par jeton à durée limitée.

---

## Dépannage

| Problème | Piste |
|----------|--------|
| PostgreSQL | Service démarré, base créée, `DATABASES` correct. |
| 403 CSRF | Recharger après connexion ; `CSRF_TRUSTED_ORIGINS` derrière ngrok/HTTPS. |
| Liens vides dans les e-mails | Définir `SITE_URL` dans `.env`. |
| Détecteurs invisibles | Abonnement actif (admin ou paiement). |
| E-mails absents | SMTP, spam, mot de passe d’application Gmail. |

---

## Annexes pour le rapport

Idées à développer dans le mémoire ou la soutenance :

1. **Cahier des charges** : objectifs, acteurs, contraintes (FR, Fdj, contexte Djibouti).
2. **Modèle de données** : MCD / tables utilisateur, analyse, abonnement, etc.
3. **Diagrammes** : cas d’utilisation, séquence pour une analyse complète.
4. **Choix techniques** : Django, APIs externes (Tavily, IA, Waafi).
5. **Limites** : dépendance aux APIs, coûts, précision des détecteurs, gestion des secrets.

---

**PlagGuard** — Projet génie logiciel — Documentation pour le jury et la reprise du projet.
