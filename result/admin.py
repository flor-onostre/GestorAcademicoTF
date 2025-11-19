from django.contrib import admin
from django.contrib.auth.models import Group

from .models import TakenCourse, Result


class ScoreAdmin(admin.ModelAdmin):
    # Columnas con encabezados traducidos
    list_display = [
        "col_student",
        "col_course",
        "col_assignment",
        "col_mid_exam",
        "col_quiz",
        "col_attendance",
        "col_final_exam",
        "col_total",
        "col_grade",
        "col_comment",
    ]

    # Métodos “proxy” para no tocar los modelos y traducir headers
    def col_student(self, obj):
        return obj.student
    col_student.short_description = "Estudiante"
    col_student.admin_order_field = "student"

    def col_course(self, obj):
        return obj.course
    col_course.short_description = "Materia"
    col_course.admin_order_field = "course"

    def col_assignment(self, obj):
        return obj.assignment
    col_assignment.short_description = "Trabajo"
    col_assignment.admin_order_field = "assignment"

    def col_mid_exam(self, obj):
        return obj.mid_exam
    col_mid_exam.short_description = "Parcial"
    col_mid_exam.admin_order_field = "mid_exam"

    def col_quiz(self, obj):
        return obj.quiz
    col_quiz.short_description = "Quiz"
    col_quiz.admin_order_field = "quiz"

    def col_attendance(self, obj):
        return obj.attendance
    col_attendance.short_description = "Asistencia"
    col_attendance.admin_order_field = "attendance"

    def col_final_exam(self, obj):
        return obj.final_exam
    col_final_exam.short_description = "Final"
    col_final_exam.admin_order_field = "final_exam"

    def col_total(self, obj):
        return obj.total
    col_total.short_description = "Total"
    col_total.admin_order_field = "total"

    def col_grade(self, obj):
        return obj.grade
    col_grade.short_description = "Calificación"
    col_grade.admin_order_field = "grade"

    def col_comment(self, obj):
        return obj.comment
    col_comment.short_description = "Comentario"
    col_comment.admin_order_field = "comment"


admin.site.register(TakenCourse, ScoreAdmin)
admin.site.register(Result)
