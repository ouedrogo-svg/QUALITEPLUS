import logging
from django.core.management.base import BaseCommand
from courses.models import Category, MonthlyCorrection, MonthlyExam
from courses.pdf_quiz_import import (
    force_rebuild_quiz_from_correction_pdf,
    force_rebuild_quiz_from_exam_pdf,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reconstruit entièrement les quiz à partir de leurs PDF sources avec le nouveau parseur propre."

    def add_arguments(self, parser):
        parser.add_argument(
            "--category",
            type=str,
            help="Slug ou nom de la catégorie (ex: 'tresor', 'finances', 'gsp'). Si omis, prend en compte toutes les catégories ou celles spécifiées.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Reconstruire les quiz de toutes les catégories.",
        )
        parser.add_argument(
            "--only-corrections",
            action="store_true",
            help="Reconstruire uniquement les quiz des corrections mensuelles.",
        )
        parser.add_argument(
            "--only-exams",
            action="store_true",
            help="Reconstruire uniquement les quiz des examens.",
        )

    def handle(self, *args, **options):
        category_arg = options.get("category")
        rebuild_all = options.get("all")
        only_corrections = options.get("only_corrections")
        only_exams = options.get("only_exams")

        if not category_arg and not rebuild_all:
            self.stdout.write(
                self.style.WARNING(
                    "Veuillez spécifier --category <nom/slug> ou --all pour reconstruire tous les quiz."
                )
            )
            return

        cat_qs = Category.objects.all()
        if category_arg:
            cat_qs = cat_qs.filter(
                slug__iexact=category_arg
            ) | cat_qs.filter(name__iexact=category_arg)
            if not cat_qs.exists():
                self.stdout.write(
                    self.style.ERROR(f"Aucune catégorie trouvée pour '{category_arg}'.")
                )
                return

        categories = list(cat_qs)
        self.stdout.write(
            self.style.SUCCESS(
                f"Reconstruction lancée pour {len(categories)} catégorie(s) : {[c.name for c in categories]}"
            )
        )

        total_corrections_done = 0
        total_exams_done = 0

        for cat in categories:
            self.stdout.write(f"\n--- Catégorie: {cat.name} ---")

            if not only_exams:
                corrections = MonthlyCorrection.objects.filter(
                    category=cat, pdf__isnull=False
                ).exclude(pdf="").order_by("year", "month", "title")
                self.stdout.write(f"Trouvé {corrections.count()} corrections avec PDF.")

                for corr in corrections:
                    self.stdout.write(
                        f"  -> Reconstruction de la correction {corr.title} ({corr.year}-{corr.month:02d})... ",
                        ending="",
                    )
                    self.stdout.flush()
                    try:
                        n_q = force_rebuild_quiz_from_correction_pdf(corr)
                        self.stdout.write(self.style.SUCCESS(f"OK ({n_q} questions)"))
                        total_corrections_done += 1
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"ERREUR: {e}"))
                        logger.exception("Erreur reconstruction correction %s", corr.pk)

            if not only_corrections:
                exams = MonthlyExam.objects.filter(
                    category=cat, pdf__isnull=False
                ).exclude(pdf="").order_by("year", "month", "title")
                self.stdout.write(f"Trouvé {exams.count()} examens avec PDF.")

                for ex in exams:
                    self.stdout.write(
                        f"  -> Reconstruction de l'examen {ex.title} ({ex.year}-{ex.month:02d})... ",
                        ending="",
                    )
                    self.stdout.flush()
                    try:
                        n_q = force_rebuild_quiz_from_exam_pdf(ex)
                        self.stdout.write(self.style.SUCCESS(f"OK ({n_q} questions)"))
                        total_exams_done += 1
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"ERREUR: {e}"))
                        logger.exception("Erreur reconstruction examen %s", ex.pk)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nTerminé ! {total_corrections_done} corrections et {total_exams_done} examens reconstruits."
            )
        )
