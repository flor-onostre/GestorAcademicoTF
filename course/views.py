import math
from datetime import timedelta, datetime
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, ListView
from django_filters.views import FilterView

from accounts.decorators import admin_required, lecturer_required, student_required
from accounts.models import Student, User
from core.forms import (
    AttendanceJustificationForm,
    AttendanceJustificationReviewForm,
    AttendanceUploadForm,
    SectionSessionForm,
    SessionDisableForm,
)
from core.models import (
    AttendanceJustification,
    AttendanceRecord,
    BulkUploadRequest,
    Room,
    RoomBlock,
    SectionSession,
    Semester,
)
from core.services.ai_ingestion import enqueue_ai_processing
from core.notifications import (
    notify_absence,
    notify_teacher_missing_attendance,
    notify_bedelia_teacher_missing,
    notify_justification_result,
    notify_room_change,
)
from course.filters import CourseAllocationFilter, ProgramFilter
from course.forms import (
    CourseAddForm,
    CourseAllocationForm,
    CourseSectionForm,
    EditCourseAllocationForm,
    ProgramForm,
    UniversityForm,
    UploadFormFile,
    UploadFormVideo,
    SectionEnrollmentForm,
    SectionEnrollmentUploadForm,
)
from course.models import (
    Course,
    CourseAllocation,
    CourseSection,
    Program,
    University,
    Upload,
    UploadVideo,
)
from result.models import TakenCourse


def _can_manage_sections(user):
    return user.is_authenticated and (
        user.is_superuser
        or getattr(user, "role", None)
        in {User.Roles.COORDINATOR, User.Roles.ADMIN, User.Roles.BEDEL, User.Roles.MANAGEMENT}
    )


def _get_accessible_programs(user):
    if not user.is_authenticated:
        return Program.objects.none()
    if user.is_superuser:
        return Program.objects.all()
    if getattr(user, "role", None) == User.Roles.COORDINATOR:
        return Program.objects.filter(coordinators=user).distinct()
    return Program.objects.none()


def ensure_section_permission(user):
    if not _can_manage_sections(user):
        raise PermissionDenied


def ensure_section_access(user, section):
    if user.is_superuser:
        return
    role = getattr(user, "role", None)
    if role in {User.Roles.ADMIN, User.Roles.BEDEL, User.Roles.MANAGEMENT}:
        return
    if role == User.Roles.COORDINATOR and section.program.coordinators.filter(
        pk=user.pk
    ).exists():
        return
    raise PermissionDenied


def _section_students(section):
    return Student.objects.filter(
        takencourse__course=section.course
    ).distinct().select_related("student")


def _regularity_status(section, student):
    from core.models import SectionSession, AttendanceRecord

    total_sessions = SectionSession.objects.filter(
        section=section, date__lte=timezone.now()
    ).count()
    if total_sessions == 0:
        return True, 0, 0
    present_count = AttendanceRecord.objects.filter(
        session__section=section,
        student=student,
        status__in=[AttendanceRecord.PRESENT, AttendanceRecord.JUSTIFIED],
    ).count()
    required = section.attendance_required or section.program.min_passing_attendance
    required = required or 0
    percentage = (present_count / total_sessions) * 100
    allowed_absences = max(
        0,
        total_sessions - math.ceil((required / 100) * total_sessions),
    )
    absences = total_sessions - present_count
    remaining = max(0, allowed_absences - absences)
    return percentage >= required, remaining, allowed_absences


DAY_TO_WEEKDAY = {
    "lunes": 0,
    "martes": 1,
    "miÃ©rcoles": 2,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sÃ¡bado": 5,
    "sabado": 5,
    "domingo": 6,
}


