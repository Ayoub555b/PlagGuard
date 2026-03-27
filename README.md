# PlagGuard — Détection de plagiat et de contenu généré par IA

## Contexte du projet

**PlagGuard** est une application web développée dans le cadre d’un projet de **génie logiciel**. Elle permet aux utilisateurs de soumettre des textes académiques ou professionnels, d’estimer le risque de **plagiat** par comparaison avec des sources en ligne, et d’utiliser un **détecteur de contenu potentiellement généré par IA** (service externe configuré par clé API). Le projet inclut également une **gestion des comptes** (inscription, confirmation par code e-mail, réinitialisation de mot de passe), un **historique des analyses**, des **rapports détaillés**, une **page de tarification** (Francs djiboutiens) et un module d’**abonnement** (WaafiPay en mode intégration, avec possibilité d’activation manuelle côté administrateur pour les tests).

---

## Table des matières

1. [Fonctionnalités principales](#fonctionnalités-principales)
2. [Stack technique](#stack-technique)
3. [Architecture logicielle](#architecture-logicielle)
4. [Structure du dépôt](#structure-du-dépôt)
5. [Prérequis](#prérequis)
6. [Installation](#installation)
7. [Configuration (variables d’environnement)](#configuration-variables-denvironnement)
8. [Base de données](#base-de-données)
9. [Lancement de l’application](#lancement-de-lapplication)
10. [Routes et URLs utiles](#routes-et-urls-utiles)
11. [Fonctionnalités détaillées](#fonctionnalités-détaillées)
12. [Sécurité et bonnes pratiques](#sécurité-et-bonnes-pratiques)
13. [Dépannage](#dépannage)
14. [Annexes pour le rapport](#annexes-pour-le-rapport)

---

## Fonctionnalités principales

| Domaine | Description |
|--------|-------------|
| **Authentification** | Inscription, connexion, déconnexion, confirmation de compte par **code à 6 chiffres** envoyé par e-mail, renvoi de code, réinitialisation de mot de passe (lien par e-mail). |
| **Analyse de plagiat** | Saisie de texte (bornes de mots), import PDF/Word optionnel, recherche web (Tavily), pipeline de similarité (Jaccard, TF-IDF, cosinus, etc.), rapport avec sources et seuil configurable. |
| **Détecteur IA (premium)** | Accès sous abonnement actif : score de probabilité IA, analyse par segments, rapport dédié. |
| **Détecteur plagiat (page dédiée)** | Même pipeline d’analyse que l’accueil, interface simplifiée pour les abonnés. |
| **Historique & rapports** | Liste des analyses passées, détail par rapport. |
| **Réglages** | Seuil de plagiat, préférences liées au module plagiat. |
| **Abonnement** | Page tarifaire en Fdj, forfait gratuit, paiement WaafiPay (HPP) pour les offres payantes, callbacks succès/échec ; activation manuelle possible via l’admin Django. |
| **Interface** | Pages responsive, menu latéral, navigation mobile (bottom nav), thème cohérent (CSS dédiés). |

---

## Stack technique

- **Framework** : [Django](https://www.djangoproject.com/) 5.x (Python 3.10+)
- **Base de données** : PostgreSQL (configuration par défaut dans `config/settings.py`)
- **Front** : Templates Django, HTML/CSS, JavaScript (Fetch API pour les appels AJAX)
- **APIs externes** :
  - **Tavily** — recherche web pour le plagiat
  - **Service de détection IA** — probabilité de texte généré automatiquement (clé API dans `.env`)
  - **WaafiPay** — paiement d’abonnement (HPP + API transaction)
- **Traitement texte / ML** : scikit-learn, numpy ; extraction PDF/Word : pypdf, python-docx

Les dépendances Python sont listées dans `requirements.txt`.

---

## Architecture logicielle

```
┌─────────────────────────────────────────────────────────────┐
│                     Navigateur (templates + JS)              │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP / JSON
┌───────────────────────────▼─────────────────────────────────┐
│              Django — app `accounts` (vues, URLs)           │
│  • Vues pages (accueil, historique, rapports, réglages…)     │
│  • API JSON (analyse plagiat, import document, détecteur IA)   │
│  • Auth, sessions, messages                                  │
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

**Applications Django** : principalement l’application `accounts` (modèles, vues, formulaires, context processors, admin).

**Fichiers de configuration** : `config/settings.py`, `config/urls.py`, `manage.py`.

---

## Structure du dépôt

| Élément | Rôle |
|--------|------|
| `manage.py` | Point d’entrée Django |
| `config/` | Projet Django (settings, urls, wsgi) |
| `accounts/` | Application métier (vues, modèles, migrations, services) |
| `templates/` | Pages HTML (accueil, connexion, rapports, etc.) |
| `static/` | Feuilles de style, images |
| `requirements.txt` | Dépendances pip |
| `.env.example` | Modèle de variables d’environnement (à copier en `.env`) |
| `venv/` | Environnement virtuel Python (local, non versionné en général) |

---

## Prérequis

- **Python** 3.10 ou supérieur
- **PostgreSQL** (version compatible avec Django ; instance locale avec base et utilisateur configurés)
- **pip** et idéalement **venv**
- Comptes / clés pour les services utilisés en production ou démo :
  - clé API **Tavily**
  - clé API **détecteur IA** (`SAPLING_API_KEY` dans `.env`)
  - (optionnel) identifiants **WaafiPay** pour les tests de paiement
- Pour l’envoi d’e-mails : compte SMTP (ex. Gmail avec mot de passe d’application) — à configurer dans `settings.py` ou via variables d’environnement selon votre déploiement

---

## Installation

### 1. Cloner ou copier le projet

Placer le dossier du projet sur la machine de développement.

### 2. Créer et activer un environnement virtuel

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

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Fichier d’environnement

Copier `.env.example` vers `.env` à la racine du projet et renseigner les clés (voir section suivante).

### 5. Migrations et superutilisateur

```bash
python manage.py migrate
python manage.py createsuperuser
```

Le compte superutilisateur permet d’accéder à `/admin/` pour gérer les utilisateurs et les abonnements manuels.

---

## Configuration (variables d’environnement)

Le fichier **`.env`** (non versionné) complète ou surcharge les réglages. Reprendre au minimum les clés suivantes depuis `.env.example` :

| Variable | Usage |
|----------|--------|
| `TAVILY_API_KEY` | Recherche web pour l’analyse de plagiat |
| `SAPLING_API_KEY` | Détecteur IA (nom technique de la variable) |
| `SITE_URL` | URL publique du site **sans slash final** (liens dans les e-mails : confirmation, reset mot de passe). Ex. `http://127.0.0.1:8000` ou `https://votre-sous-domaine.ngrok-free.app` |
| Variables **WaafiPay** | Préfixe `WAAFI_*` selon `.env.example` pour les abonnements payants |

**Important** : ne jamais commiter le fichier `.env` ni des mots de passe en clair dans le dépôt.

La configuration SMTP pour les e-mails est définie dans `config/settings.py` ; en production, il est recommandé d’utiliser des variables d’environnement plutôt que des valeurs codées en dur.

---

## Base de données

Par défaut, le projet utilise **PostgreSQL** avec les paramètres définis dans `config/settings.py` (`NAME`, `USER`, `PASSWORD`, `HOST`, `PORT`).

**Avant le premier `migrate`** :

1. Créer la base PostgreSQL (ex. `plagiat`).
2. Adapter `DATABASES` dans `settings.py` si votre utilisateur ou mot de passe diffère.

Pour un usage **uniquement local** sans PostgreSQL, on peut temporairement remplacer par SQLite (fichier `db.sqlite3`) — à documenter dans le rapport si cette variante est utilisée pour la démo.

---

## Lancement de l’application

```bash
python manage.py runserver
```

Puis ouvrir un navigateur sur `http://127.0.0.1:8000/`.

Pour exposer l’application via **ngrok** (tests mobiles, e-mails avec liens corrects), lancer ngrok vers le port 8000 et renseigner `SITE_URL` avec l’URL HTTPS fournie par ngrok. Les `CSRF_TRUSTED_ORIGINS` dans `settings.py` incluent déjà des motifs pour les domaines ngrok.

---

## Routes et URLs utiles

| URL (relatif à la racine du site) | Description |
|----------------------------------|-------------|
| `/` | Page d’accueil marketing (landing) |
| `/connexion/` | Connexion |
| `/inscription/` | Inscription (`?force=1` pour forcer l’écran d’inscription si déjà connecté) |
| `/verifiez-votre-email/` | Saisie du code de confirmation |
| `/accueil/` | Tableau de bord / analyse plagiat |
| `/historique/` | Historique |
| `/rapport/<id>/` | Détail d’un rapport |
| `/reglages/`, `/reglages/plagiat/` | Réglages |
| `/abonnement/` | Tarification et abonnement |
| `/detecteur-ia/`, `/detecteur-plagiat/` | Détecteurs (accès premium selon abonnement) |
| `/rapport-ia/` | Rapport détecteur IA (après analyse) |
| `/mot-de-passe-oublie/` | Réinitialisation du mot de passe |
| `/admin/` | Administration Django |

Les routes API incluent notamment `/api/analyser/` (plagiat) et `/api/detecteur-plagiat/sapling/` (IA).

---

## Fonctionnalités détaillées

### Analyse de plagiat

- Contraintes de longueur (nombre de mots) côté client et serveur.
- Option d’URLs cibles pour affiner la comparaison.
- Pipeline dans `accounts/plagiarism_service.py` et services associés ; recherche via `accounts/tavily_search.py`.

### Détecteur IA

- Appels à `accounts/sapling_service.py`.
- Analyse par segments pour lisser le score ; indicateur de stabilité entre segments dans les conseils du rapport si besoin.

### Abonnement

- Modèle `AbonnementWaafi` : plan, statut, dates, référence Waafi.
- Actions admin : activation / désactivation pour simulation sans compte marchand réel.
- Context processor `subscription_context` : variable `has_abonnement_actif` pour afficher les entrées premium dans les menus.

### E-mails

- Confirmation d’inscription : **code numérique** + page de validation.
- Mot de passe oublié : flux Django standard (`PasswordResetView`) avec templates dans `templates/registration/`.

---

## Sécurité et bonnes pratiques

- **`SECRET_KEY`** : à régénérer et isoler en production ; ne pas publier dans un rapport public.
- **Clés API** (recherche web, détecteur IA, Waafi) : uniquement dans `.env` ou un coffre-fort de secrets.
- **`DEBUG=False`** en production ; configurer `ALLOWED_HOSTS` et HTTPS.
- **CSRF** : activé ; les appels AJAX envoient le token CSRF (cookie + en-tête).
- **Mots de passe** : hachés par Django ; réinitialisation par jeton à usage limité dans le temps.

---

## Dépannage

| Problème | Piste |
|----------|--------|
| Erreur de connexion PostgreSQL | Vérifier que le service PostgreSQL tourne, que la base existe, et que `DATABASES` correspond. |
| 403 CSRF | Recharger la page après connexion ; vérifier `CSRF_TRUSTED_ORIGINS` derrière ngrok/HTTPS. |
| Liens vides dans les e-mails | Définir `SITE_URL` dans `.env`. |
| Détecteurs invisibles | Vérifier qu’un abonnement actif existe (admin ou paiement) et que `has_abonnement_actif` est vrai. |
| E-mails non reçus | Vérifier SMTP, dossier spam, et paramètres Gmail (mot de passe d’application). |

---

## Annexes pour le rapport

Éléments que vous pouvez développer dans le mémoire ou la soutenance :

1. **Cahier des charges** : objectifs, acteurs, contraintes (langue FR, monnaie Fdj, contexte Djibouti pour le paiement).
2. **Modèle de données** : schéma entité-association ou MCD (tables `UTILISATEUR`, `ANALYSE`, `ABONNEMENT_WAAFIPAY`, etc.).
3. **Diagrammes** : cas d’utilisation (inscription, analyse, abonnement), séquence pour une analyse complète.
4. **Choix techniques** : pourquoi Django, pourquoi APIs externes (recherche web, détecteur IA, Waafi).
5. **Tests** : manuels (parcours utilisateur), possibilité d’évoquer tests automatisés futurs.
6. **Limites** : dépendance aux APIs, coûts, précision des détecteurs, sécurité des clés.

---

## Licence et usage académique

Ce projet est réalisé dans un cadre **pédagogique** (maquette / projet de génie logiciel). L’usage commercial ou la redistribution nécessitent une validation juridique et la conformité aux conditions d’utilisation des services tiers intégrés.

---

**PlagGuard** — Projet génie logiciel — Documentation générée pour accompagner le rapport et la reprise du projet par d’autres développeurs ou le jury.
