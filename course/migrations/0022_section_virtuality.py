from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("course", "0017_coursesection_schedule_by_day_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="coursesection",
            name="virtual_days",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Días virtuales (no requieren aula) ej: ['Lunes', 'Miércoles'].",
            ),
        ),
        migrations.AddField(
            model_name="coursesection",
            name="virtual_from",
            field=models.DateField(blank=True, help_text="Fecha desde virtualidad (opcional).", null=True),
        ),
        migrations.AddField(
            model_name="coursesection",
            name="virtual_to",
            field=models.DateField(blank=True, help_text="Fecha hasta virtualidad (opcional).", null=True),
        ),
    ]
