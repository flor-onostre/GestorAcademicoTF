from django.db import migrations


def create_turns(apps, schema_editor):
    Turn = apps.get_model("course", "Turn")
    defaults = [
        ("MORNING", "Mañana"),
        ("AFTERNOON", "Tarde"),
        ("EVENING", "Noche"),
    ]
    for code, name in defaults:
        Turn.objects.update_or_create(code=code, defaults={"name": name})


class Migration(migrations.Migration):

    dependencies = [
        ("course", "0015_alter_coursesection_options_and_more"),
    ]

    operations = [
        migrations.RunPython(create_turns, migrations.RunPython.noop),
    ]
