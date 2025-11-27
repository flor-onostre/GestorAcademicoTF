from django.conf import settings
from django.template.loader import render_to_string, TemplateDoesNotExist
from django.utils.html import strip_tags

from core.utils import send_html_email


def _send(template, context, subject, recipients):
    """
    Helper to send an HTML email using existing send_html_email.
    Si la plantilla no existe, envía un texto simple para no fallar.
    """
    try:
        send_html_email(subject, recipients, template, context)
    except TemplateDoesNotExist:
        from django.core.mail import send_mail

        body = "\n".join(f"{k}: {v}" for k, v in context.items())
        send_mail(
            subject,
            body,
            getattr(settings, "EMAIL_FROM_ADDRESS", None),
            recipients,
            fail_silently=True,
        )


def notify_absence(student, section, remaining_absences, allowed_absences):
    context = {
        "student": student,
        "section": section,
        "remaining_absences": remaining_absences,
        "allowed_absences": allowed_absences,
        "site_name": getattr(settings, "SITE_NAME", "Campus"),
    }
    _send(
        "emails/absence_notice.html",
        context,
        f"[{section.course.title}] Ausencia registrada",
        [student.email],
    )


def notify_teacher_missing_attendance(teacher, section, pending_sessions):
    context = {
        "teacher": teacher,
        "section": section,
        "pending_sessions": pending_sessions,
        "site_name": getattr(settings, "SITE_NAME", "Campus"),
    }
    _send(
        "emails/attendance_reminder.html",
        context,
        f"[{section.course.title}] Recordatorio de asistencia",
        [teacher.email],
    )


def notify_bedelia_teacher_missing(teacher, section):
    context = {"teacher": teacher, "section": section}
    _send(
        "emails/bedelia_missing_attendance.html",
        context,
        "Docente con asistencia pendiente",
        [addr for addr in getattr(settings, "BEDELIA_EMAILS", [])],
    )


def notify_justification_result(justification):
    student = justification.student
    record = justification.attendance_record
    context = {
        "student": student,
        "justification": justification,
        "section": record.session.section if record and record.session else None,
    }
    _send(
        "emails/justification_result.html",
        context,
        "Resultado de tu justificativo",
        [student.email],
    )


def notify_room_change(section, old_room, new_room):
    recipients = list(section.students.values_list("email", flat=True)) + list(
        section.teachers.values_list("email", flat=True)
    )
    context = {"section": section, "old_room": old_room, "new_room": new_room}
    _send(
        "emails/room_change.html",
        context,
        f"Cambio de aula para {section.course.title}",
        recipients,
    )
