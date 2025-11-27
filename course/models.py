from decimal import Decimal
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.db.models import Q
from django.db.models.signals import pre_save, post_delete, post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from core.models import ActivityLog, Room, Semester
from core.utils import unique_slug_generator


class ProgramManager(models.Manager):
    def search(self, query=None):
        queryset = self.get_queryset()
        if query:
            or_lookup = Q(title__icontains=query) | Q(summary__icontains=query)
            queryset = queryset.filter(or_lookup).distinct()
        return queryset


class University(models.Model):
    name = models.CharField(max_length=150, unique=True)
    short_name = models.CharField(max_length=30, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = _("Universidad")
        verbose_name_plural = _("Universidades")
        ordering = ("name",)

    def __str__(self):
        return self.short_name or self.name


class Program(models.Model):
    TECNICATURA = "TEC"
    LICENCIATURA = "LIC"
    DIPLOMATURA = "DIP"
    CURSO_INGRESO = "ING"
    PROGRAM_TYPES = (
        (TECNICATURA, _("Tecnicatura")),
        (LICENCIATURA, _("Licenciatura")),
        (DIPLOMATURA, _("Diplomatura")),
        (CURSO_INGRESO, _("Curso de ingreso")),
    )

    university = models.ForeignKey(
        University,
        on_delete=models.PROTECT,
        related_name="programs",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=150, unique=True)
    summary = models.TextField(blank=True)
    coordinators = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="programs_coordinated",
        limit_choices_to={"role": "COORDINATOR"},
        help_text=_("SeleccionÃ¡ uno o mÃ¡s coordinadores responsables de la carrera."),
    )
    program_type = models.CharField(
        max_length=3, choices=PROGRAM_TYPES, default=TECNICATURA
    )
    allows_promotion = models.BooleanField(
        default=True,
        help_text=_("Indica si la carrera permite promocionar materias sin final."),
    )
    pass_score = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=4.0,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text=_("Nota mÃ­Â­nima para aprobar (0 a 10)."),
    )
    promotion_score = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=6.0,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text=_("Nota mÃ­nima para promocionar (0 a 10)."),
    )
    min_passing_attendance = models.PositiveIntegerField(
        default=75,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_("Porcentaje de asistencia requerido para aprobar."),
    )
    min_promotion_attendance = models.PositiveIntegerField(
        default=80,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_("Porcentaje de asistencia requerido para promocionar."),
    )

    objects = ProgramManager()

    def __str__(self):
        return f"{self.title}"

    def get_absolute_url(self):
        return reverse("program_detail", kwargs={"pk": self.pk})


@receiver(post_save, sender=Program)
def log_program_save(sender, instance, created, **kwargs):
    verb = "creada" if created else "actualizada"
    ActivityLog.objects.create(message=_(f"La carrera '{instance}' ha sido {verb}."))


@receiver(post_delete, sender=Program)
def log_program_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(message=_(f"La carrera '{instance}' ha sido eliminada."))


class CourseManager(models.Manager):
    def search(self, query=None):
        queryset = self.get_queryset()
        if query:
            or_lookup = (
                Q(title__icontains=query)
                | Q(summary__icontains=query)
                | Q(code__icontains=query)
                | Q(slug__icontains=query)
            )
            queryset = queryset.filter(or_lookup).distinct()
        return queryset


class Course(models.Model):
    class EvaluationModes(models.TextChoices):
        PROMOTIONAL = "PROMOTIONAL", _("Promocionable")
        FINAL = "FINAL", _("Final obligatorio")

    slug = models.SlugField(unique=True, blank=True)
    title = models.CharField(max_length=200)
    code = models.CharField(max_length=200, unique=True)
    credit = models.IntegerField(null=True, blank=True, default=None)
    summary = models.TextField(max_length=200, blank=True)
    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="primary_courses",
        help_text=_("Carrera principal (opcional)."),
    )
    programs = models.ManyToManyField(
        Program,
        related_name="courses",
        blank=True,
        help_text=_("Seleccione una o varias carreras a las que pertenece la materia."),
    )
    level = models.CharField(max_length=25, choices=settings.LEVEL_CHOICES)
    year = models.IntegerField(choices=settings.YEARS, default=1)
    semester = models.CharField(choices=settings.SEMESTER_CHOICES, max_length=200)
    is_elective = models.BooleanField(
        default=False,
        verbose_name=_("Materia electiva"),
        help_text=_("Marca si la materia es electiva dentro de la carrera."),
    )
    evaluation_mode = models.CharField(
        max_length=20,
        choices=EvaluationModes.choices,
        default=EvaluationModes.PROMOTIONAL,
        help_text=_(
            "Define si la materia es promocionable o requiere final obligatorio."
        ),
    )
    prerequisites = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="dependent_courses",
        help_text=_("Seleccione correlativas si las hubiera."),
    )

    objects = CourseManager()

    def __str__(self):
        return f"{self.title} ({self.code})"

    def get_absolute_url(self):
        return reverse("course_detail", kwargs={"slug": self.slug})

    @property
    def is_current_semester(self):

        current_semester = Semester.objects.filter(is_current_semester=True).first()
        return self.semester == current_semester.semester if current_semester else False

    @property
    def is_promotional(self):
        return self.evaluation_mode == self.EvaluationModes.PROMOTIONAL


