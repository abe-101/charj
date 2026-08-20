import pytest
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from charj.users.emails import render_feedback_body
from charj.users.emails import send_feedback_email
from charj.users.models import User

pytestmark = pytest.mark.django_db


class TestRenderFeedbackBody:
    def test_greets_user_by_name(self, user: User):
        user.name = "Dana Scully"
        assert render_feedback_body(user).startswith("Hi Dana Scully,")

    def test_blank_name_falls_back_to_there(self, user: User):
        user.name = ""
        assert render_feedback_body(user).startswith("Hi there,")

    def test_name_is_not_html_escaped(self, user: User):
        """The body is plain text, so an apostrophe must survive verbatim."""
        user.name = "Seamus O'Brien"
        assert "Seamus O'Brien" in render_feedback_body(user)

    def test_asks_where_they_heard_not_how_they_found(self, user: User):
        """ "How did you find it" reads to many people as "what did you think"."""
        body = render_feedback_body(user)
        assert "where did you hear about Charj?" in body
        assert "how did you find" not in body.lower()

    def test_contains_no_em_dash(self, user: User):
        assert "\u2014" not in render_feedback_body(user)

    def test_does_not_disclose_user_counts(self, user: User):
        """Calling someone an early user tells them how few users there are."""
        lowered = render_feedback_body(user).lower()
        assert "first" not in lowered
        assert "one of the" not in lowered


class TestSendFeedbackEmail:
    def test_sends_to_the_user(self, user: User, mailoutbox):
        send_feedback_email(user)
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == [user.email]

    def test_replies_reach_a_person(self, user: User, mailoutbox):
        """The body promises a reply reaches a person, so From must not bounce.

        No Reply-To is set: absent one, replies go to From, which is already a
        real inbox.
        """
        send_feedback_email(user)
        assert mailoutbox[0].from_email == settings.FEEDBACK_FROM_EMAIL
        assert "noreply" not in mailoutbox[0].from_email
        assert mailoutbox[0].reply_to == []

    def test_is_plain_text_only(self, user: User, mailoutbox):
        """No HTML part at all: a designed email stops reading as a personal note."""
        send_feedback_email(user)
        assert not isinstance(mailoutbox[0], EmailMultiAlternatives)
        assert not mailoutbox[0].message().is_multipart()
