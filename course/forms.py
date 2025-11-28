from django import forms
from django.conf import settings
from datetime import datetime
import json

from accounts.models import User
from django.db import models
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
            "summary": "DescripciÃ³n",
            "university": "Universidad",
            "program_type": "Tipo de carrera",
            "allows_promotion": "Permite promociÃ³n",
            "pass_score": "Nota mÃ­nima para aprobar",
            "promotion_score": "Nota mÃ­nima para promocionar",
            "min_passing_attendance": "Asistencia mÃ­nima para aprobar (%)",
            "min_promotion_attendance": "Asistencia mÃ­nima para promocionar (%)",
            "is_active": "Activa",
        }
        help_texts = {
            "allows_promotion": "Indica si la carrera permite promocionar materias sin final.",
            "pass_score": "Nota mÃ­nima para aprobar (0 a 10).",
            "promotion_score": "Nota mÃ­nima para promocionar (0 a 10).",
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
            self.fields.pop(fname, None)

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
            "code": "CÃ³digo",
            "credit": "CrÃ©ditos",
            "summary": "DescripciÃ³n",
            "programs": "Carreras",
            "is_elective": "Materia optativa",
            "evaluation_mode": "Modo de evaluaciÃ³n",
            "prerequisites": "Correlativas",
        }
        help_texts = {
            "programs": "Seleccione una o varias carreras a las que pertenece la materia.",
            "evaluation_mode": "Define si la materia es promocionable o requiere final.",
            "prerequisites": "Tilde y destilde correlativas segÃºn corresponda.",
        }
        for fname, label in labels.items():
            if fname in self.fields:
                self.fields[fname].label = label
        for fname, ht in help_texts.items():
            if fname in self.fields:
                self.fields[fname].help_text = ht

    def save(self, commit=True):
        instance = super().save(commit=False)
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
        self.fields["title"].label = "TÃ­tulo"
        self.fields["file"].label = "Archivo"


class UploadFormVideo(forms.ModelForm):
    class Meta:
        model = UploadVideo
        fields = ("title", "video")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["video"].widget.attrs.update({"class": "form-control"})
        self.fields["title"].label = "TÃ­tulo"
        self.fields["video"].label = "Video"


