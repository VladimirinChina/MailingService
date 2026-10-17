from django.apps import AppConfig


class MailingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mailings"
    verbose_name = "Рассылки"

    def ready(self) -> None:
        from . import signals  # noqa: F401
