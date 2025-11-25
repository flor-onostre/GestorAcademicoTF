from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from accounts.models import DepartmentHead, Student, User
from course.models import Course, CourseSection, Program

from .models import (
    ADMIN_VIEW_ROLES,
    AttendanceJustification,
    BuildingFloor,
    BulkUploadRequest,
    COORDINATOR_ALLOWED_AUDIENCE,
    EventInvitation,
    EVENTS,
    NewsAndEvents,
    Room,
    SectionSession,
    SEMESTER,
    Semester,
    Session,
    TEACHER_ALLOWED_AUDIENCE,
)


class NewsAndEventsForm(forms.ModelForm):
    audience_roles = forms.MultipleChoiceField(
        choices=User.Roles.choices,
        required=False,
        label=_("Roles destinatarios"),
        widget=forms.CheckboxSelectMultiple,
    )
    target_programs = forms.ModelMultipleChoiceField(
        queryset=Program.objects.none(),
        required=False,
        label=_("Carreras destinatarias"),
    )
    target_courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.none(),
        required=False,
        label=_("Materias / Comisiones"),
    )
    target_sections = forms.ModelMultipleChoiceField(
        queryset=CourseSection.objects.none(),
        required=False,
        label=_("Comisiones destinatarias"),
    )
    invite_students = forms.ModelMultipleChoiceField(
        queryset=Student.objects.none(),
        required=False,
        label=_("Invitar alumnos (solo eventos)"),
        widget=forms.SelectMultiple(
            attrs={"class": "browser-default custom-select form-control", "size": 6}
        ),
    )

    class Meta:
        model = NewsAndEvents
        fields = (
            "title",
            "summary",
            "posted_as",
            "is_public",
            "audience_roles",
            "target_programs",
            "target_courses",
            "target_sections",
            "invite_students",
        )
        labels = {
            "title": _("Titulo"),
            "summary": _("Resumen"),
            "posted_as": _("Tipo de publicacion"),
            "is_public": _("Es publica?"),
            "audience_roles": _("Roles destinatarios"),
            "target_programs": _("Carreras destinatarias"),
            "target_courses": _("Materias / Comisiones"),
            "target_sections": _("Comisiones destinatarias"),
            "invite_students": _("Invitar alumnos"),
        }

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self._configure_fields()
        self._limit_querysets()
        self._limit_audience_choices()
        self._saved_instance = None
        if self.instance and self.instance.pk and "invite_students" in self.fields:
            self.fields["invite_students"].initial = Student.objects.filter(
                event_invitations__event=self.instance
            )

    def _configure_fields(self):
        text_fields = ["title", "summary", "posted_as"]
        for name in text_fields:
            if name in self.fields:
                self.fields[name].widget.attrs.update({"class": "form-control"})
        if "is_public" in self.fields:
            self.fields["is_public"].widget.attrs.update({"class": "form-check-input"})
        for name in ["target_programs", "target_courses", "target_sections"]:
            if name in self.fields:
                self.fields[name].widget.attrs.update(
                    {"class": "browser-default custom-select form-control", "size": 6}
                )
        if "audience_roles" in self.fields:
            self.fields["audience_roles"].widget.attrs.update(
                {"class": "list-unstyled"}
            )
        if "invite_students" in self.fields:
            self.fields["invite_students"].widget.attrs.update(
                {"class": "browser-default custom-select form-control", "size": 6}
            )

    def _limit_querysets(self):
        programs_qs = Program.objects.all().order_by("title")
        courses_qs = Course.objects.all().order_by("title")
        sections_qs = CourseSection.objects.select_related("course", "program").order_by(
            "course__title"
        )
        students_qs = Student.objects.select_related("student").order_by(
            "student__first_name", "student__last_name"
        )
        if self.request_user and not self.request_user.is_superuser:
            role = getattr(self.request_user, "role", None)
            if role == User.Roles.COORDINATOR:
                programs_qs = programs_qs.filter(
                    coordinators=self.request_user
                ).distinct()
                courses_qs = courses_qs.filter(program__in=programs_qs).distinct()
                sections_qs = sections_qs.filter(program__in=programs_qs).distinct()
                students_qs = students_qs.filter(program__in=programs_qs).distinct()
            elif role == User.Roles.TEACHER:
                sections_qs = sections_qs.filter(teachers=self.request_user).distinct()
                courses_qs = courses_qs.filter(
                    sections__in=sections_qs
                ).distinct()
                programs_qs = Program.objects.filter(course__in=courses_qs).distinct()
                students_qs = students_qs.filter(
                    takencourse__course__in=courses_qs
                ).distinct()
        self.fields["target_programs"].queryset = programs_qs
        self.fields["target_courses"].queryset = courses_qs
        self.fields["target_sections"].queryset = sections_qs
        self.fields["invite_students"].queryset = students_qs

    def _limit_audience_choices(self):
        allowed = set()
        if self.request_user:
            role = getattr(self.request_user, "role", None)
            if self.request_user.is_superuser or role in ADMIN_VIEW_ROLES:
                allowed = {
                    value
                    for value, _ in User.Roles.choices
                    if value not in {"PARENT"}
                }
            elif role == User.Roles.COORDINATOR:
                allowed = COORDINATOR_ALLOWED_AUDIENCE
            elif role == User.Roles.TEACHER:
                allowed = TEACHER_ALLOWED_AUDIENCE
        choices = [
            (value, label) for value, label in User.Roles.choices if value in allowed
        ]
        self.fields["audience_roles"].choices = choices
        if not choices:
            self.fields["audience_roles"].widget = forms.MultipleHiddenInput()

    def clean(self):
        cleaned = super().clean()
        user = self.request_user
        if not user:
            return cleaned
        role = getattr(user, "role", None)
        roles_selected = set(cleaned.get("audience_roles") or [])
        if role == User.Roles.TEACHER:
            if cleaned.get("is_public"):
                self.add_error("is_public", _("Los docentes no pueden publicar noticias globales."))
            disallowed = roles_selected - TEACHER_ALLOWED_AUDIENCE
            if disallowed:
                self.add_error(
                    "audience_roles", _("Los docentes solo pueden notificar a alumnos.")
                )
            if not (cleaned.get("target_courses") or cleaned.get("target_sections")):
                self.add_error(
                    "target_sections",
                    _("Seleccioná al menos una materia o comisión asignada."),
                )
        elif role == User.Roles.COORDINATOR:
            disallowed = roles_selected - COORDINATOR_ALLOWED_AUDIENCE
            if disallowed:
                self.add_error(
                    "audience_roles",
                    _("Solo podés elegir alumnos, docentes o ambos."),
                )
        recipients_defined = any(
            [
                cleaned.get("is_public"),
                roles_selected,
                cleaned.get("target_programs"),
                cleaned.get("target_courses"),
                cleaned.get("target_sections"),
            ]
        )
        posted_as = cleaned.get("posted_as")
        if posted_as == EVENTS:
            if not (recipients_defined or cleaned.get("invite_students")):
                raise forms.ValidationError(
                    _("Definí al menos una audiencia o invitá alumnos al evento.")
                )
        else:
            if cleaned.get("invite_students"):
                self.add_error(
                    "invite_students",
                    _("Solo los eventos pueden gestionar invitaciones."),
                )
            if not recipients_defined:
                raise forms.ValidationError(
                    _("Definí al menos un destinatario (roles, carreras o materias).")
                )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit)
        self._saved_instance = instance
        return instance

    def save_m2m(self):
        super().save_m2m()
        self._sync_invitations()

    def _sync_invitations(self):
        instance = getattr(self, "_saved_instance", self.instance)
        if not instance or not instance.pk:
            return
        if instance.posted_as != EVENTS:
            EventInvitation.objects.filter(event=instance).delete()
            return
        students = self.cleaned_data.get("invite_students") or Student.objects.none()
        selected_ids = set(students.values_list("id", flat=True))
        existing_ids = set(
            EventInvitation.objects.filter(event=instance).values_list(
                "student_id", flat=True
            )
        )
        for student in students:
            EventInvitation.objects.update_or_create(
                event=instance,
                student=student,
                defaults={"status": EventInvitation.PENDING, "responded_at": None},
            )
        if existing_ids - selected_ids:
            EventInvitation.objects.filter(
                event=instance, student_id__in=existing_ids - selected_ids
            ).delete()


