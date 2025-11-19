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

# Para GPA/CGPA: usamos la propia nota numérica como "point" base (0–10)
GRADE_POINT_MAPPING = {str(n): float(n) for n in range(0, 11)}
# Compatibilidad si aparece algún valor residual
GRADE_POINT_MAPPING.update({"NG": 0.0})


class TakenCourse(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="taken_courses"
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


class Result(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    gpa = models.FloatField(null=True)
    cgpa = models.FloatField(null=True)
    semester = models.CharField(max_length=100, choices=settings.SEMESTER_CHOICES)
    session = models.CharField(max_length=100, blank=True, null=True)
    level = models.CharField(max_length=25, choices=settings.LEVEL_CHOICES, null=True)

    def __str__(self):
        return f"Resultado de {self.student} - Cuatrimestre: {self.semester}, Nivel: {self.level}"