def _generate_section_sessions(section):
    """
    Genera las clases de cursada segÃºn dÃ­as/horarios definidos en la comisiÃ³n.
    Borra las existentes y recrea.
    """
    SectionSession.objects.filter(section=section).delete()
    if not section.start_date or not section.end_date or not section.days_of_week:
        return

    schedule_map = {}
    for item in getattr(section, "schedule_by_day", []) or []:
        day = (item.get("day") or "").lower()
        start = item.get("start")
        end = item.get("end")
        if day and start and end:
            schedule_map[day] = (start, end)

    current = section.start_date
    while current <= section.end_date:
        weekday = current.weekday()
        for day_name in section.days_of_week:
            day_num = DAY_TO_WEEKDAY.get(day_name.lower())
            if day_num is None or day_num != weekday:
                continue
            schedule = schedule_map.get(day_name.lower())
            if schedule:
                start_str, end_str = schedule
            else:
                if not section.start_time or not section.end_time:
                    continue
                start_str = section.start_time.strftime("%H:%M")
                end_str = section.end_time.strftime("%H:%M")
            try:
                start_time = timezone.datetime.strptime(start_str, "%H:%M").time()
                end_time = timezone.datetime.strptime(end_str, "%H:%M").time()
            except ValueError:
                continue
            SectionSession.objects.create(
                section=section, date=current, start_time=start_time, end_time=end_time
            )
        current += timedelta(days=1)



def _time_windows(section):
    windows = []
    schedule_map = {}
    for item in getattr(section, "schedule_by_day", []) or []:
        day = (item.get("day") or "").lower()
        start = item.get("start")
        end = item.get("end")
        if day and start and end:
            try:
                start_t = datetime.strptime(start, "%H:%M").time()
                end_t = datetime.strptime(end, "%H:%M").time()
            except ValueError:
                continue
            schedule_map[day] = (start_t, end_t)
    for day in section.days_of_week or []:
        key = day.lower()
        if schedule_map.get(key):
            start_t, end_t = schedule_map[key]
        else:
            if not section.start_time or not section.end_time:
                continue
            start_t, end_t = section.start_time, section.end_time
        windows.append((key, start_t, end_t))
    return windows


def _room_available(room, section):
    # Conflictos por bloqueos
    for sess in section.sessions.all():
        blocks = RoomBlock.objects.filter(
            room=room,
            is_active=True,
            start_date__lte=sess.date,
            end_date__gte=sess.date,
        )
        for block in blocks:
            if not block.start_time or not block.end_time:
                return False
            if block.start_time < sess.end_time and block.end_time > sess.start_time:
                return False

    # Conflictos con otras comisiones en la misma sala
    windows = _time_windows(section)
    others = CourseSection.objects.filter(room=room).exclude(pk=section.pk)
    for other in others:
        if other.start_date > section.end_date or other.end_date < section.start_date:
            continue
        other_windows = _time_windows(other)
        for d1, s1, e1 in windows:
            for d2, s2, e2 in other_windows:
                if d1 == d2 and s1 < e2 and e1 > s2:
                    return False
    return True


def _auto_assign_room(section):
    if section.room_id:
        return None
    sessions = list(section.sessions.all())
    if not sessions:
        return None
    capacity_needed = section.max_capacity or section.students.count()
    rooms = Room.objects.filter(is_enabled=True).order_by("capacity", "code")
    for room in rooms:
        if room.capacity and capacity_needed and room.capacity < capacity_needed:
            continue
        if _room_available(room, section):
            section.room = room
            section.save(update_fields=["room"])
            return room
    return None


# ########################################################
# Program Views
# ########################################################


@login_required
@admin_required
def university_list(request):
    universities = University.objects.order_by("name")
    return render(
        request,
        "course/university_list.html",
        {"title": "Universidades", "universities": universities},
    )


@login_required
@admin_required
def university_add(request):
    if request.method == "POST":
        form = UniversityForm(request.POST)
        if form.is_valid():
            uni = form.save()
            messages.success(request, f"Se creÃ³ la universidad {uni.name}.")
            return redirect("university_list")
        messages.error(request, "Corrige los errores indicados abajo.")
    else:
        form = UniversityForm()
    return render(
        request, "course/university_form.html", {"title": "Agregar universidad", "form": form}
    )


@login_required
@admin_required
def university_edit(request, pk):
    uni = get_object_or_404(University, pk=pk)
    if request.method == "POST":
        form = UniversityForm(request.POST, instance=uni)
        if form.is_valid():
            uni = form.save()
            messages.success(request, f"Se actualizÃ³ la universidad {uni.name}.")
            return redirect("university_list")
        messages.error(request, "Corrige los errores indicados abajo.")
    else:
        form = UniversityForm(instance=uni)
    return render(
        request, "course/university_form.html", {"title": "Editar universidad", "form": form}
    )


@login_required
@admin_required
def university_delete(request, pk):
    uni = get_object_or_404(University, pk=pk)
    name = uni.name
    uni.delete()
    messages.success(request, f"Se eliminÃ³ la universidad {name}.")
    return redirect("university_list")


