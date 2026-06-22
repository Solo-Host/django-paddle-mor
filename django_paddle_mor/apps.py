from django.apps import AppConfig
from django.test.signals import setting_changed

from .settings import clear_django_paddle_mor_settings_cache


def _handle_setting_changed(*, setting: str, **kwargs):
    if setting == "DJANGO_PADDLE_MOR":
        clear_django_paddle_mor_settings_cache()


class DjangoPaddleMorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_paddle_mor"
    verbose_name = "Django Paddle MoR"

    def ready(self):
        setting_changed.connect(
            _handle_setting_changed,
            dispatch_uid="django_paddle_mor.handle_setting_changed",
        )
