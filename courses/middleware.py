"""Précharge les abonnements mensuels pour éviter une requête par vue / context processor."""


from django.db.models import Prefetch
from django.core.cache import cache

class PrefetchUserSubscriptionMiddleware:
    """
    Précharge le profil et les abonnements pour éviter les requêtes N+1 dans les context processors.
    Utilise un cache court pour éviter de re-requêter la DB à chaque chargement de page.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            # On utilise un cache court (60s) pour éviter de refaire ces jointures lourdes sur chaque clic.
            cache_key = f"user_prefetch_data_{user.pk}"
            cached_user = cache.get(cache_key)
            
            if cached_user:
                request.user = cached_user
            else:
                from .models import UserSubscription
                
                # On récupère l'utilisateur avec son profil et ses abonnements en UNE SEULE requête complexe.
                user_qs = user.__class__.objects.filter(pk=user.pk).select_related('profile').prefetch_related(
                    Prefetch(
                        'month_subscriptions',
                        queryset=UserSubscription.objects.select_related('category', 'plan').order_by('-year', '-month', 'category__name')
                    )
                )
                optimized_user = user_qs.first()
                if optimized_user:
                    request.user = optimized_user
                    # Mise en cache pour 1 minute pour fluidifier la navigation.
                    cache.set(cache_key, optimized_user, 60)
                
        return self.get_response(request)
