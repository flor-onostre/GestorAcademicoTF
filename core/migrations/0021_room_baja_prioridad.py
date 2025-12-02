from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_bulkuploadrequest_processed_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="room",
            name="baja_prioridad",
            field=models.BooleanField(
                default=False,
                help_text="Marcar si el aula es de uso preferente solo si no hay otras opciones.",
            ),
        ),
    ]
