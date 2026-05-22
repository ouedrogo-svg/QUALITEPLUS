from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from .models import get_user_subscribed_months, user_has_active_subscription

_ADMIN_EXAM_RECAP_CACHE_KEY = "courses:admin_exam_recap_tree_compact"
_ADMIN_SUBSCRIPTION_RECAP_CACHE_KEY = "courses:admin_subscription_recap_tree_compact"
_ADMIN_RECAP_CACHE_SECONDS = 300


def _admin_paths_needing_recap(path: str) -> bool:
    """Récap admin uniquement sur l’accueil (évite de ralentir chaque page /admin/…)."""
    if path in ("/admin/", "/admin"):
        return True
    return False


def subscription(request):
    user = request.user
    subscribed = get_user_subscribed_months(user) if user.is_authenticated else []
    subscribed_keys = {f"{m['year']}-{m['month']}" for m in subscribed}
    return {
        "has_active_subscription": user_has_active_subscription(user),
        "subscribed_months": subscribed,
        "subscribed_month_keys": subscribed_keys,
    }


def formateur_nav(request):
    """Liens des espaces formateur dans l’en-tête du site."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {
            "show_formateur_space": False,
            "show_formateur_contenu_space": False,
        }
    if getattr(user, "is_staff", False):
        return {
            "show_formateur_space": True,
            "show_formateur_contenu_space": True,
        }
    profile = getattr(user, "profile", None)
    if profile is None:
        try:
            profile = user.profile
        except ObjectDoesNotExist:
            profile = None
    if profile is None:
        return {
            "show_formateur_space": False,
            "show_formateur_contenu_space": False,
        }
    full = bool(profile.is_platform_formateur)
    contenu = bool(profile.is_content_formateur)
    return {
        "show_formateur_space": full,
        "show_formateur_contenu_space": contenu and not full,
    }


def formateur_space(request):
    """Contexte gabarits : pas d’onglet abonnements sur l’accueil formateur."""
    path = getattr(request, "path", "") or ""
    if path.startswith("/espace-formateur-contenu"):
        return {"show_formateur_subscriptions": False}
    if path in ("/espace-formateur/", "/espace-formateur"):
        return {"show_formateur_subscriptions": False}
    if path.startswith("/espace-formateur/"):
        return {"show_formateur_subscriptions": True}
    return {}


def admin_exam_recap(request):
    """Récapitulatifs compacts sur l’accueil admin uniquement."""
    path = getattr(request, "path", "") or ""
    if not _admin_paths_needing_recap(path):
        return {"show_admin_recap_header": False}
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_staff:
        return {"show_admin_recap_header": False}
    from .exam_results import build_admin_exam_recap_tree
    from .subscription_recap import (
        build_admin_subscription_recap_tree,
        subscription_recap_global_export_url,
    )

    exam_recap = cache.get(_ADMIN_EXAM_RECAP_CACHE_KEY)
    if exam_recap is None:
        exam_recap = build_admin_exam_recap_tree(compact=True)
        cache.set(_ADMIN_EXAM_RECAP_CACHE_KEY, exam_recap, _ADMIN_RECAP_CACHE_SECONDS)

    subscription_recap = cache.get(_ADMIN_SUBSCRIPTION_RECAP_CACHE_KEY)
    if subscription_recap is None:
        subscription_recap = build_admin_subscription_recap_tree(include_rows=False)
        cache.set(
            _ADMIN_SUBSCRIPTION_RECAP_CACHE_KEY,
            subscription_recap,
            _ADMIN_RECAP_CACHE_SECONDS,
        )

    return {
        "show_admin_recap_header": True,
        "admin_exam_recap": exam_recap,
        "admin_subscription_recap": subscription_recap,
        "admin_subscription_recap_export_url": subscription_recap_global_export_url(),
    }
