import contextlib
import os

from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class CardsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "charj.cards"
    verbose_name = _("Cards")

    def ready(self):
        with contextlib.suppress(ImportError):
            import charj.cards.signals  # noqa: F401, PLC0415

        if os.environ.get("DJANGO_SETTINGS_MODULE") == "config.settings.production":
            import posthog  # noqa: PLC0415

            posthog.api_key = settings.POSTHOG_API_KEY
            posthog.host = "https://us.i.posthog.com"
