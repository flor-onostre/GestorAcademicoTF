import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ==============================
# Constantes de cuatrimestre
# ==============================
FIRST = "FIRST"
SECOND = "SECOND"
SUMMER = "SUMMER"

SEMESTER = (
    (FIRST, _("1er Cuatrimestre")),
    (SECOND, _("2do Cuatrimestre")),
    (SUMMER, _("Materias de Verano")),
)

# ==============================
# Noticias / Eventos
# ==============================
NEWS = _("News")
EVENTS = _("Event")

POST = ((NEWS, _("News")), (EVENTS, _("Event")))

# Roles y audiencias usadas en formularios/vistas
ADMIN_VIEW_ROLES = {"ADMIN", "MANAGEMENT", "BEDEL"}
PUBLISHER_ROLES = ADMIN_VIEW_ROLES | {"COORDINATOR", "TEACHER"}
COORDINATOR_ALLOWED_AUDIENCE = {"STUDENT", "TEACHER"}
TEACHER_ALLOWED_AUDIENCE = {"STUDENT"}


class NewsAndEventsQuerySet(models.QuerySet):
    def search(self, query):
        lookups = (
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(posted_as__icontains=query)
        )
        return self.filter(lookups).distinct()


class NewsAndEventsManager(models.Manager):
    def get_queryset(self):
        return NewsAndEventsQuerySet(self.model, using=self._db)

    def all(self):
        return self.get_queryset()

    def get_by_id(self, id):
        qs = self.get_queryset().filter(id=id)
        if qs.count() == 1:
            return qs.first()
        return None

    def search(self, query):
        return self.get_queryset().search(query)


class NewsAndEvents(models.Model):
    title = models.CharField(max_length=200, null=True)
    summary = models.TextField(max_length=200, blank=True, null=True)
    posted_as = models.CharField(choices=POST, max_length=10)
    updated_date = models.DateTimeField(auto_now=True, auto_now_add=False, null=True)
    upload_time = models.DateTimeField(auto_now_add=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="news_posts",
    )
    is_public = models.BooleanField(default=False)
    audience_roles = models.JSONField(default=list, blank=True)
    target_programs = models.ManyToManyField(
        "course.Program",
        blank=True,
        related_name="news_targets",
        verbose_name=_("Carreras"),
    )
    target_courses = models.ManyToManyField(
        "course.Course",
        blank=True,
        related_name="news_courses",
        verbose_name=_("Materias"),
    )
    target_sections = models.ManyToManyField(
        "course.CourseSection",
        blank=True,
        related_name="news_sections",
        verbose_name=_("Comisiones"),
    )
    invite_students = models.ManyToManyField(
        "accounts.Student",
        blank=True,
        related_name="event_invitations_news",
    )

    objects = NewsAndEventsManager()

    class Meta:
        ordering = ("-upload_time",)
        verbose_name = _("Noticia o evento")
        verbose_name_plural = _("Noticias y eventos")

    def __str__(self):
        return self.title or _("Publicacion")

    @property
    def is_event(self):
        return self.posted_as == EVENTS

    @staticmethod
    def _program_ids_for_user(user):
        from course.models import Program  # import diferido para evitar ciclos

        if getattr(user, "is_superuser", False):
            return list(Program.objects.values_list("id", flat=True))

        ids = set()
        if hasattr(user, "program_id") and user.program_id:
            ids.add(user.program_id)
        if hasattr(user, "programs_as_coordinator"):
            ids.update(user.programs_as_coordinator.values_list("id", flat=True))
        if hasattr(user, "programs_as_teacher"):
            ids.update(user.programs_as_teacher.values_list("id", flat=True))
        student_rel = getattr(user, "student_profile", None) or getattr(
            user, "student", None
        )
        if student_rel:
            ids.update(student_rel.programs.values_list("id", flat=True))
            if getattr(student_rel, "program_id", None):
                ids.add(student_rel.program_id)
        return list(ids)

    @staticmethod
    def _course_ids_for_user(user):
        from course.models import Course

        if getattr(user, "is_superuser", False):
            return list(Course.objects.values_list("id", flat=True))

        ids = set()
        if hasattr(user, "courses"):
            ids.update(user.courses.values_list("id", flat=True))
        taken_rel = getattr(user, "taken_courses", None)
        if taken_rel is not None:
            ids.update(taken_rel.values_list("course_id", flat=True))
        return list(ids)

    @staticmethod
    def _section_ids_for_user(user):
        from course.models import CourseSection

        if getattr(user, "is_superuser", False):
            return list(CourseSection.objects.values_list("id", flat=True))

        ids = set()
        ids.update(CourseSection.objects.filter(teachers=user).values_list("id", flat=True))
        ids.update(CourseSection.objects.filter(students=user).values_list("id", flat=True))
        return list(ids)

    def _matches_targets(self, program_ids, course_ids, section_ids):
        has_targets = (
            self.target_programs.exists()
            or self.target_courses.exists()
            or self.target_sections.exists()
        )
        if not has_targets:
            return True
        if program_ids and self.target_programs.filter(id__in=program_ids).exists():
            return True
        if course_ids and self.target_courses.filter(id__in=course_ids).exists():
            return True
        if section_ids and self.target_sections.filter(id__in=section_ids).exists():
            return True
        return False

    def can_be_managed_by(self, user):
        role = getattr(user, "role", None)
        if getattr(user, "is_superuser", False):
            return True
        if role in ADMIN_VIEW_ROLES:
            return True
        if role in {"COORDINATOR", "TEACHER"} and self.created_by_id == getattr(
            user, "id", None
        ):
            return True
        return False

    def can_view(self, user, program_ids=None, course_ids=None, section_ids=None):
        program_ids = program_ids or []
        course_ids = course_ids or []
        section_ids = section_ids or []
        role = getattr(user, "role", None)

        if not self.is_public and self.audience_roles:
            if role not in self.audience_roles:
                return False

        if not self._matches_targets(program_ids, course_ids, section_ids):
            return False

        if self.is_event and self.invite_students.exists():
            student_profile = getattr(user, "student_profile", None) or getattr(
                user, "student", None
            )
            if not student_profile:
                return False
            if not self.invite_students.filter(id=student_profile.id).exists():
                return False

        return True


