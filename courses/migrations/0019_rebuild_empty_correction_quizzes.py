from django.db import migrations


def rebuild_empty_quizzes(apps, schema_editor):
    try:
        from courses.models import MonthlyCorrection
        from courses.pdf_quiz_import import force_rebuild_quiz_from_correction_pdf

        # Reconstruire les quiz vides ou manquants pour les corrections existantes
        for corr in MonthlyCorrection.objects.filter(pdf__isnull=False).exclude(pdf=""):
            quiz = getattr(corr, "quiz", None)
            if not quiz or quiz.questions.count() == 0:
                try:
                    force_rebuild_quiz_from_correction_pdf(corr)
                except Exception:
                    pass
    except Exception:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0018_subscriptionrequest_courses_sub_status_e90e81_idx"),
    ]

    operations = [
        migrations.RunPython(rebuild_empty_quizzes, reverse_code=migrations.RunPython.noop),
    ]
