from django import forms
from django.db import transaction
from django.contrib.auth.forms import (
    PasswordResetForm,
    UserChangeForm,
    UserCreationForm,
)
from django.utils.translation import gettext_lazy as _
import json
from pathlib import Path
from django.conf import settings

from course.models import Program
from .models import GENDERS, Student, User


BA_LOCALITIES = [("", "Seleccione una localidad")]


def _load_locality_choices():
    """
    Carga las localidades desde un JSON plano con nombres, con fallback al JSON original.
    Devuelve una lista de tuplas (valor, etiqueta) para ChoiceField.
    """
    path_primary = Path(settings.BASE_DIR) / "static" / "json" / "localidades_nombres.json"
    path_fallback = Path(settings.BASE_DIR) / "static" / "json" / "localidades.json"
    path = path_primary if path_primary.exists() else path_fallback
    base = [("", "Seleccione una localidad")]
    if not path.exists():
        return base
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return base
    names = []
    for item in data or []:
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            name = (
                item.get("name")
                or item.get("nombre")
                or item.get("Nombre")
                or item.get("localidad")
                or item.get("Localidad")
                or item.get("ciudad")
                or item.get("Ciudad")
            )
        else:
            name = None
        if name:
            names.append(str(name).strip())
    cleaned = [n for n in names if n]
    # No eliminamos duplicados para conservar localidades con mismo nombre en provincias distintas.
    cleaned = sorted(cleaned, key=lambda x: x.lower())
    return base + [(n, n) for n in cleaned]


def _load_nationality_choices():
    """
    Carga las nacionalidades desde static/json/nacionalidades.json y las ordena alfabéticamente.
    """
    path = Path(settings.BASE_DIR) / "static" / "json" / "nacionalidades.json"
    base = [("", "Seleccione una nacionalidad")]
    if not path.exists():
        return base
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return base
    names = [str(item).strip() for item in (data or []) if item]
    names = sorted(names, key=lambda x: x.lower())
    return base + [(n, n) for n in names]


class StaffAddForm(UserCreationForm):
    programs_as_coordinator = forms.ModelMultipleChoiceField(
        queryset=Program.objects.all(),
        required=False,
        widget=forms.SelectMultiple(
            attrs={"class": "browser-default custom-select form-control"}
        ),
        label="Carreras como coordinador",
    )
    programs_as_teacher = forms.ModelMultipleChoiceField(
        queryset=Program.objects.all(),
        required=False,
        widget=forms.SelectMultiple(
            attrs={"class": "browser-default custom-select form-control"}
        ),
        label="Carreras como docente",
    )

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "gender",
            "phone",
            "dni",
            "email",
            "role",
            "is_role_active",
            "programs_as_teacher",
            "programs_as_coordinator",
        ]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "gender": forms.Select(
                choices=GENDERS,
                attrs={"class": "browser-default custom-select form-control"},
            ),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "dni": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.TextInput(attrs={"class": "form-control", "type": "email"}),
            "role": forms.Select(
                choices=User.Roles.staff_choices(),
                attrs={"class": "browser-default custom-select form-control"},
            ),
            "is_role_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "username": "Usuario",
            "first_name": "Nombre/s",
            "last_name": "Apellido/s",
            "gender": "Género",
            "phone": "Teléfono",
            "dni": "DNI",
            "email": "Correo electrónico",
            "role": "Rol asignado",
            "is_role_active": "Activo",
        }
        help_texts = {
            "dni": "Ingrese el DNI sin puntos ni espacios.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["programs_as_coordinator"].initial = (
            self.instance.programs_coordinated.all()
            if self.instance and self.instance.pk
            else Program.objects.none()
        )
        self._coordinator_programs = None
        if "role" in self.fields:
            self.fields["role"].choices = [
                (User.Roles.ADMIN, User.Roles.ADMIN.label),
                *User.Roles.staff_choices(),
            ]

    def save(self, commit=True):
        self._coordinator_programs = self.cleaned_data.get("programs_as_coordinator")
        user = super().save(commit)
        if commit:
            self._save_coordinator_programs(user)
        return user

    def save_m2m(self):
        super().save_m2m()
        if self._coordinator_programs is not None:
            self._save_coordinator_programs(self.instance)

    def _save_coordinator_programs(self, user):
        programs = list(self._coordinator_programs) if self._coordinator_programs else []
        user.programs_coordinated.set(programs)


