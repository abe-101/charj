import logging

from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _

from .emails import send_feedback_email
from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import User

logger = logging.getLogger(__name__)

if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    # Force the `admin` sign in process to go through the `django-allauth` workflow:
    # https://docs.allauth.org/en/latest/common/admin.html#admin
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("name",)}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    list_display = [
        "email",
        "name",
        "is_superuser",
        "date_joined",
        "last_login",
    ]
    search_fields = ["name", "email"]
    actions = ["send_feedback_email_action"]

    ordering = ["-last_login"]
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )

    @admin.action(description="Send welcome / feedback email", permissions=["change"])
    def send_feedback_email_action(self, request, queryset):
        """Send immediately: no confirmation step, so report who was mailed."""
        sent, failed = [], []
        for user in queryset:
            try:
                send_feedback_email(user)
            except Exception:
                logger.exception("Feedback email failed for %s", user.pk)
                failed.append(user.email)
            else:
                sent.append(user.email)

        if sent:
            self.message_user(request, f"Sent to: {', '.join(sent)}", messages.SUCCESS)
        if failed:
            self.message_user(request, f"FAILED: {', '.join(failed)}", messages.ERROR)