@receiver(pre_save, sender=Course)
def course_pre_save_receiver(sender, instance, **kwargs):
    if not instance.slug:
        instance.slug = unique_slug_generator(instance)


@receiver(post_save, sender=Course)
def log_course_save(sender, instance, created, **kwargs):
    verb = "creada" if created else "actualizada"
    ActivityLog.objects.create(message=_(f"La materia '{instance}' ha sido {verb}."))


@receiver(post_delete, sender=Course)
def log_course_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(message=_(f"La materia '{instance}' ha sido eliminada."))


class CourseAllocation(models.Model):
    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        related_name="allocations",
        null=True,
        blank=True,
        help_text=_("Carrera para la cual se realiza la asignaciÃ³n."),
    )
    lecturer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="allocated_lecturer",
    )
    courses = models.ManyToManyField(Course, related_name="allocated_course")
    session = models.ForeignKey(
        "core.Session", on_delete=models.CASCADE, blank=True, null=True
    )

    def __str__(self):
        return self.lecturer.get_full_name

    def clean(self):
        super().clean()
        if self.program and self.courses.exists():
            invalid_courses = self.courses.exclude(program=self.program)
            if invalid_courses.exists():
                raise ValidationError(
                    _("Todas las materias deben pertenecer a la carrera seleccionada.")
                )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("edit_allocated_course", kwargs={"pk": self.pk})


class Upload(models.Model):
    title = models.CharField(max_length=100)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    file = models.FileField(
        upload_to="course_files/",
        help_text=_(
            "Archivos vÃ¡lidos: pdf, docx, doc, xls, xlsx, ppt, pptx, zip, rar, 7zip"
        ),
        validators=[
            FileExtensionValidator(
                [
                    "pdf",
                    "docx",
                    "doc",
                    "xls",
                    "xlsx",
                    "ppt",
                    "pptx",
                    "zip",
                    "rar",
                    "7zip",
                ]
            )
        ],
    )
    updated_date = models.DateTimeField(auto_now=True)
    upload_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title}"

    def get_extension_short(self):
        ext = self.file.name.split(".")[-1].lower()
        if ext in ("doc", "docx"):
            return "word"
        elif ext == "pdf":
            return "pdf"
        elif ext in ("xls", "xlsx"):
            return "excel"
        elif ext in ("ppt", "pptx"):
            return "powerpoint"
        elif ext in ("zip", "rar", "7zip"):
            return "archive"
        return "file"

    def delete(self, *args, **kwargs):
        self.file.delete(save=False)
        super().delete(*args, **kwargs)


@receiver(post_save, sender=Upload)
def log_upload_save(sender, instance, created, **kwargs):
    if created:
        message = _(
            f"Se subiÃ³ el archivo '{instance.title}' a la materia '{instance.course}'."
        )
    else:
        message = _(
            f"Se actualizÃ³ el archivo '{instance.title}' de la materia '{instance.course}'."
        )
    ActivityLog.objects.create(message=message)


@receiver(post_delete, sender=Upload)
def log_upload_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(
        message=_(
            f"Se eliminÃ³ el archivo '{instance.title}' de la materia '{instance.course}'."
        )
    )


class UploadVideo(models.Model):
    title = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    video = models.FileField(
        upload_to="course_videos/",
        help_text=_("Formatos de video vÃ¡lidos: mp4, mkv, wmv, 3gp, f4v, avi, mp3"),
        validators=[
            FileExtensionValidator(["mp4", "mkv", "wmv", "3gp", "f4v", "avi", "mp3"])
        ],
    )
    summary = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title}"

    def get_absolute_url(self):
        return reverse(
            "video_single", kwargs={"slug": self.course.slug, "video_slug": self.slug}
        )

    def delete(self, *args, **kwargs):
        self.video.delete(save=False)
        super().delete(*args, **kwargs)


