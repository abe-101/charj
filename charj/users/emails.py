"""Outbound application email for the users app."""

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string

from .models import User

SUBJECT = "where'd you hear about Charj?"
BODY_TEMPLATE = "emails/feedback_request.txt"


def render_feedback_body(user: User) -> str:
    """Return the plain-text body of the feedback email to ``user``."""
    return render_to_string(BODY_TEMPLATE, {"user": user})


def send_feedback_email(user: User) -> None:
    """Send to one user only: a shared to/cc list would leak addresses."""
    EmailMessage(
        subject=SUBJECT,
        body=render_feedback_body(user),
        from_email=settings.FEEDBACK_FROM_EMAIL,
        to=[user.email],
    ).send()
