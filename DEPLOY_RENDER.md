# Guide de déploiement sur Render

## Prérequis

1. **Compte Render** : https://render.com
2. **Compte Cloudinary** : https://cloudinary.com
3. **Repository Git** : Le projet doit être sur GitHub/GitLab/Bitbucket

## Étape 1 : Configurer les variables d'environnement sur Render

Dans le dashboard Render → **Environment** de votre service web, ajoutez les variables suivantes :

### Variables requises

| Variable | Description | Exemple |
|----------|-------------|---------|
| `SECRET_KEY` | Clé secrète Django | `django-insecure-xxx` (générez une clé sécurisée) |
| `DEBUG` | Mode debug | `False` |
| `ALLOWED_HOSTS` | Hôtes autorisés | `votre-app.onrender.com` |
| `DATABASE_URL` | URL PostgreSQL | Fourni automatiquement par Render |
| `CLOUDINARY_CLOUD_NAME` | Nom Cloudinary | `dysbapnpz` |
| `CLOUDINARY_API_KEY` | Clé API Cloudinary | `667772298733217` |
| `CLOUDINARY_API_SECRET` | Secret API Cloudinary | `9_haPAWa7viEHGeIt_8k2Zmrcb8` |

### Générer une SECRET_KEY sécurisée

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Étape 2 : Créer un nouveau service Web sur Render

1. Allez sur https://dashboard.render.com
2. Cliquez sur **New** → **Web Service**
3. Connectez votre repository Git
4. Configurez :

| Option | Valeur |
|--------|-------|
| **Name** | `qualiteplus` (ou autre nom) |
| **Region** | Choisissez la région la plus proche |
| **Branch** | `main` |
| **Root Directory** | Laissez vide (racine du repo) |
| **Runtime** | Python |
| **Build Command** | `./build.sh` |
| **Start Command** | `gunicorn config.wsgi:application` |

5. Cliquez sur **Create Web Service**

## Étape 3 : Vérifier le déploiement

Render va automatiquement :
- Installer les dépendances (`requirements.txt`)
- Exécuter `collectstatic`
- Exécuter les migrations (`migrate`)
- Démarrer le serveur avec `gunicorn`

## Étape 4 : Configurer ALLOWED_HOSTS

Une fois le service créé, récupérez l'URL de votre application (ex: `https://qualiteplus.onrender.com`) et mettez à jour la variable `ALLOWED_HOSTS` :

```
ALLOWED_HOSTS=qualiteplus.onrender.com
```

## Étape 5 : Vérifier les fichiers

Les fichiers sont maintenant stockés sur Cloudinary et ne seront pas perdus lors des redéploiements.

## Dépannage

### Erreur : ModuleNotFoundError

Vérifiez que `requirements.txt` contient toutes les dépendances.

### Erreur : Fichiers introuvables

Vérifiez que les variables Cloudinary sont correctement configurées.

### Erreur : ALLOWED_HOSTS

Assurez-vous que le domaine Render est dans `ALLOWED_HOSTS`.

### Logs de déploiement

Consultez les logs dans le dashboard Render → **Logs**.

## Commandes utiles en local

```bash
# Tester la configuration locale
python manage.py check

# Vérifier les variables d'environnement
python -c "from django.conf import settings; print(settings.CLOUDINARY_STORAGE)"
```
