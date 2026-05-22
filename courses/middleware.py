"""Précharge les abonnements mensuels pour éviter une requête par vue / context processor."""


class PrefetchUserSubscriptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            prefetch_cache = getattr(user, "_prefetched_objects_cache", None)
            if not prefetch_cache or "month_subscriptions" not in prefetch_cache:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                request.user = (
                    User.objects.select_related("profile")
                    .prefetch_related("month_subscriptions__category")
                    .get(pk=user.pk)
                )
        return self.get_response(request)
