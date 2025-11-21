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

try:
    from xhtml2pdf import pisa
except ImportError:  # pragma: no cover
    pisa = None

from accounts.decorators import admin_required
from accounts.filters import LecturerFilter, StudentFilter
from accounts.forms import (
    ProfileUpdateForm,
    ProgramUpdateForm,
    StaffAddForm,
    StaffUpdateForm,
    StudentAddForm,
    StudentUpdateForm,
)
from accounts.models import Student, User
from core.models import Semester, Session
from course.models import Course
from result.models import TakenCourse


# ########################################################
# Utility Functions
# ########################################################


def render_to_pdf(template_name, context):
    """Render a given template to PDF format."""
    if pisa is None:
        return HttpResponse("Generación de PDF no disponible en este entorno.")
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
            messages.success(request, "La cuenta se creó correctamente.")
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
        messages.error(request, "Corregí los errores indicados abajo.")
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
            messages.success(
                request,
                f"Se creó la cuenta de {full_name}. "
                f"En minutos se enviarán las credenciales a {email}.",
            )
            return redirect("lecturer_list")
        messages.error(request, "Corregí los errores indicados abajo.")
    else:
        form = StaffAddForm()
    return render(request, "accounts/add_staff.html", {"form": form})


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
        messages.error(request, "Corregí los errores indicados abajo.")
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
        return HttpResponse("Generación de PDF no disponible.")
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
            messages.success(
                request,
                f"Se creó la cuenta de {full_name}. "
                f"En minutos se enviarán las credenciales a {email}.",
            )
            return redirect("student_list")
        messages.error(request, "Corregí los errores indicados abajo.")
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
        messages.error(request, "Corregí el error indicado abajo.")
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
        return HttpResponse("Generación de PDF no disponible.")
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
        messages.error(request, "Corregí los errores indicados abajo.")
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
            update_session_auth_hash(request, user)
            messages.success(request, "La contraseña se actualizó correctamente.")
            return redirect("change_password")
        else:
            messages.error(request, "Corregí los errores indicados abajo.")
    else:
        form = PasswordChangeForm(user=request.user)
    return render(request, "setting/password_change.html", {"form": form})
