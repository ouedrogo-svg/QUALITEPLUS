from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0014_subscription_plan_tranches"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscriptionplan",
            name="start_month",
            field=models.PositiveIntegerField(
                blank=True,
                choices=[
                    (1, "Janvier"),
                    (2, "Février"),
                    (3, "Mars"),
                    (4, "Avril"),
                    (5, "Mai"),
                    (6, "Juin"),
                    (7, "Juillet"),
                    (8, "Août"),
                    (9, "Septembre"),
                    (10, "Octobre"),
                    (11, "Novembre"),
                    (12, "Décembre"),
                ],
                help_text="Annuel ou tranche : mois de départ des périodes accordées.",
                null=True,
                verbose_name="mois de départ",
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="start_year",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Annuel ou tranche : année du premier mois accordé (défini par l’administrateur).",
                null=True,
                verbose_name="année de départ",
            ),
        ),
        migrations.AlterField(
            model_name="subscriptionplan",
            name="included_months",
            field=models.PositiveSmallIntegerField(
                default=12,
                help_text="Si type Annuel et aucun mois listé ci-dessous : nombre de mois "
                "consécutifs à partir du mois de départ ci-dessus.",
                verbose_name="mois consécutifs (annuel, sans liste)",
            ),
        ),
        migrations.AlterField(
            model_name="subscriptionplanmonth",
            name="year",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Facultatif : si vide, l’année de départ de la formule est utilisée.",
                null=True,
                verbose_name="année",
            ),
        ),
    ]
