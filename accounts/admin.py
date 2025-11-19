from django.contrib import admin
from .models import User, Student, Parent


class UserAdmin(admin.ModelAdmin):
    list_display = [
        "get_full_name",
        "username",
        "email",
        "is_active",
        "is_student",
        "is_lecturer",
        "is_parent",
        "is_staff",
    ]
    search_fields = [
        "username",
        "first_name",
        "last_name",
        "email",
        "is_active",
        "is_lecturer",
        "is_parent",
        "is_staff",
    ]
    # Texto visible en el buscador del admin (no cambia ninguna lógica)
    search_help_text = "Buscar por usuario, nombre, apellido, email, estado y rol."

    class Meta:
        managed = True
        verbose_name = "User"
        verbose_name_plural = "Users"


# Textos visibles en la cabecera del panel de administración
admin.site.site_header = "Administración de SkyLearn"
admin.site.site_title = "Admin SkyLearn"
admin.site.index_title = "Panel de administración"

admin.site.register(User, UserAdmin)
admin.site.register(Student)
admin.site.register(Parent)