class UniversityForm(forms.ModelForm):
    class Meta:
        model = University
        fields = ("name", "short_name", "description", "is_active")
        labels = {
            "name": "Nombre de la universidad",
            "short_name": "Sigla",
            "description": "DescripciÃ³n",
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
    enable_custom_schedule = forms.BooleanField(
        required=False,
        label="Habilitar horarios diferentes por dÃ­a",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    schedule_by_day = forms.CharField(required=False, widget=forms.HiddenInput())

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
        ("MiÃ©rcoles", "MiÃ©rcoles"),
        ("Jueves", "Jueves"),
        ("Viernes", "Viernes"),
        ("SÃ¡bado", "SÃ¡bado"),
    ]

    days_of_week = forms.MultipleChoiceField(
        choices=DAYS_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="DÃ­as de cursada",
        help_text="Seleccione los dÃ­as en los que se cursa la comisiÃ³n.",
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        for fname in [
            "program",
            "attendance_required",
            "promotion_attendance_required",
            "max_capacity",
            "room",
            "students",
        ]:
            self.fields.pop(fname, None)

        if "semester" in self.fields:
            self.fields["semester"].queryset = (
                self.fields["semester"].queryset.select_related("session").order_by("-session__year", "semester")
            )
            verbose_map = {
                "FIRST": "1Â° Cuatrimestre",
                "SECOND": "2Â° Cuatrimestre",
                "SUMMER": "Materias de Verano",
            }
            self.fields["semester"].label_from_instance = lambda obj: verbose_map.get(obj.semester, obj.semester)

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
        elif getattr(self.instance, "semester_id", None) and self.instance.semester.session_id:
            sess_id = self.instance.semester.session_id
            if "semester" in self.fields:
                self.fields["semester"].queryset = self.fields["semester"].queryset.filter(session_id=sess_id)
            self.fields["session"].initial = sess_id

        course_id = self.data.get("course") or getattr(self.instance, "course_id", None)
        program_ids = []
        if course_id:
            try:
                course = Course.objects.get(pk=course_id)
                program_ids = list(course.programs.values_list("id", flat=True))
            except Course.DoesNotExist:
                program_ids = []

        selected_teacher_ids = []
        if self.data:
            selected_teacher_ids = [
                int(pk) for pk in self.data.getlist("teachers") if pk and pk.isdigit()
            ]
        elif getattr(self.instance, "pk", None):
            selected_teacher_ids = list(self.instance.teachers.values_list("pk", flat=True))

        for name, field in self.fields.items():
            widget = field.widget
            if name == "teachers":
                self.fields[name].widget = forms.CheckboxSelectMultiple()
                base_qs = User.objects.filter(role=User.Roles.TEACHER)
                if program_ids:
                    base_qs = base_qs.filter(programs_as_teacher__in=program_ids)
                if selected_teacher_ids:
                    base_qs = base_qs | User.objects.filter(pk__in=selected_teacher_ids)
                teacher_qs = base_qs.distinct().order_by("first_name", "last_name")
                self.fields[name].queryset = teacher_qs
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
            if name in ["start_time", "end_time", "schedule_by_day"]:
                field.required = False

        labels = {
            "course": "Materia",
            "program": "Carrera",
            "session": "Ciclo lectivo",
            "semester": "Cuatrimestre",
            "turn": "Turno",
            "teachers": "Docentes",
            "start_date": "Fecha de inicio",
            "end_date": "Fecha de fin",
            "start_time": "Hora de inicio (general)",
            "end_time": "Hora de fin (general)",
            "days_of_week": "DÃ­as de cursada",
            "schedule_by_day": "Horarios por dÃ­a",
            "max_capacity": "Cupo",
            "is_active": "Activa",
            "attendance_required": "Asistencia mÃ­nima (aprobaciÃ³n)",
            "promotion_attendance_required": "Asistencia mÃ­nima (promociÃ³n)",
            "code": "CÃ³digo",
        }
        help_texts = {
            "program": "Carrera responsable de la comisiÃ³n.",
            "days_of_week": "Seleccione los dÃ­as en los que se cursa la comisiÃ³n.",
            "schedule_by_day": "Ejemplo: Lunes 08:00-10:00; Martes 09:00-11:00",
            "attendance_required": "Porcentaje mÃ­nimo de asistencia para aprobar la comisiÃ³n.",
            "promotion_attendance_required": "Porcentaje mÃ­nimo de asistencia para promocionar la comisiÃ³n.",
            "code": "CÃ³digo identificador de la comisiÃ³n.",
            "session": "Seleccione el ciclo lectivo al que pertenece el cuatrimestre.",
        }
        for fname, label in labels.items():
            if fname in self.fields:
                self.fields[fname].label = label
        for fname, ht in help_texts.items():
            if fname in self.fields:
                self.fields[fname].help_text = ht

        if self.instance and self.instance.pk:
            if self.instance.days_of_week:
                self.initial["days_of_week"] = self.instance.days_of_week
            if getattr(self.instance, "schedule_by_day", None):
                self.initial["enable_custom_schedule"] = True
                self.initial["schedule_by_day"] = json.dumps(self.instance.schedule_by_day)
            if self.instance.start_date:
                self.initial["start_date"] = self.instance.start_date.isoformat()
            if self.instance.end_date:
                self.initial["end_date"] = self.instance.end_date.isoformat()
            # Si la instancia tiene horario general, mantenerlo en el formulario
            if self.instance.start_time:
                self.initial["start_time"] = self.instance.start_time
            if self.instance.end_time:
                self.initial["end_time"] = self.instance.end_time

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
            "enable_custom_schedule",
            "schedule_by_day",
            "teachers",
        ]
        self.order_fields([f for f in desired_order if f in self.fields])

    def clean_days_of_week(self):
        return self.cleaned_data.get("days_of_week") or []

    def clean(self):
        cleaned = super().clean()
        session = cleaned.get("session")
        semester = cleaned.get("semester")
        if session and semester and semester.session_id and semester.session_id != session.id:
            self.add_error("semester", "El cuatrimestre debe pertenecer al ciclo lectivo seleccionado.")

        enable_custom = cleaned.get("enable_custom_schedule")
        days = cleaned.get("days_of_week") or []
        sched_raw = cleaned.get("schedule_by_day") or ""

        if enable_custom:
            if not days:
                self.add_error("days_of_week", "Seleccione al menos un dÃ­a para definir horarios.")
                return cleaned
            try:
                sched_list = json.loads(sched_raw) if sched_raw else []
            except Exception:
                self.add_error("schedule_by_day", "Formato de horarios por dÃ­a invÃ¡lido.")
                return cleaned
            schedule = []
            day_set = {d.lower() for d in days}
            for item in sched_list:
                day = (item.get("day") or "").strip()
                start = item.get("start")
                end = item.get("end")
                if not day or day.lower() not in day_set or not start or not end:
                    continue
                try:
                    start_t = datetime.strptime(start, "%H:%M").time()
                    end_t = datetime.strptime(end, "%H:%M").time()
                except ValueError:
                    self.add_error("schedule_by_day", f"Horario invÃ¡lido para {day}. Use HH:MM.")
                    return cleaned
                if start_t >= end_t:
                    self.add_error("schedule_by_day", f"La hora de inicio debe ser menor que la de fin ({day}).")
                    return cleaned
                schedule.append({"day": day, "start": start, "end": end})
            missing = [d for d in days if d.lower() not in {s['day'].lower() for s in schedule}]
            if missing:
                self.add_error("schedule_by_day", f"Falta definir horario para: {', '.join(missing)}.")
                return cleaned
            cleaned["schedule_by_day"] = schedule
            cleaned["start_time"] = None
            cleaned["end_time"] = None
        else:
            cleaned["schedule_by_day"] = []
            start = cleaned.get("start_time")
            end = cleaned.get("end_time")
            if start and end and start >= end:
                self.add_error("start_time", "La hora de inicio debe ser menor que la de fin.")
        return cleaned

class SectionEnrollmentForm(forms.Form):
    search = forms.CharField(
        required=False,
        label="Buscar (dni, nombre o apellido)",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Buscar"}),
    )
    students = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(role=User.Roles.STUDENT).order_by("first_name", "last_name"),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "list-unstyled"}),
        label="Alumnos",
        help_text="Seleccione los alumnos inscriptos en esta comisión.",
    )

    def __init__(self, *args, **kwargs):
        section = kwargs.pop("section", None)
        queryset_override = kwargs.pop("available_students", None)
        super().__init__(*args, **kwargs)
        if section:
            program_ids = list(section.course.programs.values_list("id", flat=True))
            qs = self.fields["students"].queryset
            if queryset_override is not None:
                qs = queryset_override
            elif program_ids:
                qs = qs.filter(student__programs__id__in=program_ids).distinct()
            self.fields["students"].queryset = qs.order_by("first_name", "last_name")
            self.fields["students"].initial = section.students.all()


class SectionEnrollmentUploadForm(forms.Form):
    file = forms.FileField(
        required=True,
        label="Archivo (CSV / XLSX / PDF)",
        widget=forms.FileInput(attrs={"class": "form-control"}),
        help_text="Suba una lista con DNI o email para pre-seleccionar alumnos.",
    )

