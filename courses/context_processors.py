from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from .models import get_user_subscribed_months, user_has_active_subscription

_ADMIN_EXAM_RECAP_CACHE_KEY = "courses:admin_exam_recap_tree_full"
_ADMIN_SUBSCRIPTION_RECAP_CACHE_KEY = "courses:admin_subscription_recap_tree_compact"
_ADMIN_RECAP_CACHE_SECONDS = 300


def _is_admin_index(path: str) -> bool:
    return path in ("/admin/", "/admin")


def _is_admin_exam_recap_page(path: str) -> bool:
    return path.rstrip("/") == "/admin/exam-results-recap"


def _is_admin_area(path: str) -> bool:
    if not path.startswith("/admin"):
        return False
    if "/login" in path or "jsi18n" in path:
        return False
    return True


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
    """Récap examens et abonnements dans l’interface admin."""
    path = getattr(request, "path", "") or ""
    if not _is_admin_area(path):
        return {}

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_staff:
        return {}

    ctx = {
        "show_admin_recap_banner": True,
        "show_admin_exam_recap": False,
        "show_admin_subscription_recap": False,
        "admin_exam_recap": [],
        "admin_subscription_recap": [],
        "admin_subscription_recap_export_url": "",
    }

    if _is_admin_exam_recap_page(path):
        from .admin_views import get_admin_exam_recap_tree

        ctx["show_admin_exam_recap"] = True
        ctx["admin_exam_recap"] = get_admin_exam_recap_tree(
            force_refresh=request.GET.get("refresh") == "1"
        )
        return ctx

    if _is_admin_index(path):
        from .subscription_recap import (
            build_admin_subscription_recap_tree,
            subscription_recap_global_export_url,
        )

        subscription_recap = cache.get(_ADMIN_SUBSCRIPTION_RECAP_CACHE_KEY)
        if subscription_recap is None:
            subscription_recap = build_admin_subscription_recap_tree(
                include_rows=False
            )
            cache.set(
                _ADMIN_SUBSCRIPTION_RECAP_CACHE_KEY,
                subscription_recap,
                _ADMIN_RECAP_CACHE_SECONDS,
            )
        ctx["show_admin_subscription_recap"] = True
        ctx["admin_subscription_recap"] = subscription_recap
        ctx["admin_subscription_recap_export_url"] = (
            subscription_recap_global_export_url()
        )

    return ctx
