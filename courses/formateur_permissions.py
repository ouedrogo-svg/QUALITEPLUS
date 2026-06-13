from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.shortcuts import get_object_or_404

from .models import Category


def _profile(user):
    try:
        return user.profile
    except ObjectDoesNotExist:
        return None


def user_can_access_full_formateur_space(user) -> bool:
    """
    Espace formateur complet (contenu + demandes d’abonnement + récap).
    Réservé aux super-utilisateurs ou aux formateurs plateforme.
    """
    if not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    profile = _profile(user)
    return bool(profile and profile.is_platform_formateur)


def user_can_access_content_formateur_space(user) -> bool:
    """Espace formateur contenu (sans gestion des demandes d’abonnement)."""
    if not user.is_authenticated:
        return False
    if user_can_access_full_formateur_space(user):
        return True
    profile = _profile(user)
    return bool(profile and profile.is_content_formateur)


# Alias historique
def user_can_access_formateur_space(user) -> bool:
    return user_can_access_full_formateur_space(user)


def formateur_has_unrestricted_categories(user) -> bool:
    """
    Seuls les super-utilisateurs ont un accès total et illimité à toutes les catégories.
    Les autres membres du personnel (is_staff) sont traités comme des formateurs
    et restreints à leurs catégories assignées dans les espaces dédiés.
    """
    return bool(user.is_authenticated and getattr(user, "is_superuser", False))


def formateur_space_assigned_only(request) -> bool:
    """Dans les espaces formateur : uniquement les catégories assignées au profil."""
    path = getattr(request, "path", "") or ""
    return path.startswith("/espace-formateur")


def formateur_category_ids(user, *, assigned_only: bool = False) -> set[int] | None:
    """
    Identifiants des catégories accessibles.
    None = toutes (personnel ou administrateur).
    set() = aucune catégorie assignée.
    """
    if not user.is_authenticated:
        return set()
    
    # Les administrateurs et le personnel ont accès à TOUTES les catégories par défaut,
    # même si l'espace demande uniquement les catégories "assignées".
    if formateur_has_unrestricted_categories(user):
        return None
        
    profile = _profile(user)
    if not profile:
        return set()
    if hasattr(profile, "_prefetched_objects_cache") and "categories" in profile._prefetched_objects_cache:
        return {c.pk for c in profile.categories.all()}
    return set(profile.categories.values_list("pk", flat=True))


def scope_formateur_categories(
    qs, user, *, category_field="category_id", assigned_only: bool = False
):
    """Filtre un queryset lié à une catégorie selon le profil formateur."""
    ids = formateur_category_ids(user, assigned_only=assigned_only)
    if ids is None:
        # Administrateur : pas de filtrage, accès total.
        return qs
    if not ids:
        return qs.none()
    return qs.filter(**{f"{category_field}__in": ids})


def formateur_category_queryset(user, *, assigned_only: bool = False):
    """Queryset des catégories visibles dans l’espace formateur."""
    qs = Category.objects.all()
    ids = formateur_category_ids(user, assigned_only=assigned_only)
    if ids is None:
        return qs
    if not ids:
        return qs.none()
    return qs.filter(pk__in=ids)


def ensure_formateur_category_access(
    user, category, *, assigned_only: bool = False
) -> None:
    ids = formateur_category_ids(user, assigned_only=assigned_only)
    if ids is None:
        return
    if category.pk not in ids:
        raise PermissionDenied("Vous n’avez pas accès à cette catégorie.")


def get_formateur_category_or_404(user, pk, *, assigned_only: bool = False):
    cat = get_object_or_404(Category, pk=pk)
    ensure_formateur_category_access(user, cat, assigned_only=assigned_only)
    return cat


def get_formateur_object_or_404(
    user, model, pk, *, select_related=(), assigned_only: bool = False
):
    qs = model.objects.all()
    if select_related:
        qs = qs.select_related(*select_related)
    obj = get_object_or_404(qs, pk=pk)
    ensure_formateur_category_access(user, obj.category, assigned_only=assigned_only)
    return obj


def formateur_can_view_category_content(user, category: Category) -> bool:
    """
    Consultation du contenu public sans abonnement candidat,
    uniquement pour les catégories assignées au formateur ou pour les administrateurs.
    """
    if not user.is_authenticated:
        return False
    if not user_can_access_content_formateur_space(user):
        return False
    ids = formateur_category_ids(user, assigned_only=True)
    if ids is None:
        # Administrateur : accès à tout.
        return True
    return bool(ids) and category.pk in ids


def redirect_formateur_login(request):
    return redirect_to_login(request.get_full_path())