class StaffUpdateForm(UserChangeForm):
    programs_as_coordinator = forms.ModelMultipleChoiceField(
        queryset=Program.objects.all(),
        required=False,
        widget=forms.SelectMultiple(
            attrs={"class": "browser-default custom-select form-control"}
        ),
        label="Carreras como coordinador",
    )

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "gender",
            "email",
            "phone",
            "dni",
            "emergency_contact",
            "is_role_active",
            "programs_as_teacher",
            "programs_as_coordinator",
            "picture",
        ]
        widgets = {
            "gender": forms.Select(
                choices=GENDERS,
                attrs={"class": "browser-default custom-select form-control"},
            ),
            "email": forms.TextInput(
                attrs={"class": "form-control", "type": "email"}
            ),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "dni": forms.TextInput(attrs={"class": "form-control"}),
            "emergency_contact": forms.TextInput(attrs={"class": "form-control"}),
            "is_role_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        help_texts = {
            "dni": "Ingrese el DNI sin puntos ni espacios.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["programs_as_coordinator"].initial = (
            self.instance.programs_coordinated.all()
            if self.instance and self.instance.pk
            else Program.objects.none()
        )
        self._coordinator_programs = None

    def save(self, commit=True):
        self._coordinator_programs = self.cleaned_data.get("programs_as_coordinator")
        user = super().save(commit)
        if commit:
            self._save_coordinator_programs(user)
        return user

    def save_m2m(self):
        super().save_m2m()
        if self._coordinator_programs is not None:
            self._save_coordinator_programs(self.instance)

    def _save_coordinator_programs(self, user):
        programs = list(self._coordinator_programs) if self._coordinator_programs else []
        user.programs_coordinated.set(programs)


