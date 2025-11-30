from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from PIL import Image

from course.models import Program
from .validators import ASCIIUsernameValidator


LEVEL = settings.LEVEL_CHOICES

PROGRAM_LEVEL_MAP = {
    Program.TECNICATURA: getattr(settings, 'BACHELOR_DEGREE', 'Bachelor'),
    Program.LICENCIATURA: getattr(settings, 'MASTER_DEGREE', 'Master'),
}

class CustomUserManager(UserManager):
    def search(self, query=None):
        queryset = self.get_queryset()
        if query is not None:
            or_lookup = (
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
            )
            queryset = queryset.filter(or_lookup).distinct()
        return queryset

    def get_student_count(self):
        return self.model.objects.filter(is_student=True).count()

    def get_lecturer_count(self):
        return self.model.objects.filter(is_lecturer=True).count()

    def get_superuser_count(self):
        return self.model.objects.filter(is_superuser=True).count()


GENDERS = (
    (_("F"), _("Femenino")),
    (_("M"), _("Masculino")),
    (_("X"), _("X")),
)


class User(AbstractUser):
    class Roles(models.TextChoices):
        ADMIN = "ADMIN", _("Administrador")
        COORDINATOR = "COORDINATOR", _("Coordinador")
        BEDEL = "BEDEL", _("Bedel")
        MANAGEMENT = "MANAGEMENT", _("Gestión")
        TEACHER = "TEACHER", _("Docente")
        STUDENT = "STUDENT", _("Alumno")

        @classmethod
        def staff_choices(cls):
            return [
                (cls.COORDINATOR, cls.COORDINATOR.label),
                (cls.BEDEL, cls.BEDEL.label),
                (cls.MANAGEMENT, cls.MANAGEMENT.label),
                (cls.TEACHER, cls.TEACHER.label),
            ]

    role = models.CharField(
        max_length=32,
        choices=Roles.choices,
        default=Roles.MANAGEMENT,
        help_text=_("Define el tipo de usuario dentro del sistema."),
    )
    is_student = models.BooleanField(default=False)
    is_lecturer = models.BooleanField(default=False)
    is_dep_head = models.BooleanField(default=False)
    gender = models.CharField(max_length=1, choices=GENDERS, blank=True, null=True)
    phone = models.CharField(max_length=60, blank=True, null=True)
    address = models.CharField(max_length=120, blank=True, null=True)
    locality = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        help_text=_("Localidad de residencia (solo para alumnos)."),
    )
    nationality = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        help_text=_("Nacionalidad (solo para alumnos)."),
    )
    dni = models.CharField(max_length=32, blank=True, null=True, unique=True)
    picture = models.ImageField(
        upload_to="profile_pictures/%y/%m/%d/", default="default.png", null=True
    )
    email = models.EmailField(blank=True, null=True)
    emergency_contact = models.CharField(max_length=120, blank=True, null=True)
    is_role_active = models.BooleanField(
        default=True,
        help_text=_("Activa o desactiva la participación según el rol (Bedel, Docente, etc.)."),
    )
    must_change_password = models.BooleanField(
        default=False,
        help_text=_("Debe cambiar la contraseña en el próximo inicio de sesión."),
    )
    programs_as_teacher = models.ManyToManyField(
        Program,
        blank=True,
        related_name="teachers",
        help_text=_("Carreras donde dicta clases."),
    )

    username_validator = ASCIIUsernameValidator()

    objects = CustomUserManager()

    class Meta:
        ordering = ("-date_joined",)

    @property
    def programs_as_coordinator(self):
        return self.programs_coordinated.all()

    ROLE_REQUIRED_FIELDS = {
        Roles.ADMIN: ["first_name", "last_name", "email", "phone", "dni"],
        Roles.COORDINATOR: ["first_name", "last_name", "email", "phone", "dni"],
        Roles.BEDEL: ["first_name", "last_name", "email", "phone", "dni"],
        Roles.MANAGEMENT: ["first_name", "last_name", "email", "phone", "dni"],
        Roles.TEACHER: ["first_name", "last_name", "email", "phone", "dni"],
        Roles.STUDENT: [
            "first_name",
            "last_name",
            "email",
            "dni",
            # gender y programs se gestionan aparte y pueden no venir en importación masiva
        ],
    }

    @property
    def get_full_name(self):
        full_name = self.username
        if self.first_name and self.last_name:
            full_name = self.first_name + " " + self.last_name
        return full_name

    def __str__(self):
        return f"{self.username} ({self.get_full_name})"

    @property
    def get_user_role(self):
        if self.is_superuser:
            return _("Administrador")
        return dict(self.Roles.choices).get(self.role, _("Sin rol"))

    def get_picture(self):
        try:
            return self.picture.url
        except Exception:
            no_picture = settings.MEDIA_URL + "default.png"
            return no_picture

    def get_absolute_url(self):
        return reverse("profile_single", kwargs={"user_id": self.id})

    def _sync_role_flags(self):
        self.is_student = self.role == self.Roles.STUDENT
        self.is_lecturer = self.role == self.Roles.TEACHER
        self.is_dep_head = self.role == self.Roles.COORDINATOR

    def clean(self):
        super().clean()
        required_fields = self.ROLE_REQUIRED_FIELDS.get(self.role, [])
        errors = {}
        for field in required_fields:
            if field == "programs":
                # Los programas se gestionan en el perfil Student, no en User
                continue
            value = getattr(self, field, None)
            if not value:
                errors[field] = _("Campo obligatorio para el rol seleccionado.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self._sync_role_flags()
        update_fields = kwargs.get("update_fields")
        if update_fields and set(update_fields) == {"last_login"}:
            # No validar campos requeridos en el cierre de sesión/actualización de último login
            return super().save(*args, **kwargs)
        self.full_clean()
        super().save(*args, **kwargs)
        try:
            img = Image.open(self.picture.path)
            if img.height > 300 or img.width > 300:
                output_size = (300, 300)
                img.thumbnail(output_size)
                img.save(self.picture.path)
        except Exception:
            pass

    def delete(self, *args, **kwargs):
        try:
            if self.picture.url != settings.MEDIA_URL + "default.png":
                self.picture.delete()
        except Exception:
            pass
        super().delete(*args, **kwargs)


class StudentManager(models.Manager):
    def search(self, query=None):
        qs = self.get_queryset()
        if query is not None:
            or_lookup = Q(level__icontains=query) | Q(program__icontains=query)
            qs = qs.filter(or_lookup).distinct()
        return qs


class Student(models.Model):
    student = models.OneToOneField(User, on_delete=models.CASCADE)
    legajo = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name=_("Legajo"),
        help_text=_("Número de legajo del estudiante (opcional)."),
    )
    level = models.CharField(max_length=25, choices=LEVEL, null=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, null=True)
    programs = models.ManyToManyField(
        Program,
        blank=True,
        related_name="students",
        help_text=_("Carreras en las que está inscripto el alumno."),
    )

    objects = StudentManager()

    class Meta:
        ordering = ("-student__date_joined",)

    def __str__(self):
        return self.student.get_full_name

    @classmethod
    def get_gender_count(cls):
        males_count = cls.objects.filter(student__gender="M").count()
        females_count = cls.objects.filter(student__gender="F").count()
        return {"M": males_count, "F": females_count}

    def get_absolute_url(self):
        return reverse("profile_single", kwargs={"user_id": self.id})

    def save(self, *args, **kwargs):
        # Si no hay programa principal pero hay lista de programas, tomar el primero
        if not self.program_id and self.pk:
            first_program = self.programs.order_by("id").first()
            if first_program:
                self.program = first_program
        if self.program_id:
            self.level = PROGRAM_LEVEL_MAP.get(
                self.program.program_type,
                self.level,
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.student.delete()
        super().delete(*args, **kwargs)


class DepartmentHead(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    department = models.ForeignKey(Program, on_delete=models.CASCADE, null=True)

    class Meta:
        ordering = ("-user__date_joined",)

    def __str__(self):
        return str(self.user)