# ==============================
# Ciclo lectivo y cuatrimestre
# ==============================
class Session(models.Model):
    session = models.CharField(max_length=200, unique=True)
    is_current_session = models.BooleanField(default=False, blank=True, null=True)
    next_session_begins = models.DateField(blank=True, null=True)

    class Meta:
        verbose_name = _("Ciclo lectivo")
        verbose_name_plural = _("Ciclos lectivos")
        ordering = ("-session",)

    def __str__(self):
        return f"{self.session}"


class Semester(models.Model):
    semester = models.CharField(max_length=10, choices=SEMESTER, blank=True)
    is_current_semester = models.BooleanField(default=False, blank=True, null=True)
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, blank=True, null=True
    )
    next_semester_begins = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = _("Cuatrimestre")
        verbose_name_plural = _("Cuatrimestres")
        ordering = ("-session__session", "semester")

    def __str__(self):
        return f"{self.get_semester_display()}"


# ==============================
# Infraestructura (pisos / aulas)
# ==============================
class BuildingFloor(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name=_("Nombre"))
    number = models.IntegerField(verbose_name=_("Piso"))
    description = models.TextField(blank=True, verbose_name=_("Descripcion"))

    class Meta:
        ordering = ("number", "name")
        verbose_name = _("Piso / Nivel")
        verbose_name_plural = _("Pisos / Niveles")

    def __str__(self):
        return f"{self.number} - {self.name}"


class Room(models.Model):
    CLASSROOM = "CLASSROOM"
    LAB = "LAB"
    OTHER = "OTHER"
    ROOM_TYPES = (
        (CLASSROOM, _("Aula")),
        (LAB, _("Laboratorio")),
        (OTHER, _("Otro")),
    )

    floor = models.ForeignKey(
        BuildingFloor, on_delete=models.CASCADE, related_name="rooms"
    )
    name = models.CharField(max_length=100, verbose_name=_("Nombre"))
    code = models.CharField(max_length=100, unique=True, verbose_name=_("Codigo"))
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES, default=CLASSROOM)
    capacity = models.PositiveIntegerField(default=0)
    is_enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("code",)
        verbose_name = _("Espacio")
        verbose_name_plural = _("Espacios")

    def __str__(self):
        return f"{self.code} ({self.get_room_type_display()})"


