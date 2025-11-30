from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template, render_to_string
from django.utils.decorators import method_decorator
from django.views.generic import CreateView
from django_filters.views import FilterView
from accounts.decorators import admin_required
from accounts.filters import LecturerFilter, StudentFilter
from accounts.forms import (
    ProfileUpdateForm,
    ProgramUpdateForm,
    StaffAddForm,
    StaffUpdateForm,
    StudentAddForm,
    StudentUpdateForm,
    StudentUploadForm,
)
from accounts.models import Student, User
from accounts.utils import send_new_account_email
from core.models import Semester, Session
from course.models import Course
from course.models import Program
from core.services.ai_ingestion import _read_rows, _extract_text, _rows_from_llm
from result.models import TakenCourse

try:
    from xhtml2pdf import pisa
except ImportError:  # pragma: no cover
    pisa = None


# ########################################################
# Utility Functions
# ########################################################


def render_to_pdf(template_name, context):
    """Render a given template to PDF format."""
    if pisa is None:
        return HttpResponse("GeneraciÃ³n de PDF no disponible en este entorno.")
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'filename="profile.pdf"'
    template = render_to_string(template_name, context)
    pdf = pisa.CreatePDF(template, dest=response)
    if pdf.err:
        return HttpResponse("Tuvimos problemas al generar el PDF")
    return response


# ########################################################
# Authentication and Registration
# ########################################################


def validate_username(request):
    username = request.GET.get("username", None)
    data = {"is_taken": User.objects.filter(username__iexact=username).exists()}
    return JsonResponse(data)


def register(request):
    if request.method == "POST":
        form = StudentAddForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "La cuenta se creÃ³ correctamente.")
            return redirect("login")
        messages.error(
            request, "Hay campos incorrectos. Completalos correctamente."
        )
    else:
        form = StudentAddForm()
    return render(request, "registration/register.html", {"form": form})


# ########################################################
# Profile Views
# ########################################################


@login_required
def profile(request):
    """Show profile of the current user."""
    current_session = Session.objects.filter(is_current_session=True).first()
    current_semester = Semester.objects.filter(
        is_current_semester=True, session=current_session
    ).first()

    context = {
        "title": request.user.get_full_name,
        "current_session": current_session,
        "current_semester": current_semester,
    }

    if request.user.is_lecturer:
        courses = Course.objects.filter(
            allocated_course__lecturer__pk=request.user.id, semester=current_semester
        )
        context["courses"] = courses
        return render(request, "accounts/profile.html", context)

    if request.user.is_student:
        student = get_object_or_404(Student, student__pk=request.user.id)
        courses = TakenCourse.objects.filter(
            student__student__id=request.user.id, course__level=student.level
        )
        context.update({"courses": courses, "level": student.level})
        return render(request, "accounts/profile.html", context)

    staff = User.objects.filter(is_lecturer=True)
    context["staff"] = staff
    return render(request, "accounts/profile.html", context)


@login_required
def profile_update(request):
    """Allow current user to update their profile information."""
    if request.method == "POST":
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Perfil actualizado correctamente.")
            return redirect("profile")
        messages.error(request, "CorregÃ­ los errores indicados abajo.")
    else:
        form = ProfileUpdateForm(instance=request.user)
    return render(
        request,
        "accounts/profile.html",
        {"title": "Editar perfil", "form": form, "is_profile_form": True},
    )


@login_required
@admin_required
def admin_panel(request):
    """Custom admin dashboard with quick stats."""
    student_count = User.objects.filter(is_student=True).count()
    lecturer_count = User.objects.filter(is_lecturer=True).count()
    staff_count = User.objects.filter(role__in=[choice[0] for choice in User.Roles.staff_choices()]).count()
    context = {
        "student_count": student_count,
        "lecturer_count": lecturer_count,
        "staff_count": staff_count,
    }
    return render(request, "setting/admin_panel.html", context)