@method_decorator([login_required, lecturer_required], name="dispatch")
class ProgramFilterView(FilterView):
    filterset_class = ProgramFilter
    template_name = "course/program_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Carreras"
        return context


@login_required
@admin_required
def program_add(request):
    if request.method == "POST":
        form = ProgramForm(request.POST)
        if form.is_valid():
            program = form.save()
            messages.success(request, f"Se creÃ³ la carrera {program.title}.")
            return redirect("programs")
        messages.error(request, "Corrige los errores indicados abajo.")
    else:
        form = ProgramForm()
    return render(
        request, "course/program_add.html", {"title": "Agregar carrera", "form": form}
    )


@login_required
def program_detail(request, pk):
    program = get_object_or_404(Program, pk=pk)
    courses_qs = (
        Course.objects.filter(programs__id=pk)
        .prefetch_related("programs")
        .order_by("title")
        .distinct()
    )
    credits = courses_qs.aggregate(total_credits=Sum("credit"))
    paginator = Paginator(courses_qs, 10)
    page = request.GET.get("page")
    courses = paginator.get_page(page)
    lecturers = (
        User.objects.filter(role=User.Roles.TEACHER, programs_as_teacher__id=pk)
        .distinct()
        .order_by("first_name", "last_name")
    )
    return render(
        request,
        "course/program_single.html",
        {
            "title": program.title,
            "program": program,
            "courses": courses,
            "credits": credits,
            "lecturers": lecturers,
        },
    )


@login_required
@admin_required
def program_edit(request, pk):
    program = get_object_or_404(Program, pk=pk)
    if request.method == "POST":
        form = ProgramForm(request.POST, instance=program)
        if form.is_valid():
            program = form.save()
            messages.success(request, f"Se actualizÃ³ la carrera {program.title}.")
            return redirect("programs")
        messages.error(request, "Corrige los errores indicados abajo.")
    else:
        form = ProgramForm(instance=program)
    return render(
        request, "course/program_add.html", {"title": "Editar carrera", "form": form}
    )


@login_required
@admin_required
def program_delete(request, pk):
    program = get_object_or_404(Program, pk=pk)
    title = program.title
    program.delete()
    messages.success(request, f"Se eliminÃ³ la carrera {title}.")
    return redirect("programs")


@method_decorator([login_required, lecturer_required], name="dispatch")
class CourseFilterView(ListView):
    template_name = "course/course_list.html"
    paginate_by = 20

    def get_queryset(self):
        qs = Course.objects.prefetch_related("programs").order_by("title")
        program_id = self.request.GET.get("program") or ""
        if program_id.isdigit():
            qs = qs.filter(programs__id=program_id)
        keyword = self.request.GET.get("q")
        if keyword:
            qs = qs.filter(
                Q(title__icontains=keyword)
                | Q(code__icontains=keyword)
            ).distinct()
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Materias"
        context["programs"] = Program.objects.order_by("title")
        context["selected_program"] = self.request.GET.get("program") or ""
        context["keyword"] = self.request.GET.get("q") or ""
        return context


# ########################################################
# Course Views
# ########################################################


@login_required
def course_single(request, slug):
    course = get_object_or_404(Course, slug=slug)
    sections = (
        CourseSection.objects.filter(course=course)
        .select_related("semester", "semester__session", "turn", "room")
        .prefetch_related("teachers")
    )
    return render(
        request,
        "course/course_single.html",
        {
            "title": course.title,
            "course": course,
            "sections": sections,
        },
    )


@login_required
@lecturer_required
def course_add(request, pk):
    program = get_object_or_404(Program, pk=pk)
    if request.method == 'POST':
        form = CourseAddForm(request.POST)
        if form.is_valid():
            course = form.save()
            messages.success(request, f'Se creÃ³ la materia {course.title} ({course.code}).')
            return redirect('course_list')
        messages.error(request, 'Corrige los errores indicados abajo.')
    else:
        form = CourseAddForm(initial={'program': program})
    return render(
        request,
        'course/course_add.html',
        {'title': 'Agregar materia', 'form': form, 'program': program},
    )