class StudentAddForm(UserCreationForm):
    programs = forms.ModelMultipleChoiceField(
        queryset=Program.objects.all(),
        widget=forms.SelectMultiple(
            attrs={"class": "browser-default custom-select form-control", "size": 6}
        ),
        label="Carreras",
        required=True,
    )
    locality = forms.ChoiceField(
        choices=BA_LOCALITIES,
        label="Localidad",
        required=True,
        widget=forms.Select(
            attrs={
                "class": "browser-default custom-select form-control",
                "data-live-search": "true",
            }
        ),
    )
    nationality = forms.ChoiceField(
        choices=[("", "Seleccione una nacionalidad")],
        label="Nacionalidad",
        widget=forms.Select(
            attrs={"class": "browser-default custom-select form-control"}
        ),
        required=True,
    )

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "gender",
            "address",
            "locality",
            "nationality",
            "phone",
            "dni",
            "email",
            "emergency_contact",
            "programs",
            "is_role_active",
        ]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "gender": forms.Select(
                choices=GENDERS,
                attrs={"class": "browser-default custom-select form-control"},
            ),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "locality": forms.Select(
                attrs={
                    "class": "browser-default custom-select form-control",
                    "data-live-search": "true",
                }
            ),
            "nationality": forms.Select(
                attrs={"class": "browser-default custom-select form-control"}
            ),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "dni": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.TextInput(attrs={"class": "form-control", "type": "email"}),
            "emergency_contact": forms.TextInput(attrs={"class": "form-control"}),
            "programs": forms.SelectMultiple(
                attrs={"class": "browser-default custom-select form-control", "size": 6}
            ),
            "is_role_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "username": "Usuario",
            "first_name": "Nombre/s",
            "last_name": "Apellido/s",
            "gender": "Género",
            "address": "Dirección",
            "locality": "Localidad",
            "nationality": "Nacionalidad",
            "phone": "Teléfono",
            "dni": "DNI",
            "email": "Correo electrónico",
            "emergency_contact": "Contacto de emergencia",
            "programs": "Carreras",
            "is_role_active": "Activo",
        }
        help_texts = {
            "dni": "Ingrese el DNI sin puntos ni espacios.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "locality" in self.fields:
            self.fields["locality"].choices = _load_locality_choices()
        if "nationality" in self.fields:
            self.fields["nationality"].choices = _load_nationality_choices()

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Roles.STUDENT
        if commit:
            user.save()
            programs = list(self.cleaned_data.get("programs") or [])
            primary = programs[0] if programs else None
            student, _ = Student.objects.get_or_create(student=user)
            if primary:
                student.program = primary
            student.save()
            if programs:
                student.programs.set(programs)
        return user


class StudentUpdateForm(UserChangeForm):
    programs = forms.ModelMultipleChoiceField(
        queryset=Program.objects.all(),
        widget=forms.SelectMultiple(
            attrs={"class": "browser-default custom-select form-control", "size": 6}
        ),
        label="Carreras",
        required=False,
    )
    nationality = forms.ChoiceField(
        choices=[("", "Seleccione una nacionalidad")],
        label="Nacionalidad",
        required=False,
        widget=forms.Select(
            attrs={"class": "browser-default custom-select form-control"}
        ),
    )

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "gender",
            "email",
            "phone",
            "address",
            "locality",
            "nationality",
            "dni",
            "emergency_contact",
            "is_role_active",
            "programs",
        ]
        widgets = {
            "gender": forms.Select(
                choices=GENDERS,
                attrs={"class": "browser-default custom-select form-control"},
            ),
            "email": forms.TextInput(
                attrs={"class": "form-control", "type": "email"}
            ),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "locality": forms.Select(
                choices=BA_LOCALITIES,
                attrs={
                    "class": "browser-default custom-select form-control",
                    "data-live-search": "true",
                },
            ),
            "nationality": forms.Select(
                attrs={"class": "browser-default custom-select form-control"}
            ),
            "dni": forms.TextInput(attrs={"class": "form-control"}),
            "emergency_contact": forms.TextInput(attrs={"class": "form-control"}),
            "is_role_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "programs": forms.SelectMultiple(
                attrs={"class": "browser-default custom-select form-control", "size": 6}
            ),
        }
        help_texts = {
            "dni": "Ingrese el DNI sin puntos ni espacios.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "locality" in self.fields:
            self.fields["locality"].choices = _load_locality_choices()
        if "nationality" in self.fields:
            self.fields["nationality"].choices = _load_nationality_choices()
        if self.instance and self.instance.pk:
            try:
                student = Student.objects.get(student=self.instance)
                self.fields["programs"].initial = student.programs.all()
            except Student.DoesNotExist:
                pass

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            student, _ = Student.objects.get_or_create(student=user)
            programs = list(self.cleaned_data.get("programs") or [])
            if programs:
                student.program = programs[0]
                student.save()
                student.programs.set(programs)
            else:
                student.programs.clear()
        return user


class ProgramUpdateForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["program"]
        widgets = {
            "program": forms.Select(
                attrs={"class": "browser-default custom-select form-control"}
            )
        }


class ProfileUpdateForm(UserChangeForm):
    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "gender",
            "email",
            "phone",
            "address",
            "dni",
            "emergency_contact",
            "is_role_active",
            "picture",
        ]
        widgets = {
            "gender": forms.Select(
                choices=GENDERS,
                attrs={"class": "browser-default custom-select form-control"},
            ),
            "email": forms.TextInput(
                attrs={"class": "form-control", "type": "email"}
            ),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "dni": forms.TextInput(attrs={"class": "form-control"}),
            "emergency_contact": forms.TextInput(attrs={"class": "form-control"}),
            "is_role_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        help_texts = {
            "dni": "Ingrese el DNI sin puntos ni espacios.",
        }


class EmailValidationOnForgotPassword(PasswordResetForm):
    def clean_email(self):
        email = self.cleaned_data["email"]
        if not User.objects.filter(email__iexact=email, is_active=True).exists():
            msg = _("No existe un usuario con este correo electrónico.")
            self.add_error("email", msg)
        return email


