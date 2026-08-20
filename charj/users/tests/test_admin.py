import contextlib
from http import HTTPStatus
from importlib import reload
from typing import cast

import pytest
from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from charj.users.models import User
from charj.users.tests.factories import UserFactory


class TestUserAdmin:
    def test_changelist(self, admin_client):
        url = reverse("admin:users_user_changelist")
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

    def test_search(self, admin_client):
        url = reverse("admin:users_user_changelist")
        response = admin_client.get(url, data={"q": "test"})
        assert response.status_code == HTTPStatus.OK

    def test_add(self, admin_client):
        url = reverse("admin:users_user_add")
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

        response = admin_client.post(
            url,
            data={
                "email": "new-admin@example.com",
                "password1": "My_R@ndom-P@ssw0rd",
                "password2": "My_R@ndom-P@ssw0rd",
            },
        )
        assert response.status_code == HTTPStatus.FOUND
        assert User.objects.filter(email="new-admin@example.com").exists()

    def test_view_user(self, admin_client):
        user = User.objects.get(email="admin@example.com")
        url = reverse("admin:users_user_change", kwargs={"object_id": user.pk})
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

    @pytest.fixture
    def _force_allauth(self, settings):
        settings.DJANGO_ADMIN_FORCE_ALLAUTH = True
        # Reload the admin module to apply the setting change
        import charj.users.admin as users_admin  # noqa: PLC0415

        with contextlib.suppress(admin.sites.AlreadyRegistered):  # type: ignore[attr-defined]
            reload(users_admin)

    @pytest.mark.django_db
    @pytest.mark.usefixtures("_force_allauth")
    def test_allauth_login(self, rf, settings):
        request = rf.get("/fake-url")
        request.user = AnonymousUser()
        response = admin.site.login(request)

        # The `admin` login view should redirect to the `allauth` login view
        target_url = reverse(settings.LOGIN_URL) + "?next=" + request.path
        assertRedirects(response, target_url, fetch_redirect_response=False)


class TestSendFeedbackEmailAction:
    def test_sends_a_separate_message_to_each_user(self, admin_client, mailoutbox):
        """A shared to/cc list would expose every user's address to the others."""
        users = [cast("User", UserFactory()) for _ in range(3)]
        admin_client.post(
            reverse("admin:users_user_changelist"),
            data={
                "action": "send_feedback_email_action",
                "_selected_action": [str(u.pk) for u in users],
            },
        )
        # Set comparison: the changelist orders by -last_login, not creation.
        assert [len(m.to) for m in mailoutbox] == [1, 1, 1]
        assert {m.to[0] for m in mailoutbox} == {u.email for u in users}

    @pytest.mark.django_db
    def test_hidden_from_staff_without_change_permission(self, rf):
        """View-only staff must not be able to mass-email the customer base."""
        request = rf.get("/")
        request.user = cast("User", UserFactory(is_staff=True))
        actions = admin.site._registry[User].get_actions(request)  # noqa: SLF001
        assert "send_feedback_email_action" not in actions
