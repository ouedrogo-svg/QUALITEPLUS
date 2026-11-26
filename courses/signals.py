import logging
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import UserSubscription, SubscriptionRequest, MonthlyCorrection, MonthlyExam
from .background_tasks import defer_to_background
from accounts.models import UserProfile

logger = logging.getLogger(__name__)

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


@receiver(post_save, sender=MonthlyCorrection)
def on_correction_post_save(sender, instance, created, **kwargs):
    if not instance.pdf:
        return
    has_quiz = hasattr(instance, "quiz") and instance.quiz and instance.quiz.questions.exists()
    if not has_quiz or created:
        pk = instance.pk

        def _sync():
            from .models import MonthlyCorrection
            from .pdf_quiz_import import force_rebuild_quiz_from_correction_pdf

            try:
                corr = MonthlyCorrection.objects.get(pk=pk)
                force_rebuild_quiz_from_correction_pdf(corr)
            except Exception:
                logger.exception("Erreur lors de la synchronisation automatique du quiz pour la correction %s", pk)

        transaction.on_commit(lambda: defer_to_background(_sync))


@receiver(post_save, sender=MonthlyExam)
def on_exam_post_save(sender, instance, created, **kwargs):
    if not instance.pdf:
        return
    has_quiz = hasattr(instance, "quiz") and instance.quiz and instance.quiz.questions.exists()
    if not has_quiz or created:
        pk = instance.pk

        def _sync():
            from .models import MonthlyExam
            from .pdf_quiz_import import force_rebuild_quiz_from_exam_pdf

            try:
                exam = MonthlyExam.objects.get(pk=pk)
                force_rebuild_quiz_from_exam_pdf(exam)
            except Exception:
                logger.exception("Erreur lors de la synchronisation automatique du quiz pour l'examen %s", pk)

        transaction.on_commit(lambda: defer_to_background(_sync))
