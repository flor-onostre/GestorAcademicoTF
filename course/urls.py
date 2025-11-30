from django.urls import path
from . import views


urlpatterns = [
    # Program urls
    path("universidades/", views.university_list, name="university_list"),
    path("universidades/agregar/", views.university_add, name="university_add"),
    path("universidades/<int:pk>/editar/", views.university_edit, name="university_edit"),
    path("universidades/<int:pk>/eliminar/", views.university_delete, name="university_delete"),
    path("", views.ProgramFilterView.as_view(), name="programs"),
    path("<int:pk>/detail/", views.program_detail, name="program_detail"),
    path("add/", views.program_add, name="add_program"),
    path("<int:pk>/edit/", views.program_edit, name="edit_program"),
    path("<int:pk>/delete/", views.program_delete, name="program_delete"),
    # Course urls
    path("course/<slug>/detail/", views.course_single, name="course_detail"),
    path("<int:pk>/course/add/", views.course_add, name="course_add"),
    path("course/<slug>/edit/", views.course_edit, name="edit_course"),
    path("course/delete/<slug>/", views.course_delete, name="delete_course"),
    # Course sections
    path("sections/", views.course_section_list, name="course_section_list"),
    path("sections/add/", views.course_section_create, name="course_section_create"),
    path("sections/<int:pk>/edit/", views.course_section_update, name="course_section_update"),
    path("sections/<int:pk>/delete/", views.course_section_delete, name="course_section_delete"),
    path("sections/<int:pk>/assign_room/", views.course_section_assign_room, name="course_section_assign_room"),
    path("sections/<int:pk>/sessions/", views.section_sessions_view, name="section_sessions"),
    path("sections/<int:pk>/students/", views.section_enrollment, name="section_enrollment"),
    path("sessions/<int:session_id>/attendance/", views.session_attendance_view, name="session_attendance"),
    path("sections/<int:pk>/uploads/", views.section_upload_planilla, name="section_upload_planilla"),
    path("materias/", views.CourseFilterView.as_view(), name="course_list"),
    path("attendance/justify/<uuid:token>/", views.submit_justification, name="submit_justification"),
    path("attendance/justification/<int:pk>/review/", views.review_justification, name="review_justification"),
    # File uploads urls
    path(
        "course/<slug>/documentations/upload/",
        views.handle_file_upload,
        name="upload_file_view",
    ),
    path(
        "course/<slug>/documentations/<int:file_id>/edit/",
        views.handle_file_edit,
        name="upload_file_edit",
    ),
    path(
        "course/<slug>/documentations/<int:file_id>/delete/",
        views.handle_file_delete,
        name="upload_file_delete",
    ),
    # Video uploads urls
    path(
        "course/<slug>/video_tutorials/upload/",
        views.handle_video_upload,
        name="upload_video",
    ),
    path(
        "course/<slug>/video_tutorials/<video_slug>/detail/",
        views.handle_video_single,
        name="video_single",
    ),
    path(
        "course/<slug>/video_tutorials/<video_slug>/edit/",
        views.handle_video_edit,
        name="upload_video_edit",
    ),
    path(
        "course/<slug>/video_tutorials/<video_slug>/delete/",
        views.handle_video_delete,
        name="upload_video_delete",
    ),
    # course registration
    path("course/registration/", views.course_registration, name="course_registration"),
    path("course/drop/", views.course_drop, name="course_drop"),
    path("my_courses/", views.user_course_list, name="user_course_list"),
]
