from decimal import Decimal
from django.conf import settings

from django.db import models
from django.urls import reverse

from accounts.models import Student
from core.models import Semester
from course.models import Course

# -----------------------------
# Escala de calificaciones 0–10
# -----------------------------
# Guardamos la nota como string para compatibilidad con CharField(max_length=2).
GRADE_CHOICES = tuple((str(n), str(n)) for n in range(10, -1, -1))  # "10","9",...,"0"

# Comentarios / estado de cursada (valores internos estables; etiquetas en español)
PASS = "PASS"          # Aprobado (>= 4)
FAIL = "FAIL"          # Reprobado (< 4)
PROMOTED = "PROMOTED"  # Promocionado (>= 6)

COMMENT_CHOICES = (
    (PROMOTED, "Promocionado"),
    (PASS, "Aprobado"),
    (FAIL, "Reprobado"),
)

COURSE_COMPLETION_PROMOTED = "PROMOTED"
COURSE_COMPLETION_FINAL = "FINAL"
COURSE_COMPLETION_RETAKE = "RETAKE"

COURSE_COMPLETION_CHOICES = (
    (COURSE_COMPLETION_PROMOTED, "Promocionado"),
    (COURSE_COMPLETION_FINAL, "Debe rendir final"),
    (COURSE_COMPLETION_RETAKE, "Debe recursar"),
)

# Para GPA/CGPA: usamos la propia nota numérica como "point" base (0–10)
GRADE_POINT_MAPPING = {str(n): float(n) for n in range(0, 11)}
# Compatibilidad si aparece algún valor residual
GRADE_POINT_MAPPING.update({"NG": 0.0})