class RoomBlock(models.Model):
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, related_name="blocks", verbose_name=_("Espacio")
    )
    start_date = models.DateField(verbose_name=_("Fecha desde"))
    end_date = models.DateField(verbose_name=_("Fecha hasta"))
    start_time = models.TimeField(null=True, blank=True, verbose_name=_("Hora inicio"))
    end_time = models.TimeField(null=True, blank=True, verbose_name=_("Hora fin"))
    reason = models.CharField(max_length=255, blank=True, verbose_name=_("Motivo"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="room_blocks_created",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Bloqueo de espacio")
        verbose_name_plural = _("Bloqueos de espacios")
        ordering = ("-start_date", "-start_time")

    def __str__(self):
        return f"{self.room} bloqueada del {self.start_date} al {self.end_date}"


# ==============================
# Bitacora simple
# ==============================
class ActivityLog(models.Model):
    message = models.TextField()
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Registro de actividad")
        verbose_name_plural = _("Registros de actividad")

    def __str__(self):
        return f"[{self.created_at}]{self.message}"


# ==============================
# Asistencia y comisiones
# ==============================
class SectionSession(models.Model):
    section = models.ForeignKey(
        "course.CourseSection", on_delete=models.CASCADE, related_name="sessions"
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_cancelled = models.BooleanField(default=False)
    cancellation_reason = models.TextField(blank=True)
    attendance_submitted = models.BooleanField(default=False)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_sessions",
    )

    class Meta:
        ordering = ("-date", "-start_time")
        verbose_name = _("Clase de comision")
        verbose_name_plural = _("Clases de comision")

    def __str__(self):
        return f"{self.section} - {self.date}"


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = "PRESENT", _("Presente")
        ABSENT = "ABSENT", _("Ausente")
        LATE = "LATE", _("Llego tarde")
        JUSTIFIED = "JUSTIFIED", _("Justificada")

    section = models.ForeignKey(
        "course.CourseSection",
        on_delete=models.CASCADE,
        related_name="attendances",
        null=True,
        blank=True,
    )
    session = models.ForeignKey(
        SectionSession,
        on_delete=models.CASCADE,
        related_name="attendances",
        null=True,
        blank=True,
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_records_recorded",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PRESENT
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    justification_token = models.UUIDField(
        default=uuid.uuid4, editable=False, unique=True
    )

    class Meta:
        unique_together = ("session", "student")
        ordering = ("-created_at",)
        verbose_name = _("Registro de asistencia")
        verbose_name_plural = _("Registros de asistencia")

    STATUS_CHOICES = Status.choices

    def __str__(self):
        return f"{self.student} - {self.section} - {self.session.date}"


class AttendanceJustification(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pendiente")
        APPROVED = "APPROVED", _("Aprobada")
        REJECTED = "REJECTED", _("Rechazada")

    attendance_record = models.ForeignKey(
        AttendanceRecord,
        on_delete=models.CASCADE,
        related_name="justifications",
        null=True,
        blank=True,
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="absence_justifications",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    submitted_comment = models.TextField(blank=True)
    document = models.FileField(upload_to="justifications/", blank=True, null=True)
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    responded_at = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="justifications_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Justificacion de inasistencia")
        verbose_name_plural = _("Justificaciones de inasistencia")

    def __str__(self):
        return f"{self.student} - {self.get_status_display()}"


class AttendanceReminderLog(models.Model):
    section = models.ForeignKey(
        "course.CourseSection",
        on_delete=models.CASCADE,
        related_name="reminders",
        null=True,
        blank=True,
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_reminders",
        null=True,
        blank=True,
    )
    sent_at = models.DateTimeField(default=timezone.now)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ("-sent_at",)
        verbose_name = _("Recordatorio de asistencia")
        verbose_name_plural = _("Recordatorios de asistencia")

    def __str__(self):
        return f"Reminder {self.section} to {self.teacher}"


class BulkUploadRequest(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", _("Recibido")
        PROCESSING = "PROCESSING", _("Procesando")
        COMPLETED = "COMPLETED", _("Completado")
        FAILED = "FAILED", _("Fallido")

    class Kind(models.TextChoices):
        ATTENDANCE = "ATTENDANCE", _("Asistencia")
        GRADES = "GRADES", _("Notas")
        ENROLLMENT = "ENROLLMENT", _("Inscripciones")

    kind = models.CharField(max_length=20, choices=Kind.choices)
    file = models.FileField(upload_to="bulk_uploads/")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="bulk_uploads",
    )
    section = models.ForeignKey(
        "course.CourseSection",
        on_delete=models.CASCADE,
        related_name="bulk_uploads",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RECEIVED,
        help_text=_("Estado de procesamiento de la carga."),
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    result_log = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bulk_uploads_uploaded",
    )

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Carga masiva")
        verbose_name_plural = _("Cargas masivas")

    def __str__(self):
        return f"{self.get_kind_display()} - {self.created_at.date()}"


class EventInvitation(models.Model):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    STATUS_CHOICES = (
        (PENDING, _("Pendiente")),
        (ACCEPTED, _("Aceptada")),
        (DECLINED, _("Rechazada")),
    )

    event = models.ForeignKey(
        NewsAndEvents, on_delete=models.CASCADE, related_name="invitations"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_invitations",
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=PENDING
    )
    responded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ("event", "student")
        verbose_name = _("Invitacion a evento")
        verbose_name_plural = _("Invitaciones a eventos")

    def __str__(self):
        return f"{self.event} -> {self.student}"
