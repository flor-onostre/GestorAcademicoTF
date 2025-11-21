from django.contrib import admin
from modeltranslation.admin import TranslationAdmin
from .models import (
    AttendanceJustification,
    AttendanceRecord,
    AttendanceReminderLog,
    BulkUploadRequest,
    BuildingFloor,
    NewsAndEvents,
    Room,
    SectionSession,
    Semester,
    Session,
)


class NewsAndEventsAdmin(TranslationAdmin):
    pass


admin.site.register(Semester)
admin.site.register(Session)
admin.site.register(NewsAndEvents, NewsAndEventsAdmin)
admin.site.register(BuildingFloor)
admin.site.register(Room)
admin.site.register(SectionSession)
admin.site.register(AttendanceRecord)
admin.site.register(BulkUploadRequest)
admin.site.register(AttendanceJustification)
admin.site.register(AttendanceReminderLog)
