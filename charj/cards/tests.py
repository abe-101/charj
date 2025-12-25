import json
from http import HTTPStatus

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from djstripe.models import Customer
from djstripe.models import PaymentMethod

from charj.cards.services import CardDisplay
from charj.cards.services import get_user_cards
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


class TestCardDisplayService:
    """Tests for the card display service layer."""

    def test_get_user_cards_returns_empty_list_when_no_cards(
        self,
        user: User,
    ):
        """Should return empty list when user has no payment methods."""
        cards = get_user_cards(user)
        assert cards == []

    def test_get_user_cards_returns_card_display_objects(
        self,
        user: User,
    ):
        """Should return CardDisplay objects with correct primitive data."""
        # Create customer and payment method
        customer, _ = Customer.get_or_create(subscriber=user)

        # Create a test payment method with stripe_data
        PaymentMethod.objects.create(
            id="pm_test_123",
            customer=customer,
            livemode=False,
            stripe_data={
                "id": "pm_test_123",
                "type": "card",
                "card": {
                    "brand": "visa",
                    "last4": "4242",
                    "exp_month": 12,
                    "exp_year": 2030,
                },
            },
        )

        cards = get_user_cards(user)

        assert len(cards) == 1
        card = cards[0]
        assert isinstance(card, CardDisplay)
        assert card.payment_method_id == "pm_test_123"
        assert card.brand == "visa"
        assert card.last4 == "4242"
        assert card.exp_month == 12  # noqa: PLR2004
        assert card.exp_year == 2030  # noqa: PLR2004

    def test_card_display_is_pure_data(
        self,
        user: User,
    ):
        """CardDisplay should contain only primitives, no Django models."""
        # Create customer and payment method
        customer, _ = Customer.get_or_create(subscriber=user)

        PaymentMethod.objects.create(
            id="pm_test_456",
            customer=customer,
            livemode=False,
            stripe_data={
                "id": "pm_test_456",
                "type": "card",
                "card": {
                    "brand": "mastercard",
                    "last4": "5555",
                    "exp_month": 6,
                    "exp_year": 2029,
                },
            },
        )

        cards = get_user_cards(user)
        card = cards[0]

        # Verify all fields are primitives
        assert isinstance(card.payment_method_id, str)
        assert isinstance(card.brand, str)
        assert isinstance(card.last4, str)
        assert isinstance(card.exp_month, int)
        assert isinstance(card.exp_year, int)
        assert isinstance(card.is_default, bool)
        assert card.subscription_status is None or isinstance(
            card.subscription_status,
            str,
        )
        assert card.subscription_id is None or isinstance(card.subscription_id, str)

    def test_card_display_properties(self):
        """Test has_subscription and is_active properties."""
        # Card with active subscription
        card_with_active = CardDisplay(
            payment_method_id="pm_1",
            brand="visa",
            last4="4242",
            exp_month=12,
            exp_year=2030,
            is_default=False,
            subscription_status="active",
            subscription_id="sub_123",
        )
        assert card_with_active.has_subscription is True
        assert card_with_active.is_active is True

        # Card without subscription
        card_without_sub = CardDisplay(
            payment_method_id="pm_2",
            brand="mastercard",
            last4="5555",
            exp_month=6,
            exp_year=2029,
            is_default=False,
        )
        assert card_without_sub.has_subscription is False
        assert card_without_sub.is_active is False

        # Card with canceled subscription
        card_canceled = CardDisplay(
            payment_method_id="pm_3",
            brand="amex",
            last4="1234",
            exp_month=3,
            exp_year=2028,
            is_default=False,
            subscription_status="canceled",
            subscription_id="sub_456",
        )
        assert card_canceled.has_subscription is True
        assert card_canceled.is_active is False


class TestDashboardViewWithCards:
    """Tests for dashboard view with card display functionality."""

    def test_context_includes_cards_data(
        self,
        user: User,
        rf: RequestFactory,
    ):
        """Dashboard should include cards_data in context."""
        request = rf.get("/fake-url/")
        request.user = user
        response = dashboard_view(request)

        assert response.status_code == HTTPStatus.OK
        assert "cards_data" in response.context_data
        assert "has_cards" in response.context_data

    def test_empty_state_when_no_cards(
        self,
        user: User,
        rf: RequestFactory,
    ):
        """Should show empty state when user has no cards."""
        request = rf.get("/fake-url/")
        request.user = user
        response = dashboard_view(request)

        assert response.status_code == HTTPStatus.OK
        assert response.context_data["has_cards"] is False
        assert len(response.context_data["cards_data"]) == 0

    def test_displays_payment_methods(
        self,
        user: User,
        rf: RequestFactory,
    ):
        """Should display payment methods when they exist."""
        # Create customer and payment method
        customer, _ = Customer.get_or_create(subscriber=user)

        PaymentMethod.objects.create(
            id="pm_test_789",
            customer=customer,
            livemode=False,
            stripe_data={
                "id": "pm_test_789",
                "type": "card",
                "card": {
                    "brand": "visa",
                    "last4": "9999",
                    "exp_month": 9,
                    "exp_year": 2031,
                },
            },
        )

        request = rf.get("/fake-url/")
        request.user = user
        response = dashboard_view(request)

        assert response.status_code == HTTPStatus.OK
        assert response.context_data["has_cards"] is True
        assert len(response.context_data["cards_data"]) == 1
        card = response.context_data["cards_data"][0]
        assert card.brand == "visa"
        assert card.last4 == "9999"