@login_required
@admin_required
def profile_single(request, user_id):
    """Show profile of any selected user."""
    if request.user.id == user_id:
        return redirect("profile")

    current_session = Session.objects.filter(is_current_session=True).first()
    current_semester = Semester.objects.filter(
        is_current_semester=True, session=current_session
    ).first()
    user = get_object_or_404(User, pk=user_id)

    context = {
        "title": user.get_full_name,
        "current_session": current_session,
        "current_semester": current_semester,
        "user": user,
    }

    if user.is_lecturer:
        courses = Course.objects.filter(
            allocated_course__lecturer__pk=user.id, semester=current_semester
        )
        context["courses"] = courses
        return render(request, "accounts/profile_single.html", context)

    if user.is_student:
        student = get_object_or_404(Student, student__pk=user.id)
        courses = TakenCourse.objects.filter(
            student__student__id=user.id, course__level=student.level
        )
        context.update({"courses": courses, "level": student.level})
        return render(request, "accounts/profile_single.html", context)

    staff = User.objects.filter(is_lecturer=True)
    context["staff"] = staff
    return render(request, "accounts/profile_single.html", context)


# ########################################################
# Staff Views
# ########################################################


@login_required
@admin_required
def staff_add_view(request):
    if request.method == "POST":
        form = StaffAddForm(request.POST)
        if form.is_valid():
            staff = form.save()
            full_name = staff.get_full_name
            email = staff.email
            if email and staff.dni:
                send_new_account_email(staff, staff.dni)
            messages.success(
                request,
                f"Se creÃ³ la cuenta de {full_name}. "
                f"En minutos se enviarÃ¡n las credenciales a {email}.",
            )
            return redirect("lecturer_list")
        messages.error(request, "CorregÃ­ los errores indicados abajo.")
    else:
        form = StaffAddForm()
    return render(request, "accounts/add_staff.html", {"form": form, "title": "Agregar docente"})


@login_required
@admin_required
def edit_staff(request, pk):
    staff_user = get_object_or_404(User, pk=pk, is_lecturer=True)
    if request.method == "POST":
        form = StaffUpdateForm(request.POST, request.FILES, instance=staff_user)
        if form.is_valid():
            form.save()
            full_name = staff_user.get_full_name
            messages.success(
                request, f"Docente {full_name} actualizado correctamente."
            )
            return redirect("lecturer_list")
        messages.error(request, "CorregÃ­ los errores indicados abajo.")
    else:
        form = StaffUpdateForm(instance=staff_user)
    return render(
        request,
        "accounts/add_staff.html",
        {"title": "Editar docente", "form": form},
    )


@method_decorator([login_required, admin_required], name="dispatch")
class LecturerFilterView(FilterView):
    queryset = User.objects.filter(is_lecturer=True)
    filterset_class = LecturerFilter
    template_name = "accounts/lecturer_list.html"
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Docentes"
        return context


@login_required
@admin_required
def render_lecturer_pdf_list(request):
    lecturers = User.objects.filter(is_lecturer=True)
    template_path = "pdf/lecturer_list.html"
    context = {"lecturers": lecturers}
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'filename="lista_docentes.pdf"'
    template = get_template(template_path)
    html = template.render(context)
    if pisa is None:
        return HttpResponse("GeneraciÃ³n de PDF no disponible.")
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse(f"Se produjeron errores al generar el PDF <pre>{html}</pre>")
    return response


@login_required
@admin_required
def delete_staff(request, pk):
    lecturer = get_object_or_404(User, is_lecturer=True, pk=pk)
    full_name = lecturer.get_full_name
    lecturer.delete()
    messages.success(request, f"Docente {full_name} eliminado correctamente.")
    return redirect("lecturer_list")


# ########################################################
# Student Views
# ########################################################


@login_required
@admin_required
def student_add_view(request):
    if request.method == "POST":
        form = StudentAddForm(request.POST)
        if form.is_valid():
            student = form.save()
            full_name = student.get_full_name
            email = student.email
            if email and student.dni:
                send_new_account_email(student, student.dni)
            messages.success(
                request,
                f"Se creÃ³ la cuenta de {full_name}. "
                f"En minutos se enviarÃ¡n las credenciales a {email}.",
            )
            return redirect("student_list")
        messages.error(request, "CorregÃ­ los errores indicados abajo.")
    else:
        form = StudentAddForm()
    return render(
        request, "accounts/add_student.html", {"title": "Agregar estudiante", "form": form}
    )


