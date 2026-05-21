from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0015_subscription_plan_start_period"),
    ]

    operations = [
        migrations.AddField(
            model_name="monthlycorrection",
            name="duration_minutes",
            field=models.PositiveIntegerField(
                default=60,
                help_text="Temps imparti au candidat pour valider le quiz une fois l’épreuve commencée.",
                verbose_name="durée du quiz (minutes)",
            ),
        ),
    ]
