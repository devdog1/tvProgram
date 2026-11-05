from django.urls import path
from . import views

urlpatterns = [
    # Dashboard (NetBox-style Overview)
    path("", views.dashboard_view, name="dashboard"),

    # Programs CRUD & details
    path("programs/", views.program_list, name="program_list"),
    path("programs/new/", views.program_create, name="program_create"),
    path("programs/import/", views.program_bulk_import, name="program_bulk_import"),
    path("programs/<int:pk>/", views.program_detail, name="program_detail"),
    path("programs/<int:pk>/edit/", views.program_edit, name="program_edit"),
    path("programs/<int:pk>/delete/", views.program_delete, name="program_delete"),
    path("programs/<int:pk>/signoff/", views.program_signoff, name="program_signoff"),
    path("programs/<int:pk>/attach/", views.program_attach_file, name="program_attach_file"),
    path("attachments/<int:attachment_id>/delete/", views.program_delete_attachment, name="program_delete_attachment"),

    # TV Series & Episodic
    path("series/", views.series_list, name="series_list"),
    path("series/new/", views.series_create, name="series_create"),
    path("series/<int:pk>/", views.series_detail, name="series_detail"),
    path("series/<int:pk>/edit/", views.series_edit, name="series_edit"),
    path("series/<int:pk>/delete/", views.series_delete, name="series_delete"),
    path("series/<int:pk>/signoff/", views.series_signoff, name="series_signoff"),

    # Custom Fields (Admins / Editors)
    path("custom-fields/", views.custom_fields_list, name="custom_fields_list"),
    path("custom-fields/new/", views.custom_field_create, name="custom_field_create"),
    path("custom-fields/<int:pk>/edit/", views.custom_field_edit, name="custom_field_edit"),
    path("custom-fields/<int:pk>/delete/", views.custom_field_delete, name="custom_field_delete"),

    # Review Queue & Change Log
    path("signoff-queue/", views.signoff_queue, name="signoff_queue"),
    path("changelog/", views.changelog_list, name="changelog_list"),

    # Event Hook Manager
    path("event-hooks/", views.event_hooks_list, name="event_hooks_list"),
    path("event-hooks/new/", views.event_hook_create, name="event_hook_create"),
    path("event-hooks/<int:pk>/edit/", views.event_hook_edit, name="event_hook_edit"),
    path("event-hooks/<int:pk>/toggle/", views.event_hook_toggle, name="event_hook_toggle"),
    path("event-hooks/<int:pk>/delete/", views.event_hook_delete, name="event_hook_delete"),

    # Metadata System Options
    path("options/", views.manage_options, name="manage_options"),
    path("options/", views.manage_options, name="options_dashboard"),
    path("options/<str:model_name>/new/", views.option_create, name="option_create"),
    path("options/<str:model_name>/<int:pk>/edit/", views.option_edit, name="option_edit"),
    path("options/<str:model_name>/<int:pk>/toggle/", views.option_toggle, name="option_toggle"),

    # SMTP Settings Admin View
    path("settings/smtp/", views.smtp_settings_view, name="smtp_settings"),
]
