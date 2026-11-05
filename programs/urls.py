from django.urls import path
from . import views

urlpatterns = [
    path("", views.program_list, name="program_list"),
    path("programs/new/", views.program_create, name="program_create"),
    path("programs/<int:pk>/edit/", views.program_edit, name="program_edit"),
    path("programs/<int:pk>/delete/", views.program_delete, name="program_delete"),

    # Option management
    path("options/", views.options_dashboard, name="options_dashboard"),
    path("options/<str:opt_type>/new/", views.option_create, name="option_create"),
    path("options/<str:opt_type>/<int:pk>/edit/", views.option_edit, name="option_edit"),
    path("options/<str:opt_type>/<int:pk>/toggle/", views.option_toggle, name="option_toggle"),
]
