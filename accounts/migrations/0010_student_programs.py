from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("course", "0012_course_prerequisites_course_programs_and_more"),
        ("accounts", "0009_alter_user_gender_choices"),
    ]

    operations = [
        migrations.AddField(
            model_name="student",
            name="programs",
            field=models.ManyToManyField(
                blank=True,
                help_text="Carreras en las que está inscripto el alumno.",
                related_name="students",
                to="course.program",
            ),
        ),
    ]