class SessionForm(forms.ModelForm):
    class Meta:
        model = Session
        fields = ["session", "is_current_session"]
        labels = {
            "session": _("Nombre del ciclo lectivo"),
            "is_current_session": _("Es el ciclo actual?"),
        }
        widgets = {
            "session": forms.TextInput(attrs={"class": "form-control"}),
            "is_current_session": forms.Select(
                choices=((True, _("Si")), (False, _("No"))),
                attrs={"class": "browser-default custom-select form-control"},
            ),
        }


class SemesterForm(forms.ModelForm):
    semester = forms.CharField(
        widget=forms.Select(
            choices=SEMESTER,
            attrs={"class": "browser-default custom-select"},
        ),
        label="Cuatrimestre",
    )
    is_current_semester = forms.CharField(
        widget=forms.Select(
            choices=((True, "Si"), (False, "No")),
            attrs={"class": "browser-default custom-select"},
        ),
        label="Es el cuatrimestre actual?",
    )
    session = forms.ModelChoiceField(
        queryset=Session.objects.all(),
        widget=forms.Select(attrs={"class": "browser-default custom-select"}),
        required=True,
        label="Ciclo lectivo",
    )

    class Meta:
        model = Semester
        fields = ["semester", "is_current_semester", "session"]


class BuildingFloorForm(forms.ModelForm):
    class Meta:
        model = BuildingFloor
        fields = ["name", "number", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = [
            "floor",
            "name",
            "code",
            "room_type",
            "capacity",
            "is_enabled",
            "description",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["floor"].widget.attrs.update(
            {"class": "browser-default custom-select form-control"}
        )
        self.fields["room_type"].widget.attrs.update(
            {"class": "browser-default custom-select form-control"}
        )
        self.fields["is_enabled"].widget.attrs.update({"class": "form-check-input"})
        self.fields["capacity"].widget.attrs.update({"class": "form-control"})
        self.fields["name"].widget.attrs.update({"class": "form-control"})
        self.fields["code"].widget.attrs.update({"class": "form-control"})
        self.fields["description"].widget.attrs.update({"class": "form-control"})


class SectionSessionForm(forms.ModelForm):
    class Meta:
        model = SectionSession
        fields = ["date", "start_time", "end_time"]

    def __init__(self, *args, **kwargs):
        self.section = kwargs.pop("section", None)
        super().__init__(*args, **kwargs)
        self.fields["date"].widget.attrs.update({"class": "form-control", "type": "date"})
        self.fields["start_time"].widget.attrs.update(
            {"class": "form-control", "type": "time", "step": "900"}
        )
        self.fields["end_time"].widget.attrs.update(
            {"class": "form-control", "type": "time", "step": "900"}
        )

    def clean(self):
        cleaned = super().clean()
        if self.errors or not self.section:
            return cleaned
        instance = SectionSession(
            section=self.section,
            date=cleaned.get("date"),
            start_time=cleaned.get("start_time"),
            end_time=cleaned.get("end_time"),
        )
        try:
            instance.clean()
        except ValidationError as exc:
            raise forms.ValidationError(exc)
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.section = self.section
        if commit:
            obj.save()
        return obj


class AttendanceJustificationForm(forms.ModelForm):
    class Meta:
        model = AttendanceJustification
        fields = ["submitted_comment", "document"]
        labels = {
            "submitted_comment": _("Comentario"),
            "document": _("Documento de respaldo"),
        }
        widgets = {
            "submitted_comment": forms.Textarea(
                attrs={"class": "form-control", "rows": 3}
            ),
            "document": forms.ClearableFileInput(
                attrs={"class": "form-control", "accept": ".pdf,.jpg,.png"}
            ),
        }


class AttendanceJustificationReviewForm(forms.ModelForm):
    class Meta:
        model = AttendanceJustification
        fields = ["status"]
        labels = {"status": _("Estado")}
        widgets = {
            "status": forms.Select(
                attrs={"class": "browser-default custom-select form-control"}
            )
        }


class SessionDisableForm(forms.Form):
    reason = forms.CharField(
        label="Motivo",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )


class AttendanceUploadForm(forms.ModelForm):
    class Meta:
        model = BulkUploadRequest
        fields = ["kind", "file", "notes"]
        labels = {
            "kind": "Tipo de carga",
            "file": "Archivo (Excel/PDF)",
            "notes": "Notas adicionales",
        }
        widgets = {
            "kind": forms.Select(attrs={"class": "browser-default custom-select form-control"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".xls,.xlsx,.pdf"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }
