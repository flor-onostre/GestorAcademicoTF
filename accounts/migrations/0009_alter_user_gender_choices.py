from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_user_locality_user_nationality"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[("F", "Femenino"), ("M", "Masculino"), ("X", "X")],
                max_length=1,
                null=True,
            ),
        ),
    ]
