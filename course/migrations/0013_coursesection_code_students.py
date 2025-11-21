from django.db import migrations, models
from django.conf import settings

class Migration(migrations.Migration):
    dependencies = [
        ('course', '0012_course_prerequisites_course_programs_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='coursesection',
            name='code',
            field=models.CharField(
                max_length=50,
                unique=True,
                null=True,
                blank=True,
                help_text='Código identificador de la comisión.',
            ),
        ),
        migrations.AddField(
            model_name='coursesection',
            name='students',
            field=models.ManyToManyField(
                blank=True,
                help_text='Seleccione los alumnos inscriptos en esta comisión.',
                limit_choices_to={'role': 'STUDENT'},
                related_name='sections_enrolled',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Alumnos',
            ),
        ),
    ]
