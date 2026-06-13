from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import UserSubscription, SubscriptionRequest
from accounts.models import UserProfile

def invalidate_user_prefetch_cache(user_id):
    """Invalidate all cached info for a specific user to prevent stale views."""
    cache.delete(f"user_prefetch_data_{user_id}")
    cache.delete(f"user_subscribed_months_{user_id}")
    cache.delete(f"home_categories_{user_id}")
    # Also invalidate global and admin recaps as they count on request updates
    cache.delete("courses:admin_subscription_recap_tree_compact")
    cache.delete("courses:admin_exam_recap_tree_full")
    cache.delete("home_categories_anon")
    cache.delete("home_subscription_plans")

@receiver(post_save, sender=UserSubscription)
@receiver(post_delete, sender=UserSubscription)
def on_subscription_change(sender, instance, **kwargs):
    invalidate_user_prefetch_cache(instance.user_id)

@receiver(post_save, sender=SubscriptionRequest)
@receiver(post_delete, sender=SubscriptionRequest)
def on_request_change(sender, instance, **kwargs):
    invalidate_user_prefetch_cache(instance.user_id)

@receiver(post_save, sender=UserProfile)
@receiver(post_delete, sender=UserProfile)
def on_profile_change(sender, instance, **kwargs):
    invalidate_user_prefetch_cache(instance.user_id)
