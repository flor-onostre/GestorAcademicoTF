from django.contrib import admin
from django.contrib.auth.models import Group
from modeltranslation.admin import TranslationAdmin

from .models import (
    Course,
    CourseAllocation,
    CourseSection,
    ExamAttempt,
    ExamSchedule,
    Program,
    Turn,
    Upload,
    University,
)


class UniversityAdmin(admin.ModelAdmin):
    list_display = ("name", "short_name", "is_active")
    search_fields = ("name", "short_name")
    list_filter = ("is_active",)


class ProgramAdmin(TranslationAdmin):
    list_display = ("title", "university", "program_type", "allows_promotion")
    list_filter = ("program_type", "allows_promotion", "university")
    search_fields = ("title",)


class CourseAdmin(TranslationAdmin):
    pass


class UploadAdmin(TranslationAdmin):
    pass


admin.site.register(University, UniversityAdmin)
admin.site.register(Program, ProgramAdmin)
admin.site.register(Course, CourseAdmin)
admin.site.register(CourseAllocation)


@admin.register(Turn)
class TurnAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(CourseSection)
class CourseSectionAdmin(admin.ModelAdmin):
    list_display = ("course", "program", "semester", "turn", "start_date", "end_date", "is_active")
    list_filter = ("program", "semester", "turn", "is_active")
    search_fields = ("course__title",)
    filter_horizontal = ("teachers",)


@admin.register(ExamSchedule)
class ExamScheduleAdmin(admin.ModelAdmin):
    list_display = ("course", "exam_type", "date", "start_time", "room", "is_free_exam")
    list_filter = ("exam_type", "date", "room")
    search_fields = ("course__title",)
    filter_horizontal = ("teachers",)


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ("schedule", "student", "score", "passed", "created_at")
    list_filter = ("schedule__exam_type", "passed")
    search_fields = ("student__student__first_name", "student__student__last_name")


admin.site.register(Upload, UploadAdmin)
