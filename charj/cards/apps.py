import contextlib

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CardsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "charj.cards"
    verbose_name = _("Cards")

    def ready(self):
        with contextlib.suppress(ImportError):
            import charj.cards.signals  # noqa: F401, PLC0415