@receiver(pre_save, sender=UploadVideo)
def video_pre_save_receiver(sender, instance, **kwargs):
    if not instance.slug:
        instance.slug = unique_slug_generator(instance)


@receiver(post_save, sender=UploadVideo)
def log_uploadvideo_save(sender, instance, created, **kwargs):
    if created:
        message = _(
            f"Se subiÃ³ el video '{instance.title}' a la materia '{instance.course}'."
        )
    else:
        message = _(
            f"Se actualizÃ³ el video '{instance.title}' de la materia '{instance.course}'."
        )
    ActivityLog.objects.create(message=message)


@receiver(post_delete, sender=UploadVideo)
def log_uploadvideo_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(
        message=_(
            f"Se eliminÃ³ el video '{instance.title}' de la materia '{instance.course}'."
        )
    )


class CourseOffer(models.Model):
    """NOTE: Only department head can offer semester courses"""

    dep_head = models.ForeignKey("accounts.DepartmentHead", on_delete=models.CASCADE)

    def __str__(self):
        return str(self.dep_head)


class Turn(models.Model):
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    EVENING = "EVENING"
    DEFAULT_TURNS = (
        (MORNING, _("MaÃ±ana")),
        (AFTERNOON, _("Tarde")),
        (EVENING, _("Noche")),
    )

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Turno")
        verbose_name_plural = _("Turnos")
        ordering = ("name",)

    def __str__(self):
        return self.name


class CourseSection(models.Model):
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="sections"
    )
    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        related_name="sections",
        help_text=_("Carrera responsable de la comisiÃ³n."),
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.PROTECT,
        related_name="sections",
    )
    turn = models.ForeignKey(
        Turn,
        on_delete=models.PROTECT,
        related_name="sections",
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sections",
    )
    teachers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="teaching_sections",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    days_of_week = models.JSONField(
        default=list,
        help_text=_("Lista de d?as de cursada (ej: ['Lunes','Mi?rcoles'])."),
        blank=True,
    )
    schedule_by_day = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Horarios por d?a, ej: [{'day': 'Lunes', 'start': '08:00', 'end': '10:00'}]."),
    )
    max_capacity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    attendance_required = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_("Porcentaje mÃ­nimo de asistencia para aprobar la comisiÃ³n."),
    )
    promotion_attendance_required = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_("Porcentaje mÃ­nimo de asistencia para promocionar la comisiÃ³n."),
    )
    code = models.CharField(
        max_length=50,
        null=True,
        blank=True, 
        unique=True, 
        help_text=_("CÃ³digo identificador de la comisiÃ³n.")
    )
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        blank=True, 
        related_name="sections_enrolled", 
        limit_choices_to={"role": "STUDENT"}, 
        verbose_name=_("Alumnos"), 
        help_text=_("Seleccione los alumnos inscriptos en esta comisiÃ³n.")
    )

    class Meta:
        verbose_name = _("ComisiÃ³n")
        verbose_name_plural = _("Comisiones")
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.course} - {self.turn} ({self.semester})"

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(_("La fecha de inicio no puede ser posterior a la de fin."))
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError(_("La hora de inicio debe ser menor que la de finalizaciÃ³n."))
        if self.program_id and self.course:
            course_program_ids = set(
                filter(
                    None,
                    [self.course.program_id, *self.course.programs.values_list("id", flat=True)],
                )
            )
            if self.program_id not in course_program_ids:
                raise ValidationError(_("La comisiÃ³n debe pertenecer a la misma carrera que la materia."))
        for field_name in ("attendance_required", "promotion_attendance_required"):
            value = getattr(self, field_name)
            if value is not None and not (0 <= value <= 100):
                raise ValidationError(_("Los porcentajes de asistencia deben estar entre 0 y 100."))
        if (
            self.attendance_required is not None
            and self.promotion_attendance_required is not None
            and self.promotion_attendance_required < self.attendance_required
        ):
            raise ValidationError(
                _("La asistencia para promocionar debe ser igual o mayor que la asistencia para aprobar.")
            )

    def save(self, *args, **kwargs):
        if not self.program_id and self.course_id:
            # Usa la carrera principal de la materia o la primera asociada
            if self.course.program_id:
                self.program = self.course.program
            else:
                first_prog = self.course.programs.first()
                if first_prog:
                    self.program = first_prog
        program = self.program or (self.course.program if self.course_id else None)
        if program:
            if self.attendance_required is None:
                self.attendance_required = program.min_passing_attendance
            if self.promotion_attendance_required is None:
                self.promotion_attendance_required = program.min_promotion_attendance
        if not self.room_id:
            self.room = self._find_available_room()
        super().save(*args, **kwargs)
        self._resolve_room_conflicts()

    def _find_available_room(self):
        candidates = Room.objects.filter(is_enabled=True).order_by("capacity")
        if self.max_capacity:
            candidates = candidates.filter(capacity__gte=self.max_capacity)
        for room in candidates:
            conflict = False
            for other in CourseSection.objects.filter(room=room).exclude(pk=self.pk):
                if not set(other.days_of_week or []).intersection(self.days_of_week or []):
                    continue
                if (
                    self.start_time < other.end_time
                    and self.end_time > other.start_time
                ):
                    conflict = True
                    break
            if not conflict:
                return room
        return None

    def _resolve_room_conflicts(self):
        if not self.room_id:
            return
        conflicts = CourseSection.objects.filter(
            room=self.room
        ).exclude(pk=self.pk)
        for other in conflicts:
            if not set(other.days_of_week or []).intersection(self.days_of_week or []):
                continue
                if (
                    self.start_time < other.end_time
                    and self.end_time > other.start_time
                ):
                    alternative = other._find_available_room()
                    if alternative and alternative != other.room:
                        CourseSection.objects.filter(pk=other.pk).update(room=alternative)


