"""Custom middleware for the Charj project."""

from django.conf import settings
from django.contrib.auth.middleware import LoginRequiredMiddleware


class CustomLoginRequiredMiddleware(LoginRequiredMiddleware):
    """
    Custom LoginRequiredMiddleware that allows exempting specific URL paths.

    This middleware extends Django's LoginRequiredMiddleware to support
    exempting certain URLs from authentication requirements using the
    OPEN_URLS setting.

    OPEN_URLS supports two patterns:
    - Exact match: "/health/" - must match exactly
    - Prefix match: "/api/v1/auth/*" - matches anything starting with /api/v1/auth/
    """

    def __init__(self, get_response=None):
        self.get_response = get_response
        super().__init__(get_response)

    def process_view(self, request, view_func, view_args, view_kwargs):
        """Process the view and check if the URL should be exempted from auth."""
        for pattern in settings.OPEN_URLS:
            if pattern.endswith("*"):
                # Prefix match - remove the * and check startswith
                prefix = pattern[:-1]
                if request.path.startswith(prefix):
                    return None  # Skip auth
            # Exact match
            elif request.path == pattern:
                return None  # Skip auth
        return super().process_view(request, view_func, view_args, view_kwargs)
