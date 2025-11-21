from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_remove_user_programs_as_coordinator"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="locality",
            field=models.CharField(
                blank=True,
                help_text="Localidad de residencia (solo para alumnos).",
                max_length=120,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="nationality",
            field=models.CharField(
                blank=True,
                help_text="Nacionalidad (solo para alumnos).",
                max_length=120,
                null=True,
            ),
        ),
    ]