@login_required
@admin_required
def edit_student(request, pk):
    student_user = get_object_or_404(User, is_student=True, pk=pk)
    if request.method == "POST":
        form = StudentUpdateForm(request.POST, request.FILES, instance=student_user)
        if form.is_valid():
            form.save()
            full_name = student_user.get_full_name
            messages.success(request, f"Estudiante {full_name} actualizado correctamente.")
            return redirect("student_list")
        messages.error(request, "CorregÃ­ el error indicado abajo.")
    else:
        form = StudentUpdateForm(instance=student_user)
    return render(
        request, "accounts/edit_student.html", {"title": "Editar estudiante", "form": form}
    )


@method_decorator([login_required, admin_required], name="dispatch")
class StudentListView(FilterView):
    queryset = Student.objects.all()
    filterset_class = StudentFilter
    template_name = "accounts/student_list.html"
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Estudiantes"
        return context


@login_required
@admin_required
def render_student_pdf_list(request):
    students = Student.objects.all()
    template_path = "pdf/student_list.html"
    context = {"students": students}
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'filename="lista_estudiantes.pdf"'
    template = get_template(template_path)
    html = template.render(context)
    if pisa is None:
        return HttpResponse("GeneraciÃ³n de PDF no disponible.")
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse(f"Se produjeron errores al generar el PDF <pre>{html}</pre>")
    return response


@login_required
@admin_required
def delete_student(request, pk):
    student = get_object_or_404(Student, pk=pk)
    full_name = student.student.get_full_name
    student.delete()
    messages.success(request, f"Estudiante {full_name} eliminado correctamente.")
    return redirect("student_list")


@login_required
@admin_required
def edit_student_program(request, pk):
    student = get_object_or_404(Student, student_id=pk)
    user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = ProgramUpdateForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            form.save()
            full_name = user.get_full_name
            messages.success(request, f"La carrera de {full_name} fue actualizada.")
            return redirect("profile_single", user_id=pk)
        messages.error(request, "CorregÃ­ los errores indicados abajo.")
    else:
        form = ProgramUpdateForm(instance=student)
    return render(
        request,
        "accounts/edit_student_program.html",
        {"title": "Editar carrera", "form": form, "student": student},
    )


# ########################################################
# Password Change
# ########################################################


@login_required
def change_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            if getattr(user, "must_change_password", False):
                user.must_change_password = False
                user.save(update_fields=["must_change_password"])
            update_session_auth_hash(request, user)
            messages.success(request, "La contraseÃ±a se actualizÃ³ correctamente.")
            return redirect("home")
        else:
            messages.error(request, "CorregÃ­ los errores indicados abajo.")
    else:
        form = PasswordChangeForm(user=request.user)
    return render(request, "setting/password_change.html", {"form": form})

