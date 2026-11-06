from django.apps import AppConfig


class ProgramsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "programs"

    def ready(self):
        import programs.schema_extensions  # noqa: F401
