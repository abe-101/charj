import json
from http import HTTPStatus

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from djstripe.models import Customer

from charj.cards.views import add_card_view
from charj.cards.views import create_customer_portal_session_view
from charj.cards.views import create_setup_intent_view
from charj.cards.views import create_subscription_view
from charj.cards.views import dashboard_view
from charj.users.models import User

pytestmark = pytest.mark.django_db


class TestDashboardView:
    """Tests for the dashboard view."""

    def test_authenticated_user_can_access(self, user: User, rf: RequestFactory):
        """Authenticated users should be able to access the dashboard."""
        request = rf.get("/fake-url/")
        request.user = user
        response = dashboard_view(request)
        assert response.status_code == HTTPStatus.OK

    def test_unauthenticated_user_redirected(self, client):
        """Unauthenticated users should be redirected to login."""
        response = client.get("/cards/")
        assert response.status_code == HTTPStatus.FOUND
        assert "/accounts/login/" in response.url


class TestCustomerPortalSessionView:
    """Tests for the customer portal session view."""

    def test_creates_portal_session_and_redirects(
        self,
        user: User,
        rf: RequestFactory,
    ):
        """Should create Customer Portal session and redirect to Stripe."""
        request = rf.get("/fake-url/")
        request.user = user
        # Mock build_absolute_uri
        request.build_absolute_uri = lambda x: f"http://testserver{x}"

        response = create_customer_portal_session_view(request)

        assert response.status_code == HTTPStatus.FOUND
        # Should redirect to Stripe billing portal
        assert "billing.stripe.com" in response.url

    def test_requires_authentication(self, rf: RequestFactory, client):
        """Unauthenticated users should be redirected to login."""
        response = client.get("/cards/customer-portal/")
        assert response.status_code == HTTPStatus.FOUND
        assert "/accounts/login/" in response.url


class TestAddCardView:
    """Tests for the add card page view."""

    def test_authenticated_user_can_access(self, user: User, rf: RequestFactory):
        """Authenticated users should be able to access the add card page."""
        request = rf.get("/fake-url/")
        request.user = user
        response = add_card_view(request)
        assert response.status_code == HTTPStatus.OK

    def test_unauthenticated_user_redirected(self, client):
        """Unauthenticated users should be redirected to login."""
        response = client.get("/cards/add/")
        assert response.status_code == HTTPStatus.FOUND
        assert "/accounts/login/" in response.url


class TestCreateSetupIntentView:
    """Tests for the SetupIntent creation API endpoint."""

    def test_creates_setup_intent_successfully(self, user: User, rf: RequestFactory):
        """Should create SetupIntent and return client_secret."""
        request = rf.post("/fake-url/")
        request.user = user
        response = create_setup_intent_view(request)
        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.content)
        assert "clientSecret" in data
        assert data["clientSecret"].startswith("seti_test_")

    def test_requires_authentication(self, rf: RequestFactory):
        """Unauthenticated requests should be rejected."""
        request = rf.post("/fake-url/")
        request.user = AnonymousUser()
        response = create_setup_intent_view(request)
        assert response.status_code == HTTPStatus.UNAUTHORIZED
        data = json.loads(response.content)
        assert "error" in data

    def test_requires_post_method(self, user: User, rf: RequestFactory):
        """GET requests should be rejected."""
        request = rf.get("/fake-url/")
        request.user = user
        response = create_setup_intent_view(request)
        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED


class TestCreateSubscriptionView:
    """Tests for the subscription creation API endpoint."""

    def test_creates_subscription_successfully(
        self,
        user: User,
        rf: RequestFactory,
        settings,
    ):
        """Should create subscription with valid payment method."""
        settings.STRIPE_PRICE_ID = "price_test_123"
        # Create customer first (normally done by SetupIntent view)
        Customer.get_or_create(subscriber=user)

        request = rf.post(
            "/fake-url/",
            data=json.dumps({"payment_method_id": "pm_test_123"}),
            content_type="application/json",
        )
        request.user = user
        response = create_subscription_view(request)
        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.content)
        assert data["success"] is True
        assert "subscription_id" in data

    def test_requires_authentication(self, rf: RequestFactory):
        """Unauthenticated requests should be rejected."""
        request = rf.post(
            "/fake-url/",
            data=json.dumps({"payment_method_id": "pm_test_123"}),
            content_type="application/json",
        )
        request.user = AnonymousUser()
        response = create_subscription_view(request)
        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_validates_payment_method_id_required(self, user: User, rf: RequestFactory):
        """Should reject requests without payment_method_id."""
        request = rf.post(
            "/fake-url/",
            data=json.dumps({}),
            content_type="application/json",
        )
        request.user = user
        response = create_subscription_view(request)
        assert response.status_code == HTTPStatus.BAD_REQUEST
        data = json.loads(response.content)
        assert "payment_method_id" in data["error"]

    def test_validates_price_id_configured(
        self,
        user: User,
        rf: RequestFactory,
        settings,
    ):
        """Should reject requests when STRIPE_PRICE_ID not configured."""
        settings.STRIPE_PRICE_ID = ""
        # Create customer first (normally done by SetupIntent view)
        Customer.get_or_create(subscriber=user)

        request = rf.post(
            "/fake-url/",
            data=json.dumps({"payment_method_id": "pm_test_123"}),
            content_type="application/json",
        )
        request.user = user
        response = create_subscription_view(request)
        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        data = json.loads(response.content)
        assert "pricing not configured" in data["error"]

    def test_requires_post_method(self, user: User, rf: RequestFactory):
        """GET requests should be rejected."""
        request = rf.get("/fake-url/")
        request.user = user
        response = create_subscription_view(request)
        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
