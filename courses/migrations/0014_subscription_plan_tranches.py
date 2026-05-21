from django.db import migrations, models


def populate_plan_names(apps, schema_editor):
    SubscriptionPlan = apps.get_model("courses", "SubscriptionPlan")
    for plan in SubscriptionPlan.objects.all():
        if plan.name:
            continue
        if plan.billing_period == "yearly" and plan.included_months > 1:
            plan.name = f"Annuel ({plan.included_months} mois)"
        elif plan.billing_period == "yearly":
            plan.name = "Annuel"
        elif plan.billing_period == "monthly":
            plan.name = "Mensuel"
        else:
            plan.name = "Formule d’abonnement"
        plan.save(update_fields=["name"])


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0013_plan_included_months"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscriptionplan",
            name="name",
            field=models.CharField(
                blank=True,
                help_text="Ex. « Pack 1er semestre », « 3 mois au choix ».",
                max_length=120,
                verbose_name="nom de la tranche",
            ),
        ),
        migrations.AlterField(
            model_name="subscriptionplan",
            name="billing_period",
            field=models.CharField(
                blank=True,
                choices=[("monthly", "Mensuel"), ("yearly", "Annuel")],
                default="",
                help_text="Laissé vide pour les tranches avec mois personnalisés. "
                "Conservé pour compatibilité avec d’anciennes formules.",
                max_length=20,
                verbose_name="période (ancien format)",
            ),
        ),
        migrations.AlterField(
            model_name="subscriptionplan",
            name="included_months",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="Utilisé uniquement si aucun mois n’est défini dans la liste ci-dessous "
                "(formules mensuelles / annuelles héritées).",
                verbose_name="nombre de mois inclus (ancien format)",
            ),
        ),
        migrations.AlterModelOptions(
            name="subscriptionplan",
            options={
                "ordering": ["name", "billing_period", "id"],
                "verbose_name": "option d’abonnement",
                "verbose_name_plural": "options d’abonnement",
            },
        ),
        migrations.RunPython(populate_plan_names, migrations.RunPython.noop),
        migrations.CreateModel(
            name="SubscriptionPlanMonth",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "month",
                    models.PositiveIntegerField(
                        choices=[
                            (1, "janvier"),
                            (2, "février"),
                            (3, "mars"),
                            (4, "avril"),
                            (5, "mai"),
                            (6, "juin"),
                            (7, "juillet"),
                            (8, "août"),
                            (9, "septembre"),
                            (10, "octobre"),
                            (11, "novembre"),
                            (12, "décembre"),
                        ],
                        verbose_name="mois",
                    ),
                ),
                (
                    "year",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Facultatif : si vide, l’année du mois choisi par le candidat est utilisée.",
                        null=True,
                        verbose_name="année",
                    ),
                ),
                (
                    "plan",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="included_periods",
                        to="courses.subscriptionplan",
                        verbose_name="tranche",
                    ),
                ),
            ],
            options={
                "verbose_name": "mois inclus",
                "verbose_name_plural": "mois inclus",
                "ordering": ["year", "month", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="subscriptionplanmonth",
            constraint=models.UniqueConstraint(
                fields=("plan", "year", "month"),
                name="unique_plan_included_period",
            ),
        ),
    ]