@login_required
@admin_required
def student_upload_view(request):
    form = StudentUploadForm(request.POST or None, request.FILES or None)
    created, skipped, errors = [], [], []
    if request.method == "POST" and form.is_valid():
        uploaded = form.cleaned_data["file"]
        target_program = form.cleaned_data.get("program")
        tmp_path = None
        processed_rows = 0
        try:
            from tempfile import NamedTemporaryFile
            from pathlib import Path
            from core.services.ai_ingestion import _rows_from_llm_students
            tmp = NamedTemporaryFile(delete=False, suffix=Path(uploaded.name).suffix or ".dat")
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            tmp.close()
            tmp_path = Path(tmp.name)
            try:
                rows = _read_rows(tmp_path)
            except Exception:
                # Solo soportamos ahora CSV/XLSX; otros formatos no se procesan
                rows = []
            # Si no se detectan columnas útiles, pedir al LLM que mapée a campos de alumno
            if rows and isinstance(rows, list) and rows and isinstance(rows[0], dict):
                sample = rows[:5]
                headers = list(sample[0].keys())
                header_lower = [str(k).lower() for k in headers]
                has_dni = any("dni" in k or "document" in k for k in header_lower)
                has_mail = any("mail" in k or "email" in k or "correo" in k for k in header_lower)
                needs_llm = not (has_dni and has_mail)
                if needs_llm:
                    rows = _rows_from_llm_students(
                        headers=", ".join(map(str, headers)),
                        sample_rows="\n".join([str(r) for r in sample]),
                    )

            if not rows:
                errors.append("No se encontraron datos en el archivo. Verifica formato/encabezados.")

            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                processed_rows += 1

                # Heurísticas de detección de columnas
                lower_map = {str(k).lower(): v for k, v in row.items()}
                raw_dni = row.get("dni") or row.get("DNI") or lower_map.get("documento") or lower_map.get("doc") or ""
                if isinstance(raw_dni, (int, float)):
                    raw_dni = int(raw_dni)
                dni = str(raw_dni).strip()
                if dni.replace(".", "", 1).isdigit():
                    try:
                        dni = str(int(float(dni)))
                    except Exception:
                        dni = dni

                # Nombre / Apellido
                first = str(
                    row.get("first_name")
                    or row.get("nombre")
                    or row.get("Nombre")
                    or row.get("Nombres")
                    or lower_map.get("nombre(s)")
                    or lower_map.get("nombres")
                    or ""
                ).strip()
                last = str(
                    row.get("last_name")
                    or row.get("apellido")
                    or row.get("Apellido(s)")
                    or row.get("Apellido")
                    or lower_map.get("apellidos")
                    or lower_map.get("apellido")
                    or row.get("Apellidos")
                    or ""
                ).strip()

                # Email: buscar en campos conocidos o cualquier valor con @
                email = str(
                    row.get("email")
                    or row.get("Email")
                    or row.get("Email_Falso")
                    or row.get("Mail")
                    or row.get("Correo")
                    or lower_map.get("correo")
                    or lower_map.get("mail")
                    or ""
                ).strip()
                if not email:
                    for val in row.values():
                        if isinstance(val, str) and "@" in val:
                            email = val.strip()
                            break
                # Normalizar email; si no es válido, usar uno placeholder
                from django.core.validators import validate_email
                from django.core.exceptions import ValidationError as DjangoValidationError
                if not email:
                    email = f"{dni}@nomail.invalid"
                else:
                    try:
                        validate_email(email)
                    except DjangoValidationError:
                        email = f"{dni}@nomail.invalid"

                # Legajo
                legajo = str(
                    row.get("legajo")
                    or row.get("Codigo")
                    or row.get("Código")
                    or lower_map.get("codigo")
                    or lower_map.get("id")
                    or ""
                ).strip() or None

                # Faltantes obligatorios
                if not dni or not first or not last:
                    errors.append(f"Fila incompleta: {row}")
                    continue

                if User.objects.filter(dni=dni).exists():
                    skipped.append(dni)
                    continue

                user = User(
                    username=dni,
                    dni=dni,
                    first_name=first,
                    last_name=last,
                    email=email,
                    role=User.Roles.STUDENT,
                    is_student=True,
                    must_change_password=True,
                    is_active=True,
                )
                user.set_password(dni)
                user.save()
                student, _ = Student.objects.get_or_create(student=user)
                student.legajo = legajo
                if target_program:
                    student.program = target_program
                    student.save()
                    student.programs.set([target_program])
                else:
                    student.save()
                progs_txt = str(row.get("programas") or row.get("programs") or "").strip()
                program_titles = [p.strip() for p in progs_txt.split(",") if p.strip()]
                programs = Program.objects.filter(title__in=program_titles)
                if programs and not target_program:
                    student.program = programs.first()
                    student.save()
                    student.programs.set(programs)
                student.save()
                created.append(dni)
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
        if processed_rows == 0 and not errors:
            errors.append("No se pudo interpretar el archivo. Asegúrate de que tenga encabezados (ej: DNI, Nombre, Apellido, Email).")
        elif not created and not errors:
            errors.append("No se pudo crear ningún alumno. Verifica que los DNI no estén ya cargados o ajusta los encabezados.")
        if errors:
            messages.error(
                request,
                f"Altas creadas: {len(created)}. Repetidos: {len(skipped)}. Errores: {len(errors)}.",
            )
        else:
            messages.success(
                request,
                f"Altas creadas: {len(created)}. Repetidos: {len(skipped)}. Errores: {len(errors)}.",
            )
    return render(
        request,
        "accounts/student_upload.html",
        {"form": form, "created": created, "skipped": skipped, "errors": errors, "title": "Importar estudiantes"},
    )
