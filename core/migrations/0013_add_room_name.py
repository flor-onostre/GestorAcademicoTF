from django.db import migrations, models


def set_room_name(apps, schema_editor):
    Room = apps.get_model("core", "Room")
    for room in Room.objects.all():
        if not room.name:
            room.name = room.code
            room.save(update_fields=["name"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_remove_semester_next_semester_begins_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="room",
            name="name",
            field=models.CharField(
                default="",
                max_length=120,
                verbose_name="Nombre",
                help_text=(
                    "Nombre del espacio (ej: Aula 101, Laboratorio de química, Auditorio)."
                ),
            ),
            preserve_default=False,
        ),
        migrations.RunPython(set_room_name, migrations.RunPython.noop),
    ]