@login_required
@lecturer_required
def course_edit(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if request.method == 'POST':
        form = CourseAddForm(request.POST, instance=course)
        if form.is_valid():
            course = form.save()
            messages.success(request, f'Se actualizÃ³ la materia {course.title} ({course.code}).')
            return redirect('course_list')
        messages.error(request, 'Corrige los errores indicados abajo.')
    else:
        form = CourseAddForm(instance=course)
    return render(
        request, 'course/course_add.html', {'title': 'Editar materia', 'form': form}
    )
def course_edit(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if request.method == "POST":
        form = CourseAddForm(request.POST, instance=course)
        if form.is_valid():
            course = form.save()
            messages.success(
                request, f"Se actualizÃ³ la materia {course.title} ({course.code})."
            )
            return redirect("course_list")
        messages.error(request, "Corrige los errores indicados abajo.")
    else:
        form = CourseAddForm(instance=course)
    return render(
        request, "course/course_add.html", {"title": "Editar materia", "form": form}
    )


@login_required
@lecturer_required
def course_delete(request, slug):
    course = get_object_or_404(Course, slug=slug)
    title = course.title
    program_id = course.program.id
    course.delete()
    messages.success(request, f"Se eliminÃ³ la materia {title}.")
    return redirect("program_detail", pk=program_id)


# ########################################################
# Course Section Views
# ########################################################


@login_required
def course_section_list(request):
    ensure_section_permission(request.user)
    programs = _get_accessible_programs(request.user)
    sections = (
        CourseSection.objects.select_related(
            "course", "program", "semester", "turn", "room"
        )
        .prefetch_related("teachers")
        .order_by("course__title", "turn__name")
    )
    if not request.user.is_superuser:
        sections = sections.filter(program__in=programs)
    selected_program = request.GET.get("program") or None
    selected_course = request.GET.get("course") or None
    if selected_program:
        try:
            selected_program_id = int(selected_program)
        except (TypeError, ValueError):
            selected_program_id = None
        else:
            if request.user.is_superuser or programs.filter(
                pk=selected_program_id
            ).exists():
                sections = sections.filter(program_id=selected_program_id)
            else:
                selected_program_id = None
        selected_program = selected_program_id
    if selected_course:
        sections = sections.filter(course__id=selected_course)
    context = {
        "title": "Comisiones",
        "sections": sections,
        "programs": programs.order_by("title"),
        "selected_program": selected_program,
        "selected_course": selected_course,
        "courses": Course.objects.order_by("title"),
    }
    return render(request, "course/section_list.html", context)


@login_required
def course_section_create(request):
    ensure_section_permission(request.user)
    if request.method == "POST":
        form = CourseSectionForm(request.POST, user=request.user)
        if form.is_valid():
            section = form.save()
            _generate_section_sessions(section)
            messages.success(
                request,
                f"Se creÃ³ la comisiÃ³n de '{section.course}' para el turno {section.turn}.",
            )
            return redirect("course_section_list")
        messages.error(request, "Corrige los errores indicados abajo.")
    else:
        form = CourseSectionForm(user=request.user)
    return render(
        request,
        "course/section_form.html",
        {"form": form, "title": "Nueva comisiÃ³n"},
    )


@login_required
def course_section_update(request, pk):
    section = get_object_or_404(CourseSection, pk=pk)
    ensure_section_access(request.user, section)
    if request.method == "POST":
        form = CourseSectionForm(request.POST, instance=section, user=request.user)
        if form.is_valid():
            section = form.save()
            _generate_section_sessions(section)
            messages.success(
                request,
                f"Se actualizÃ³ la comisiÃ³n de '{section.course}'.",
            )
            return redirect("course_section_list")
        messages.error(request, "Corrige los errores indicados abajo.")
    else:
        form = CourseSectionForm(instance=section, user=request.user)
    return render(
        request,
        "course/section_form.html",
        {"form": form, "title": "Editar comisiÃ³n"},
    )


@login_required
def course_section_delete(request, pk):
    section = get_object_or_404(CourseSection, pk=pk)
    ensure_section_access(request.user, section)
    if request.method == "POST":
        course_name = str(section.course)
        section.delete()
        messages.success(
            request,
            f"Se eliminÃ³ la comisiÃ³n asociada a '{course_name}'.",
        )
        return redirect("course_section_list")
    return render(
        request,
        "course/section_confirm_delete.html",
        {"section": section, "title": "Eliminar comisiÃ³n"},
    )


@login_required
def section_sessions_view(request, pk):
    section = get_object_or_404(CourseSection, pk=pk)
    ensure_section_access(request.user, section)
    sessions = (
        SectionSession.objects.filter(section=section)
        .select_related("cancelled_by")
        .order_by("-date", "-start_time")
    )
    session_form = SectionSessionForm(section=section)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_session":
            session_form = SectionSessionForm(request.POST, section=section)
            if session_form.is_valid():
                new_session = session_form.save(commit=False)
                new_session.created_by = request.user
                new_session.save()
                messages.success(request, "Se agregÃ³ la clase al calendario.")
                return redirect("section_sessions", pk=section.pk)
            messages.error(request, "Revisa los datos ingresados.")
        elif action == "disable_session":
            form = SessionDisableForm(request.POST)
            if form.is_valid():
                target_session = get_object_or_404(
                    SectionSession,
                    pk=request.POST.get("session_id"),
                    section=section,
                )
                target_session.is_cancelled = True
                target_session.cancellation_reason = form.cleaned_data["reason"]
                target_session.cancelled_by = request.user
                target_session.save()
                messages.success(request, "La clase fue deshabilitada.")
                return redirect("section_sessions", pk=section.pk)
            messages.error(request, "Indica el motivo para suspender la clase.")
        elif action == "enable_session":
            session_id = request.POST.get("session_id")
            target_session = get_object_or_404(
                SectionSession, pk=session_id, section=section
            )
            target_session.is_cancelled = False
            target_session.cancellation_reason = ""
            target_session.cancelled_by = None
            target_session.save()
            messages.success(request, "La clase volviÃ³ a estar habilitada.")
            return redirect("section_sessions", pk=section.pk)
    context = {
        "section": section,
        "sessions": sessions,
        "session_form": session_form,
        "title": "Calendario de cursada",
    }
    return render(request, "course/section_sessions.html", context)


@login_required
def session_attendance_view(request, session_id):
    session = get_object_or_404(SectionSession, pk=session_id)
    ensure_section_access(request.user, session.section)
    students = _section_students(session.section)
    records_map = {
        record.student_id: record
        for record in AttendanceRecord.objects.filter(session=session)
    }
    if request.method == "POST":
        if session.is_cancelled:
            messages.error(request, "No podÃ©s cargar asistencia en una clase suspendida.")
        else:
            new_absences = []
            for student in students:
                status = request.POST.get(f"student_{student.id}")
                comment = request.POST.get(f"comment_{student.id}", "")
                if not status:
                    continue
                previous = records_map.get(student.id)
                record, _ = AttendanceRecord.objects.update_or_create(
                    session=session,
                    student=student,
                    defaults={
                        "status": status,
                        "comment": comment,
                        "recorded_by": request.user,
                    },
                )
                records_map[student.id] = record
                if status == AttendanceRecord.Status.ABSENT and (
                    not previous or previous.status != AttendanceRecord.Status.ABSENT
                ):
                    is_reg, remaining, allowed = _regularity_status(
                        session.section, student
                    )
                    new_absences.append((record, remaining, allowed))
            session.attendance_submitted = True
            session.save(update_fields=["attendance_submitted"])
            for record, remaining, allowed in new_absences:
                notify_absence(record, remaining, allowed)
            messages.success(request, "Asistencia guardada correctamente.")
            return redirect("session_attendance", session_id=session.pk)
    student_rows = []
    for student in students:
        record = records_map.get(student.id)
        is_regular, remaining_absences, allowed_absences = _regularity_status(
            session.section, student
        )
        student_rows.append(
            {
                "student": student,
                "record": record,
                "is_regular": is_regular,
                "remaining_absences": remaining_absences,
                "allowed_absences": allowed_absences,
            }
        )
    student_rows.sort(key=lambda r: (r["is_regular"], r["student"].get_full_name()))
    pending_justifications = AttendanceJustification.objects.filter(
        attendance_record__session=session,
        status=AttendanceJustification.PENDING,
    )
    context = {
        "session": session,
        "section": session.section,
        "student_rows": student_rows,
        "status_choices": AttendanceRecord.STATUS_CHOICES,
        "pending_justifications": pending_justifications,
    }
    return render(request, "course/session_attendance.html", context)


@login_required
def section_upload_planilla(request, pk):
    section = get_object_or_404(CourseSection, pk=pk)
    ensure_section_access(request.user, section)
    upload_form = AttendanceUploadForm()
    if request.method == "POST":
        upload_form = AttendanceUploadForm(request.POST, request.FILES)
        if upload_form.is_valid():
            upload_request = upload_form.save(commit=False)
            upload_request.section = section
            upload_request.uploaded_by = request.user
            upload_request.save()
            enqueue_ai_processing(upload_request)
            messages.success(
                request,
                "Planilla enviada. El procesamiento automÃ¡tico se completarÃ¡ cuando el servicio de IA estÃ© disponible.",
            )
            return redirect("section_upload_planilla", pk=section.pk)
        messages.error(request, "No fue posible registrar el archivo. Revisa los datos.")
    uploads = section.bulk_uploads.order_by("-created_at")
    return render(
        request,
        "course/section_upload_ai.html",
        {
            "section": section,
            "upload_form": upload_form,
            "uploads": uploads,
        },
    )


@login_required
def submit_justification(request, token):
    record = get_object_or_404(AttendanceRecord, justification_token=token)
    if record.student.student != request.user:
        raise PermissionDenied
    justification, _ = AttendanceJustification.objects.get_or_create(
        attendance_record=record
    )
    if request.method == "POST":
        form = AttendanceJustificationForm(request.POST, request.FILES, instance=justification)
        if form.is_valid():
            form.save()
            messages.success(request, "JustificaciÃ³n enviada. QuedarÃ¡ pendiente de aprobaciÃ³n.")
            return redirect("home")
        messages.error(request, "Revisa los errores del formulario.")
    else:
        form = AttendanceJustificationForm(instance=justification)
    return render(
        request,
        "course/attendance_justification_form.html",
        {"form": form, "record": record},
    )


@login_required
def review_justification(request, pk):
    justification = get_object_or_404(AttendanceJustification, pk=pk)
    section = justification.attendance_record.session.section
    user = request.user
    allowed_roles = {User.Roles.BEDEL, User.Roles.ADMIN, User.Roles.MANAGEMENT}
    is_teacher = section.teachers.filter(pk=user.pk).exists()
    if not (user.role in allowed_roles or user.is_superuser or is_teacher):
        raise PermissionDenied
    if request.method == "POST":
        form = AttendanceJustificationReviewForm(request.POST, instance=justification)
        if form.is_valid():
            justification = form.save(commit=False)
            justification.reviewed_by = user
            justification.reviewed_at = timezone.now()
            justification.save()
            if justification.status == AttendanceJustification.APPROVED:
                justification.attendance_record.status = AttendanceRecord.JUSTIFIED
                justification.attendance_record.save(update_fields=["status"])
            notify_justification_result(justification)
            messages.success(request, "JustificaciÃ³n actualizada.")
            return redirect("section_sessions", pk=section.pk)
        messages.error(request, "OcurriÃ³ un error al actualizar.")
    else:
        form = AttendanceJustificationReviewForm(instance=justification)
    return render(
        request,
        "course/attendance_justification_review.html",
        {"form": form, "justification": justification},
    )


# ########################################################
# Course Allocation Views
# ########################################################


@method_decorator([login_required, lecturer_required], name="dispatch")
class CourseAllocationFormView(CreateView):
    form_class = CourseAllocationForm
    template_name = "course/course_allocation_form.html"

    def form_valid(self, form):
        lecturer = form.cleaned_data["lecturer"]
        selected_courses = form.cleaned_data["courses"]
        allocation, created = CourseAllocation.objects.get_or_create(lecturer=lecturer)
        allocation.courses.set(selected_courses)
        messages.success(
            self.request, f"Se asignaron materias a {lecturer.get_full_name} correctamente."
        )
        return redirect("course_allocation_view")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Asignar materias"
        return context


@method_decorator([login_required, lecturer_required], name="dispatch")
class CourseAllocationFilterView(FilterView):
    filterset_class = CourseAllocationFilter
    template_name = "course/course_allocation_view.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Asignaciones de materias"
        return context


@login_required
@lecturer_required
def edit_allocated_course(request, pk):
    allocation = get_object_or_404(CourseAllocation, pk=pk)
    if request.method == "POST":
        form = EditCourseAllocationForm(request.POST, instance=allocation)
        if form.is_valid():
            form.save()
            messages.success(request, "Se actualizaron las asignaciones de materias.")
            return redirect("course_allocation_view")
        messages.error(request, "Corrige los errores indicados abajo.")
    else:
        form = EditCourseAllocationForm(instance=allocation)
    return render(
        request,
        "course/course_allocation_form.html",
        {"title": "Editar asignaciones", "form": form},
    )


@login_required
@lecturer_required
def deallocate_course(request, pk):
    allocation = get_object_or_404(CourseAllocation, pk=pk)
    allocation.delete()
    messages.success(request, "Se quitaron las asignaciones correctamente.")
    return redirect("course_allocation_view")


# ########################################################
# File Upload Views
# ########################################################


@login_required
@lecturer_required
def handle_file_upload(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if request.method == "POST":
        form = UploadFormFile(request.POST, request.FILES)
        if form.is_valid():
            upload = form.save(commit=False)
            upload.course = course
            upload.save()
            messages.success(request, f"Se subiÃ³ '{upload.title}'.")
            return redirect("course_detail", slug=slug)
        messages.error(request, "Corrige los errores indicados abajo.")
    else:
        form = UploadFormFile()
    return render(
        request,
        "upload/upload_file_form.html",
        {"title": "Subir archivo", "form": form, "course": course},
    )


@login_required
@lecturer_required
def handle_file_edit(request, slug, file_id):
    course = get_object_or_404(Course, slug=slug)
    upload = get_object_or_404(Upload, pk=file_id)
    if request.method == "POST":
        form = UploadFormFile(request.POST, request.FILES, instance=upload)
        if form.is_valid():
            upload = form.save()
            messages.success(request, f"Se actualizÃ³ '{upload.title}'.")
            return redirect("course_detail", slug=slug)
        messages.error(request, "Corrige los errores indicados abajo.")
    else:
        form = UploadFormFile(instance=upload)
    return render(
        request,
        "upload/upload_file_form.html",
        {"title": "Editar archivo", "form": form, "course": course},
    )


@login_required
@lecturer_required
def handle_file_delete(request, slug, file_id):
    upload = get_object_or_404(Upload, pk=file_id)
    title = upload.title
    upload.delete()
    messages.success(request, f"Se eliminÃ³ '{title}'.")
    return redirect("course_detail", slug=slug)


# ########################################################
# Video Upload Views
# ########################################################


@login_required
@lecturer_required
def handle_video_upload(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if request.method == "POST":
        form = UploadFormVideo(request.POST, request.FILES)
        if form.is_valid():
            video = form.save(commit=False)
            video.course = course
            video.save()
            messages.success(request, f"Se subiÃ³ el video '{video.title}'.")
            return redirect("course_detail", slug=slug)
        messages.error(request, "Corrige los errores indicados abajo.")
    else:
        form = UploadFormVideo()
    return render(
        request,
        "upload/upload_video_form.html",
        {"title": "Subir video", "form": form, "course": course},
    )


@login_required
def handle_video_single(request, slug, video_slug):
    course = get_object_or_404(Course, slug=slug)
    video = get_object_or_404(UploadVideo, slug=video_slug)
    return render(
        request,
        "upload/video_single.html",
        {"video": video, "course": course},
    )


@login_required
@lecturer_required
def handle_video_edit(request, slug, video_slug):
    course = get_object_or_404(Course, slug=slug)
    video = get_object_or_404(UploadVideo, slug=video_slug)
    if request.method == "POST":
        form = UploadFormVideo(request.POST, request.FILES, instance=video)
        if form.is_valid():
            video = form.save()
            messages.success(request, f"Se actualizÃ³ el video '{video.title}'.")
            return redirect("course_detail", slug=slug)
        messages.error(request, "Corrige los errores indicados abajo.")
    else:
        form = UploadFormVideo(instance=video)
    return render(
        request,
        "upload/upload_video_form.html",
        {"title": "Editar video", "form": form, "course": course},
    )


@login_required
@lecturer_required
def handle_video_delete(request, slug, video_slug):
    video = get_object_or_404(UploadVideo, slug=video_slug)
    title = video.title
    video.delete()
    messages.success(request, f"Se eliminÃ³ el video '{title}'.")
    return redirect("course_detail", slug=slug)


# ########################################################
# Course Registration Views
# ########################################################


@login_required
@student_required
def course_registration(request):
    if request.method == "POST":
        student = Student.objects.get(student__pk=request.user.id)
        ids = ()
        data = request.POST.copy()
        data.pop("csrfmiddlewaretoken", None)  # remove csrf_token
        for key in data.keys():
            ids = ids + (str(key),)
        for s in range(0, len(ids)):
            course = Course.objects.get(pk=ids[s])
            obj = TakenCourse.objects.create(student=student, course=course)
            obj.save()
        messages.success(request, "Materias inscriptas correctamente.")
        return redirect("course_registration")
    else:
        current_semester = Semester.objects.filter(is_current_semester=True).first()
        if not current_semester:
            messages.error(request, "No se encontrÃ³ un cuatrimestre activo.")
            return render(request, "course/course_registration.html")

        # student = Student.objects.get(student__pk=request.user.id)
        student = get_object_or_404(Student, student__id=request.user.id)
        taken_courses = TakenCourse.objects.filter(student__student__id=request.user.id)
        t = ()
        for i in taken_courses:
            t += (i.course.pk,)

        courses = (
            Course.objects.filter(
                program__pk=student.program.id,
                level=student.level,
                semester=current_semester,
            )
            .exclude(id__in=t)
            .order_by("year")
        )
        all_courses = Course.objects.filter(
            level=student.level, program__pk=student.program.id
        )

        no_course_is_registered = False  # Check if no course is registered
        all_courses_are_registered = False

        registered_courses = Course.objects.filter(level=student.level).filter(id__in=t)
        if (
            registered_courses.count() == 0
        ):  # Check if number of registered courses is 0
            no_course_is_registered = True

        if registered_courses.count() == all_courses.count():
            all_courses_are_registered = True

        total_first_semester_credit = 0
        total_sec_semester_credit = 0
        total_registered_credit = 0
        for i in courses:
            if i.semester == "First":
                total_first_semester_credit += int(i.credit)
            if i.semester == "Second":
                total_sec_semester_credit += int(i.credit)
        for i in registered_courses:
            total_registered_credit += int(i.credit)
        context = {
            "is_calender_on": True,
            "all_courses_are_registered": all_courses_are_registered,
            "no_course_is_registered": no_course_is_registered,
            "current_semester": current_semester,
            "courses": courses,
            "total_first_semester_credit": total_first_semester_credit,
            "total_sec_semester_credit": total_sec_semester_credit,
            "registered_courses": registered_courses,
            "total_registered_credit": total_registered_credit,
            "student": student,
        }
        return render(request, "course/course_registration.html", context)


@login_required
@student_required
def course_drop(request):
    if request.method == "POST":
        student = get_object_or_404(Student, student__pk=request.user.id)
        course_ids = request.POST.getlist("course_ids")
        print("course_ids", course_ids)
        for course_id in course_ids:
            course = get_object_or_404(Course, pk=course_id)
            TakenCourse.objects.filter(student=student, course=course).delete()
        messages.success(request, "Se dio de baja a las materias seleccionadas.")
        return redirect("course_registration")


# ########################################################
# User Course List View
# ########################################################


@login_required
def user_course_list(request):
    if request.user.is_lecturer:
        sections = (
            CourseSection.objects.filter(teachers=request.user)
            .select_related("course", "semester", "turn", "room")
            .order_by("course__title")
        )
        return render(
            request,
            "course/user_course_list.html",
            {"sections": sections, "title": "Mis comisiones"},
        )

    if request.user.is_student:
        student = get_object_or_404(Student, student__pk=request.user.id)
        taken_courses = TakenCourse.objects.filter(student=student)
        return render(
            request,
            "course/user_course_list.html",
            {"student": student, "taken_courses": taken_courses},
        )

    # For other users
    return render(request, "course/user_course_list.html")


@login_required
def section_enrollment(request, pk):
    section = get_object_or_404(CourseSection, pk=pk)
    ensure_section_access(request.user, section)
    if request.method == "POST":
        form = SectionEnrollmentForm(request.POST, section=section)
        if form.is_valid():
            students = form.cleaned_data.get("students") or []
            section.students.set(students)
            messages.success(request, "Alumnos actualizados para la comisión.")
            return redirect("section_enrollment", pk=section.pk)
        messages.error(request, "Revisa los errores del formulario.")
    else:
        form = SectionEnrollmentForm(section=section)
    return render(
        request,
        "course/section_enrollment.html",
        {
            "form": form,
            "section": section,
            "title": "Asignar alumnos",
        },
    )