class TakenCourse(models.Model):
    COMPLETION_PROMOTED = COURSE_COMPLETION_PROMOTED
    COMPLETION_FINAL = COURSE_COMPLETION_FINAL
    COMPLETION_RETAKE = COURSE_COMPLETION_RETAKE

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="taken_courses"
    )
    section = models.ForeignKey(
        "course.CourseSection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="taken_courses",
    )
    assignment = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    mid_exam = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    quiz = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    attendance = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    final_exam = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    first_partial = models.DecimalField(
        max_digits=4, decimal_places=1, default=Decimal("0.0")
    )
    second_partial = models.DecimalField(
        max_digits=4, decimal_places=1, default=Decimal("0.0")
    )
    total = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"), editable=False
    )
    grade = models.CharField(
        choices=GRADE_CHOICES, max_length=2, blank=True, editable=False
    )
    point = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"), editable=False
    )
    comment = models.CharField(
        choices=COMMENT_CHOICES, max_length=200, blank=True, editable=False
    )
    completion_status = models.CharField(
        choices=COURSE_COMPLETION_CHOICES,
        max_length=20,
        blank=True,
        editable=False,
    )

    def get_absolute_url(self):
        return reverse("course_detail", kwargs={"slug": self.course.slug})

    def __str__(self):
        return f"{self.course.title} ({self.course.code})"

    # -----------------------------
    # Cálculos
    # -----------------------------
    def get_total(self):
        # Suma todas las componentes
        return sum(
            [
                Decimal(self.assignment),
                Decimal(self.mid_exam),
                Decimal(self.quiz),
                Decimal(self.attendance),
                Decimal(self.final_exam),
            ]
        )

    def _total_to_10(self, total: Decimal) -> Decimal:
        """
        Normaliza el total a escala 0–10 sin asumir un esquema fijo:
        - Si el total ya está en 0–10, lo deja como está.
        - Si es >10 (por ej. escala 0–100), lo divide por 10.
        """
        if total is None:
            return Decimal("0")
        if total <= 10:
            return total
        return total / Decimal("10")

    def get_grade(self):
        total = self.get_total()
        grade_0_10 = self._total_to_10(total)
        # Redondeo al entero más cercano y límite entre 0 y 10
        grade_int = max(0, min(10, int(round(grade_0_10))))
        return str(grade_int)

    def get_comment(self):
        # Promociona con 6+, aprueba con 4–5, reprueba con <4
        try:
            g = int(self.grade) if self.grade not in (None, "", "NG") else 0
        except ValueError:
            g = 0
        if g >= 6:
            return PROMOTED
        if g >= 4:
            return PASS
        return FAIL

    def get_point(self):
        # Puntos = créditos * nota (0–10)
        credit = self.course.credit
        try:
            grade_num = Decimal(self.grade)
        except Exception:
            grade_num = Decimal("0")
        return Decimal(credit) * grade_num

    def save(self, *args, **kwargs):
        self.total = self.get_total()
        self.grade = self.get_grade()
        self.point = self.get_point()
        self.comment = self.get_comment()
        self.completion_status = self.determine_completion_status()
        super().save(*args, **kwargs)

    # GPA/cGPA: promedios ponderados por créditos, sobre 10
    def calculate_gpa(self):
        current_semester = Semester.objects.filter(is_current_semester=True).first()
        if not current_semester:
            return Decimal("0.00")

        taken_courses = TakenCourse.objects.filter(
            student=self.student,
            course__level=self.student.level,
            course__semester=current_semester.semester,
        )

        total_points = sum(tc.point for tc in taken_courses)
        total_credits = sum(tc.course.credit for tc in taken_courses)

        if total_credits > 0:
            gpa = total_points / Decimal(total_credits)
            return round(gpa, 2)
        return Decimal("0.00")

    def calculate_cgpa(self):
        taken_courses = TakenCourse.objects.filter(student=self.student)

        total_points = sum(tc.point for tc in taken_courses)
        total_credits = sum(tc.course.credit for tc in taken_courses)

        if total_credits > 0:
            cgpa = total_points / Decimal(total_credits)
            return round(cgpa, 2)
        return Decimal("0.00")

    def _attendance_thresholds(self):
        section = self.section
        program = self.course.program if self.course else None
        pass_att = Decimal("0")
        promo_att = Decimal("0")
        if section:
            pass_att = Decimal(section.attendance_required or 0)
            promo_att = Decimal(section.promotion_attendance_required or pass_att)
        elif program:
            pass_att = Decimal(program.min_passing_attendance or 0)
            promo_att = Decimal(program.min_promotion_attendance or pass_att)
        return pass_att, promo_att

    def _partial_status(self, score, pass_score, promotion_score):
        try:
            value = Decimal(score)
        except Exception:
            value = Decimal("0")
        if value >= promotion_score:
            return "PROMOTED"
        if value >= pass_score:
            return "APPROVED"
        return "FAILED"

    def determine_completion_status(self):
        course = self.course
        if not course or not course.program:
            return COURSE_COMPLETION_FINAL
        pass_score = Decimal(course.program.pass_score)
        promotion_score = Decimal(course.program.promotion_score)
        attendance_value = Decimal(self.attendance or 0)
        pass_att, promo_att = self._attendance_thresholds()
        if attendance_value < pass_att:
            return COURSE_COMPLETION_RETAKE
        if course.evaluation_mode == Course.EvaluationModes.FINAL:
            return COURSE_COMPLETION_FINAL
        first_status = self._partial_status(
            self.first_partial, pass_score, promotion_score
        )
        second_status = self._partial_status(
            self.second_partial, pass_score, promotion_score
        )
        if (
            first_status == "PROMOTED"
            and second_status == "PROMOTED"
            and attendance_value >= promo_att
        ):
            return COURSE_COMPLETION_PROMOTED
        if first_status in {"PROMOTED", "APPROVED"} and second_status in {
            "PROMOTED",
            "APPROVED",
        }:
            return COURSE_COMPLETION_FINAL
        return COURSE_COMPLETION_RETAKE


class Result(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    gpa = models.FloatField(null=True)
    cgpa = models.FloatField(null=True)
    semester = models.CharField(max_length=100, choices=settings.SEMESTER_CHOICES)
    session = models.CharField(max_length=100, blank=True, null=True)
    level = models.CharField(max_length=25, choices=settings.LEVEL_CHOICES, null=True)

    def __str__(self):
        return f"Resultado de {self.student} - Cuatrimestre: {self.semester}, Nivel: {self.level}"
