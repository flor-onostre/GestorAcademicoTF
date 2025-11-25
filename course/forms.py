from django import forms
from django.conf import settings

from accounts.models import User
from core.models import Session
from .models import (
    Program,
    Course,
    CourseAllocation,
    Upload,
    UploadVideo,
    University,
    CourseSection,
)


class ProgramForm(forms.ModelForm):
    class Meta:
        model = Program
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "browser-default custom-select form-control")
            else:
                widget.attrs.setdefault("class", "form-control")

        labels = {
            "title": "Nombre de la carrera",
            "summary": "Descripción",
            "university": "Universidad",
            "program_type": "Tipo de carrera",
            "allows_promotion": "Permite promoción",
            "pass_score": "Nota mínima para aprobar",
            "promotion_score": "Nota mínima para promocionar",
            "min_passing_attendance": "Asistencia mínima para aprobar (%)",
            "min_promotion_attendance": "Asistencia mínima para promocionar (%)",
            "is_active": "Activa",
        }
        help_texts = {
            "allows_promotion": "Indica si la carrera permite promocionar materias sin final.",
            "pass_score": "Nota mínima para aprobar (0 a 10).",
            "promotion_score": "Nota mínima para promocionar (0 a 10).",
            "min_passing_attendance": "Porcentaje de asistencia requerido para aprobar.",
            "min_promotion_attendance": "Porcentaje de asistencia requerido para promocionar.",
        }
        for fname, label in labels.items():
            if fname in self.fields:
                self.fields[fname].label = label
        for fname, ht in help_texts.items():
            if fname in self.fields:
                self.fields[fname].help_text = ht


class CourseAddForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for fname in ["year", "semester", "program", "level"]:
            if fname in self.fields:
                self.fields.pop(fname)

        for name, field in self.fields.items():
            widget = field.widget
            if name == "prerequisites":
                self.fields[name].widget = forms.CheckboxSelectMultiple()
                self.fields[name].queryset = Course.objects.all().order_by("title")
                if self.instance and self.instance.pk:
                    self.fields[name].queryset = self.fields[name].queryset.exclude(
                        pk=self.instance.pk
                    )
                widget = self.fields[name].widget
            if name == "programs":
                self.fields[name].widget = forms.CheckboxSelectMultiple()
                self.fields[name].queryset = Program.objects.all().order_by("title")
                widget = self.fields[name].widget
            if isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "browser-default custom-select form-control")
            else:
                widget.attrs.setdefault("class", "form-control")

        labels = {
            "title": "Nombre de la materia",
            "code": "Código",
            "credit": "Créditos",
            "summary": "Descripción",
            "programs": "Carreras",
            "is_elective": "Materia optativa",
            "evaluation_mode": "Modo de evaluación",
            "prerequisites": "Correlativas",
        }
        help_texts = {
            "programs": "Seleccione una o varias carreras a las que pertenece la materia.",
            "evaluation_mode": "Define si la materia es promocionable o requiere final.",
            "prerequisites": "Tilde y destilde correlativas según corresponda.",
        }
        for fname, label in labels.items():
            if fname in self.fields:
                self.fields[fname].label = label
        for fname, ht in help_texts.items():
            if fname in self.fields:
                self.fields[fname].help_text = ht

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Si el modelo requiere nivel, forzamos un valor por defecto desde LEVEL_CHOICES.
        if hasattr(instance, "level") and not getattr(instance, "level", None):
            choices = getattr(settings, "LEVEL_CHOICES", [])
            instance.level = choices[0][0] if choices else ""
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class CourseAllocationForm(forms.ModelForm):
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.all().order_by("level"),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "browser-default checkbox"}),
        required=True,
    )
    lecturer = forms.ModelChoiceField(
        queryset=User.objects.filter(is_lecturer=True),
        widget=forms.Select(attrs={"class": "browser-default custom-select"}),
        label="Docente",
    )

    class Meta:
        model = CourseAllocation
        fields = ["lecturer", "courses"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lecturer"].queryset = User.objects.filter(is_lecturer=True)
        self.fields["courses"].label = "Materias"


class EditCourseAllocationForm(forms.ModelForm):
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.all().order_by("level"),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )
    lecturer = forms.ModelChoiceField(
        queryset=User.objects.filter(is_lecturer=True),
        widget=forms.Select(attrs={"class": "browser-default custom-select"}),
        label="Docente",
    )

    class Meta:
        model = CourseAllocation
        fields = ["lecturer", "courses"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lecturer"].queryset = User.objects.filter(is_lecturer=True)
        self.fields["courses"].label = "Materias"


class UploadFormFile(forms.ModelForm):
    class Meta:
        model = Upload
        fields = ("title", "file")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["file"].widget.attrs.update({"class": "form-control"})
        self.fields["title"].label = "Título"
        self.fields["file"].label = "Archivo"


class UploadFormVideo(forms.ModelForm):
    class Meta:
        model = UploadVideo
        fields = ("title", "video")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["video"].widget.attrs.update({"class": "form-control"})
        self.fields["title"].label = "Título"
        self.fields["video"].label = "Video"


class UniversityForm(forms.ModelForm):
    class Meta:
        model = University
        fields = ("name", "short_name", "description", "is_active")
        labels = {
            "name": "Nombre de la universidad",
            "short_name": "Sigla",
            "description": "Descripción",
            "is_active": "Activa",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "short_name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            else:
                widget.attrs.setdefault("class", "form-control")


class CourseSectionForm(forms.ModelForm):
    session = forms.ModelChoiceField(
        queryset=Session.objects.all(),
        required=True,
        label="Ciclo lectivo",
        widget=forms.Select(attrs={"class": "browser-default custom-select form-control"}),
    )

    class Meta:
        model = CourseSection
        fields = "__all__"
        widgets = {
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "start_time": forms.TimeInput(
                attrs={"class": "form-control", "type": "time", "step": "900"}
            ),
            "end_time": forms.TimeInput(
                attrs={"class": "form-control", "type": "time", "step": "900"}
            ),
            "days_of_week": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    DAYS_CHOICES = [
        ("Lunes", "Lunes"),
        ("Martes", "Martes"),
        ("Miércoles", "Miércoles"),
        ("Jueves", "Jueves"),
        ("Viernes", "Viernes"),
        ("Sábado", "Sábado"),
    ]

    days_of_week = forms.MultipleChoiceField(
        choices=DAYS_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Días de cursada",
        help_text="Seleccione los días en los que se cursa la comisión.",
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        # Ocultar campos que se derivan automáticamente o se asignan luego (aula, alumnos)
        for fname in [
            "program",
            "attendance_required",
            "promotion_attendance_required",
            "max_capacity",
            "room",
            "students",
        ]:
            if fname in self.fields:
                self.fields.pop(fname)

        # Sincronizamos semestre con el ciclo lectivo elegido
        if "semester" in self.fields:
            self.fields["semester"].queryset = (
                self.fields["semester"].queryset.select_related("session").order_by("-session__year", "semester")
            )
            # Mostrar etiquetas en español aunque el modelo tenga textos dañados
            verbose_map = {
                "FIRST": "1° Cuatrimestre",
                "SECOND": "2° Cuatrimestre",
                "SUMMER": "Materias de Verano",
            }
            self.fields["semester"].label_from_instance = lambda obj: verbose_map.get(obj.semester, obj.semester)

        # Filtrar semestre por ciclo lectivo si se envió sesión
        session_value = None
        if self.data.get("session"):
            try:
                session_value = int(self.data.get("session"))
            except (TypeError, ValueError):
                session_value = None
        elif self.initial.get("session"):
            session_value = self.initial.get("session").pk if hasattr(self.initial.get("session"), "pk") else self.initial.get("session")

        if session_value and "semester" in self.fields:
            self.fields["semester"].queryset = self.fields["semester"].queryset.filter(session_id=session_value)
            self.fields["session"].initial = session_value

        # Filtrar docentes por carrera de la materia seleccionada
        course_id = self.data.get("course") or getattr(self.instance, "course_id", None)
        program_ids = []
        if course_id:
            try:
                course = Course.objects.get(pk=course_id)
                program_ids = list(course.programs.values_list("id", flat=True))
            except Course.DoesNotExist:
                program_ids = []

        for name, field in self.fields.items():
            widget = field.widget
            if name == "teachers":
                self.fields[name].widget = forms.CheckboxSelectMultiple()
                teacher_qs = User.objects.filter(role=User.Roles.TEACHER)
                if program_ids:
                    teacher_qs = teacher_qs.filter(programs_as_teacher__in=program_ids).distinct()
                self.fields[name].queryset = teacher_qs.order_by("first_name", "last_name")
                # Mostrar sólo nombre y apellido en la etiqueta
                self.fields[name].label_from_instance = (
                    lambda obj: f"{obj.first_name} {obj.last_name}".strip()
                )
                widget = self.fields[name].widget
            if isinstance(widget, forms.CheckboxSelectMultiple):
                widget.attrs.setdefault("class", "list-unstyled")
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.SelectMultiple):
                widget.attrs.setdefault("class", "browser-default custom-select form-control")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "browser-default custom-select form-control")
            else:
                widget.attrs.setdefault("class", "form-control")

        # Etiquetas y ayudas en español
        labels = {
            "course": "Materia",
            "program": "Carrera",
            "session": "Ciclo lectivo",
            "semester": "Cuatrimestre",
            "turn": "Turno",
            "teachers": "Docentes",
            "start_date": "Fecha de inicio",
            "end_date": "Fecha de fin",
            "start_time": "Hora de inicio",
            "end_time": "Hora de fin",
            "days_of_week": "Días de cursada",
            "max_capacity": "Cupo",
            "is_active": "Activa",
            "attendance_required": "Asistencia mínima (aprobación)",
            "promotion_attendance_required": "Asistencia mínima (promoción)",
            "code": "Código",
        }
        help_texts = {
            "program": "Carrera responsable de la comisión.",
            "days_of_week": "Seleccione los días en los que se cursa la comisión.",
            "attendance_required": "Porcentaje mínimo de asistencia para aprobar la comisión.",
            "promotion_attendance_required": "Porcentaje mínimo de asistencia para promocionar la comisión.",
            "code": "Código identificador de la comisión.",
            "session": "Seleccione el ciclo lectivo al que pertenece el cuatrimestre.",
        }
        for fname, label in labels.items():
            if fname in self.fields:
                self.fields[fname].label = label
        for fname, ht in help_texts.items():
            if fname in self.fields:
                self.fields[fname].help_text = ht

        # Inicializa días de cursada desde el JSON a la lista esperada
        if self.instance and self.instance.pk and self.instance.days_of_week:
            self.initial["days_of_week"] = self.instance.days_of_week

        # Orden de campos en el formulario
        desired_order = [
            "course",
            "turn",
            "code",
            "session",
            "semester",
            "start_date",
            "end_date",
            "days_of_week",
            "start_time",
            "end_time",
            "teachers",
        ]
        self.order_fields([f for f in desired_order if f in self.fields])

    def clean_days_of_week(self):
        data = self.cleaned_data.get("days_of_week") or []
        # Se almacena como lista en JSONField
        return data

    def clean(self):
        cleaned = super().clean()
        session = cleaned.get("session")
        semester = cleaned.get("semester")
        if session and semester and semester.session_id and semester.session_id != session.id:
            self.add_error("semester", "El cuatrimestre debe pertenecer al ciclo lectivo seleccionado.")
        return cleaned

