from datetime import timedelta

from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone

from accounts.models import User
from core.models import AttendanceReminderLog, SectionSession


class Command(BaseCommand):
    help = "Envía recordatorios de asistencia a docentes y notifica a Bedelía"

    def handle(self, *args, **options):
        threshold_date = timezone.now() - timedelta(days=1)
        sessions = SectionSession.objects.filter(
            attendance_submitted=False,
            is_cancelled=False,
            date__lte=threshold_date,
        ).select_related("section")
        if not sessions.exists():
            self.stdout.write("No hubo sesiones pendientes de asistencia.")
            return
        for session in sessions:
            for teacher in session.section.teachers.all():
                missing_count = SectionSession.objects.filter(
                    section__teachers=teacher,
                    attendance_submitted=False,
                    date__lte=session.date,
                ).count()
                if missing_count >= 2 and not AttendanceReminderLog.objects.filter(
                    teacher=teacher, session=session
                ).exists():
                    self._notify_teacher(teacher, session, missing_count)
                    AttendanceReminderLog.objects.create(
                        teacher=teacher, session=session
                    )
                    self._notify_bedelia(teacher, session, missing_count)

    def _notify_teacher(self, teacher, session, missing_count):
        send_mail(
            "Recordatorio de asistencia",
            f"Registrá la asistencia de tus últimas clases. Hay {missing_count} sesiones sin cargar.",
            None,
            [teacher.email],
            fail_silently=True,
        )

    def _notify_bedelia(self, teacher, session, missing_count):
        recipients = User.objects.filter(role=User.Roles.BEDEL).values_list(
            "email", flat=True
        )
        if recipients:
            send_mail(
                "Docente con asistencia pendiente",
                f"{teacher.get_full_name()} tiene {missing_count} clases sin asistencia cargada para la comisión {session.section}.",
                None,
                list(filter(None, recipients)),
                fail_silently=True,
            )
