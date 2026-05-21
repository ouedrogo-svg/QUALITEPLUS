from django.apps import AppConfig


class CoursesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "courses"
    verbose_name = "Cours"

    def ready(self):
        from .sqlite import register_sqlite_pragmas

        register_sqlite_pragmas()
