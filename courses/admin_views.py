"""Vues personnalisées pour l’interface d’administration Django."""

from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.shortcuts import render

from .exam_results import build_admin_exam_recap_tree

_ADMIN_EXAM_RECAP_CACHE_KEY = "courses:admin_exam_recap_tree_full"
_ADMIN_EXAM_RECAP_CACHE_SECONDS = 300


def get_admin_exam_recap_tree(*, force_refresh: bool = False) -> list[dict]:
    if not force_refresh:
        cached = cache.get(_ADMIN_EXAM_RECAP_CACHE_KEY)
        if cached is not None:
            return cached
    tree = build_admin_exam_recap_tree(compact=False)
    cache.set(_ADMIN_EXAM_RECAP_CACHE_KEY, tree, _ADMIN_EXAM_RECAP_CACHE_SECONDS)
    return tree


def invalidate_admin_exam_recap_cache() -> None:
    cache.delete(_ADMIN_EXAM_RECAP_CACHE_KEY)


@staff_member_required
def admin_exam_results_recap_view(request):
    """Récap global : catégorie → mois → examen → nom, prénom, note, classement."""
    if request.GET.get("refresh") == "1":
        invalidate_admin_exam_recap_cache()
    tree = get_admin_exam_recap_tree(
        force_refresh=request.GET.get("refresh") == "1"
    )
    return render(
        request,
        "admin/exam_results_recap_page.html",
        {
            "title": "Récapitulatif des résultats d’examens",
            "admin_exam_recap": tree,
            "show_admin_recap_banner": True,
            "show_admin_exam_recap": True,
            "show_admin_subscription_recap": False,
        },
    )