class ExamSchedule(models.Model):
    class ExamTypes(models.TextChoices):
        FIRST_PARTIAL = "FIRST_PARTIAL", _("Primer Parcial")
        SECOND_PARTIAL = "SECOND_PARTIAL", _("Segundo Parcial")
        FIRST_RETAKE = "FIRST_RETAKE", _("Recuperatorio del Primer Parcial")
        SECOND_RETAKE = "SECOND_RETAKE", _("Recuperatorio del Segundo Parcial")
        REGULAR_FINAL = "REGULAR_FINAL", _("Final regular")
        FREE_EXAM = "FREE_EXAM", _("Examen libre")

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="exam_schedules",
    )
    section = models.ForeignKey(
        CourseSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exam_schedules",
    )
    exam_type = models.CharField(max_length=20, choices=ExamTypes.choices)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exam_schedules",
    )
    teachers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="exam_schedules",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Examen")
        verbose_name_plural = _("ExÃ¡menes")
        ordering = ("-date", "-start_time")

    def __str__(self):
        return f"{self.get_exam_type_display()} - {self.course}"

    @property
    def is_free_exam(self):
        return self.exam_type == self.ExamTypes.FREE_EXAM

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError(_("La hora de inicio debe ser menor que la hora de fin."))
        if self.section and self.section.course_id != self.course_id:
            raise ValidationError(_("La comisiÃ³n seleccionada debe pertenecer a la materia."))


class ExamAttempt(models.Model):
    schedule = models.ForeignKey(
        ExamSchedule,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    student = models.ForeignKey(
        "accounts.Student",
        on_delete=models.CASCADE,
        related_name="exam_attempts",
    )
    score = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("0.0"),
    )
    passed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Intento de examen")
        verbose_name_plural = _("Intentos de examen")
        unique_together = ("schedule", "student")

    def __str__(self):
        return f"{self.student} - {self.schedule}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.passed and self.schedule.is_free_exam:
            self._mark_course_as_passed()

    def _mark_course_as_passed(self):
        TakenCourse = apps.get_model("result", "TakenCourse")
        course = self.schedule.course
        if not course or not course.program:
            return
        taken, created = TakenCourse.objects.get_or_create(
            student=self.student,
            course=course,
            defaults={
                "section": self.schedule.section,
                "attendance": Decimal("100"),
                "final_exam": Decimal(course.program.pass_score),
                "first_partial": Decimal(course.program.pass_score),
                "second_partial": Decimal(course.program.pass_score),
            },
        )
        pass_score = Decimal(course.program.pass_score)
        taken.section = self.schedule.section or taken.section
        taken.assignment = Decimal("0")
        taken.mid_exam = Decimal("0")
        taken.quiz = Decimal("0")
        taken.final_exam = pass_score
        taken.first_partial = pass_score
        taken.second_partial = pass_score
        taken.attendance = Decimal("100")
        taken.save()


@receiver(post_save, sender=CourseSection)
def log_section_save(sender, instance, created, **kwargs):
    verb = "creada" if created else "actualizada"
    ActivityLog.objects.create(
        message=_(
            f"Se {verb} la comisiÃ³n de '{instance.course}' para el turno '{instance.turn}'."
        )
    )


@receiver(post_delete, sender=CourseSection)
def log_section_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(
        message=_(
            f"Se eliminÃ³ la comisiÃ³n de '{instance.course}' para el turno '{instance.turn}'."
        )
    )
