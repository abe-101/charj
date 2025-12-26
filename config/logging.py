"""Custom logging components for structured logging with request context."""

import logging
import uuid
from contextvars import ContextVar
from typing import Any

from django.http import HttpRequest

# Context variables for storing request-scoped data
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)
user_id_var: ContextVar[int | None] = ContextVar("user_id", default=None)
user_email_var: ContextVar[str | None] = ContextVar("user_email", default=None)
request_path_var: ContextVar[str | None] = ContextVar("request_path", default=None)
request_method_var: ContextVar[str | None] = ContextVar("request_method", default=None)
ip_address_var: ContextVar[str | None] = ContextVar("ip_address", default=None)


class RequestContextFilter(logging.Filter):
    """
    Logging filter that adds request context from contextvars to LogRecord.

    This filter reads values from contextvars set by RequestContextMiddleware
    and adds them as extra fields to each log record. These fields are then
    automatically included in structured log output (JSON in production, Rich in dev).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Add context variables to the log record."""
        # Only add fields if they don't already exist (don't override explicit values)
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        if not hasattr(record, "session_id"):
            record.session_id = session_id_var.get()
        if not hasattr(record, "user_id"):
            record.user_id = user_id_var.get()
        if not hasattr(record, "user_email"):
            record.user_email = user_email_var.get()
        if not hasattr(record, "path"):
            record.path = request_path_var.get()
        if not hasattr(record, "method"):
            record.method = request_method_var.get()
        if not hasattr(record, "ip_address"):
            record.ip_address = ip_address_var.get()

        return True


class RequestContextMiddleware:
    """
    Middleware that extracts request context and stores it in contextvars.

    This middleware runs early in the request/response cycle and populates
    contextvars with user information, request metadata, and a unique request ID.
    These values are then picked up by RequestContextFilter and added to all logs.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> Any:
        # Generate unique request ID
        req_id = str(uuid.uuid4())
        request_id_var.set(req_id)

        # Get session ID (persists across requests for the same user)
        # Only log first 8 chars for security - enough to trace sessions
        # without exposing full key
        session_key = request.session.session_key
        if not session_key:
            # Create session if it doesn't exist
            request.session.create()
            session_key = request.session.session_key
        session_id_var.set(session_key[:8] if session_key else None)

        # Extract request metadata
        request_path_var.set(request.path)
        request_method_var.set(request.method)

        # Get IP address (handle proxy headers)
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR")
        ip_address_var.set(ip)

        # Extract user information if authenticated
        if hasattr(request, "user") and request.user.is_authenticated:
            user_id_var.set(request.user.id)
            user_email_var.set(request.user.email)
        else:
            user_id_var.set(None)
            user_email_var.set(None)

        response = self.get_response(request)

        # Clean up context vars after response (important for thread reuse)
        request_id_var.set(None)
        session_id_var.set(None)
        user_id_var.set(None)
        user_email_var.set(None)
        request_path_var.set(None)
        request_method_var.set(None)
        ip_address_var.set(None)

        return response
