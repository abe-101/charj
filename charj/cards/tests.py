import json
from http import HTTPStatus

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from djstripe.models import Customer
from djstripe.models import PaymentMethod

from charj.cards.pricing_service import InvalidPricingParametersError
from charj.cards.pricing_service import PricingError
from charj.cards.pricing_service import format_frequency_display
from charj.cards.pricing_service import format_price_display
from charj.cards.pricing_service import generate_lookup_key
from charj.cards.pricing_service import get_or_create_price
from charj.cards.pricing_service import validate_pricing_parameters
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
        # Now uses dynamic pricing via STRIPE_PRODUCT_ID
        settings.STRIPE_PRODUCT_ID = "prod_test_123"
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

    def test_validates_product_id_configured(
        self,
        user: User,
        rf: RequestFactory,
        settings,
    ):
        """Should reject requests when STRIPE_PRODUCT_ID not configured."""
        settings.STRIPE_PRODUCT_ID = ""
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
        assert "STRIPE_PRODUCT_ID not configured" in data["error"]

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
            brand_image="visa.png",
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
            brand_image="mastercard.png",
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
            brand_image="amex.png",
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


class TestPricingServiceValidation:
    """Tests for pricing service validation functions."""

    def test_validate_pricing_parameters_valid(self):
        """Valid parameters should not raise exceptions."""
        # No exception means validation passed
        validate_pricing_parameters(100, "year", 1)
        validate_pricing_parameters(50, "month", 1)  # Minimum amount
        validate_pricing_parameters(100000, "week", 36)  # Max amount and interval count
        validate_pricing_parameters(500, "day", 7)

    def test_validate_pricing_parameters_amount_too_low(self, settings):
        """Amount below minimum should raise error."""
        settings.STRIPE_MIN_AMOUNT_CENTS = 50
        with pytest.raises(InvalidPricingParametersError) as exc_info:
            validate_pricing_parameters(49, "year", 1)
        assert "at least 50 cents" in str(exc_info.value)

    def test_validate_pricing_parameters_amount_too_high(self, settings):
        """Amount above maximum should raise error."""
        settings.STRIPE_MAX_AMOUNT_CENTS = 100000
        with pytest.raises(InvalidPricingParametersError) as exc_info:
            validate_pricing_parameters(100001, "year", 1)
        assert "cannot exceed" in str(exc_info.value)

    def test_validate_pricing_parameters_invalid_interval(self, settings):
        """Invalid interval should raise error."""
        settings.STRIPE_ALLOWED_INTERVALS = ["day", "week", "month", "year"]
        with pytest.raises(InvalidPricingParametersError) as exc_info:
            validate_pricing_parameters(100, "biweekly", 1)
        assert "Invalid interval" in str(exc_info.value)

    def test_validate_pricing_parameters_interval_count_zero(self):
        """Interval count of 0 should raise error."""
        with pytest.raises(InvalidPricingParametersError) as exc_info:
            validate_pricing_parameters(100, "year", 0)
        assert "at least 1" in str(exc_info.value)

    def test_validate_pricing_parameters_interval_count_negative(self):
        """Negative interval count should raise error."""
        with pytest.raises(InvalidPricingParametersError) as exc_info:
            validate_pricing_parameters(100, "year", -1)
        assert "at least 1" in str(exc_info.value)

    def test_validate_pricing_parameters_interval_count_too_high(self, settings):
        """Interval count above maximum should raise error."""
        settings.STRIPE_MAX_INTERVAL_COUNT = 36
        with pytest.raises(InvalidPricingParametersError) as exc_info:
            validate_pricing_parameters(100, "year", 37)
        assert "cannot exceed 36" in str(exc_info.value)


class TestPricingServiceLookupKey:
    """Tests for lookup key generation."""

    def test_generate_lookup_key_basic(self):
        """Generate correct lookup key format."""
        assert generate_lookup_key(100, "year", 1) == "year_1_100"
        assert generate_lookup_key(500, "month", 1) == "month_1_500"
        assert generate_lookup_key(1000, "week", 2) == "week_2_1000"
        assert generate_lookup_key(50, "day", 7) == "day_7_50"

    def test_generate_lookup_key_large_values(self):
        """Lookup keys work with large values."""
        assert generate_lookup_key(100000, "month", 36) == "month_36_100000"


class TestPricingServiceFormatting:
    """Tests for display formatting functions."""

    def test_format_price_display_whole_dollars(self):
        """Whole dollar amounts should not show cents."""
        assert format_price_display(100) == "$1"
        assert format_price_display(500) == "$5"
        assert format_price_display(10000) == "$100"

    def test_format_price_display_with_cents(self):
        """Non-whole dollar amounts should show cents."""
        assert format_price_display(50) == "$0.50"
        assert format_price_display(199) == "$1.99"
        assert format_price_display(1550) == "$15.50"

    def test_format_frequency_display_single_interval(self):
        """Single interval counts show friendly names."""
        assert format_frequency_display("day", 1) == "daily"
        assert format_frequency_display("week", 1) == "weekly"
        assert format_frequency_display("month", 1) == "monthly"
        assert format_frequency_display("year", 1) == "yearly"

    def test_format_frequency_display_multiple_intervals(self):
        """Multiple interval counts show 'every X intervals'."""
        assert format_frequency_display("day", 7) == "every 7 days"
        assert format_frequency_display("week", 2) == "every 2 weeks"
        assert format_frequency_display("month", 3) == "every 3 months"
        assert format_frequency_display("year", 2) == "every 2 years"


class TestGetOrCreatePrice:
    """Tests for the main get_or_create_price function."""

    def test_creates_new_price_when_not_cached(self, settings, db):
        """Should create new price via Stripe API when not in cache."""
        settings.STRIPE_PRODUCT_ID = "prod_test_123"
        price_id = get_or_create_price(100, "year", 1)
        assert price_id == "price_test_dynamic"

    def test_rejects_invalid_parameters(self, settings):
        """Should reject invalid pricing parameters."""
        settings.STRIPE_PRODUCT_ID = "prod_test_123"
        with pytest.raises(InvalidPricingParametersError):
            get_or_create_price(10, "year", 1)  # Below minimum

    def test_raises_error_when_product_id_not_configured(self, settings, db):
        """Should raise error when STRIPE_PRODUCT_ID not set."""
        settings.STRIPE_PRODUCT_ID = ""
        with pytest.raises(PricingError) as exc_info:
            get_or_create_price(100, "year", 1)
        assert "STRIPE_PRODUCT_ID not configured" in str(exc_info.value)


class TestCardDisplayPriceProperties:
    """Tests for CardDisplay price-related properties."""

    def test_subscription_amount_display_whole_dollar(self):
        """Whole dollar amounts display without cents."""
        card = CardDisplay(
            payment_method_id="pm_1",
            brand="visa",
            brand_image="visa.png",
            last4="4242",
            exp_month=12,
            exp_year=2030,
            is_default=False,
            subscription_amount_cents=100,
        )
        assert card.subscription_amount_display == "$1"

    def test_subscription_amount_display_with_cents(self):
        """Non-whole dollar amounts display with cents."""
        card = CardDisplay(
            payment_method_id="pm_1",
            brand="visa",
            brand_image="visa.png",
            last4="4242",
            exp_month=12,
            exp_year=2030,
            is_default=False,
            subscription_amount_cents=550,
        )
        assert card.subscription_amount_display == "$5.50"

    def test_subscription_amount_display_none(self):
        """None amount returns None display."""
        card = CardDisplay(
            payment_method_id="pm_1",
            brand="visa",
            brand_image="visa.png",
            last4="4242",
            exp_month=12,
            exp_year=2030,
            is_default=False,
        )
        assert card.subscription_amount_display is None

    def test_subscription_frequency_display_monthly(self):
        """Monthly interval displays correctly."""
        card = CardDisplay(
            payment_method_id="pm_1",
            brand="visa",
            brand_image="visa.png",
            last4="4242",
            exp_month=12,
            exp_year=2030,
            is_default=False,
            subscription_interval="month",
            subscription_interval_count=1,
        )
        assert card.subscription_frequency_display == "monthly"

    def test_subscription_frequency_display_every_3_months(self):
        """Multiple intervals display correctly."""
        card = CardDisplay(
            payment_method_id="pm_1",
            brand="visa",
            brand_image="visa.png",
            last4="4242",
            exp_month=12,
            exp_year=2030,
            is_default=False,
            subscription_interval="month",
            subscription_interval_count=3,
        )
        assert card.subscription_frequency_display == "every 3 months"

    def test_subscription_price_display_combined(self):
        """Combined price and frequency display correctly."""
        card = CardDisplay(
            payment_method_id="pm_1",
            brand="visa",
            brand_image="visa.png",
            last4="4242",
            exp_month=12,
            exp_year=2030,
            is_default=False,
            subscription_amount_cents=500,
            subscription_interval="month",
            subscription_interval_count=1,
        )
        assert card.subscription_price_display == "$5/month"

    def test_subscription_price_display_every_3_months(self):
        """Combined price with multiple intervals."""
        card = CardDisplay(
            payment_method_id="pm_1",
            brand="visa",
            brand_image="visa.png",
            last4="4242",
            exp_month=12,
            exp_year=2030,
            is_default=False,
            subscription_amount_cents=1000,
            subscription_interval="month",
            subscription_interval_count=3,
        )
        assert card.subscription_price_display == "$10 every 3 months"


class TestCreateSubscriptionViewWithCustomPricing:
    """Tests for subscription creation with custom pricing parameters."""

    def test_creates_subscription_with_default_pricing(
        self,
        user: User,
        rf: RequestFactory,
        settings,
    ):
        """Should create subscription with default $1/year when no pricing params."""
        settings.STRIPE_PRODUCT_ID = "prod_test_123"
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

    def test_creates_subscription_with_custom_amount(
        self,
        user: User,
        rf: RequestFactory,
        settings,
    ):
        """Should create subscription with custom amount."""
        settings.STRIPE_PRODUCT_ID = "prod_test_123"
        Customer.get_or_create(subscriber=user)

        request = rf.post(
            "/fake-url/",
            data=json.dumps(
                {
                    "payment_method_id": "pm_test_123",
                    "amount_cents": 500,
                    "interval": "month",
                    "interval_count": 1,
                },
            ),
            content_type="application/json",
        )
        request.user = user
        response = create_subscription_view(request)
        assert response.status_code == HTTPStatus.OK
        data = json.loads(response.content)
        assert data["success"] is True

    def test_rejects_invalid_amount(
        self,
        user: User,
        rf: RequestFactory,
        settings,
    ):
        """Should reject subscription with invalid amount."""
        settings.STRIPE_PRODUCT_ID = "prod_test_123"
        settings.STRIPE_MIN_AMOUNT_CENTS = 50
        Customer.get_or_create(subscriber=user)

        request = rf.post(
            "/fake-url/",
            data=json.dumps(
                {
                    "payment_method_id": "pm_test_123",
                    "amount_cents": 10,  # Below minimum
                    "interval": "year",
                    "interval_count": 1,
                },
            ),
            content_type="application/json",
        )
        request.user = user
        response = create_subscription_view(request)
        assert response.status_code == HTTPStatus.BAD_REQUEST
        data = json.loads(response.content)
        assert "at least" in data["error"]

    def test_rejects_invalid_interval(
        self,
        user: User,
        rf: RequestFactory,
        settings,
    ):
        """Should reject subscription with invalid interval."""
        settings.STRIPE_PRODUCT_ID = "prod_test_123"
        Customer.get_or_create(subscriber=user)

        request = rf.post(
            "/fake-url/",
            data=json.dumps(
                {
                    "payment_method_id": "pm_test_123",
                    "amount_cents": 100,
                    "interval": "biweekly",  # Invalid
                    "interval_count": 1,
                },
            ),
            content_type="application/json",
        )
        request.user = user
        response = create_subscription_view(request)
        assert response.status_code == HTTPStatus.BAD_REQUEST
        data = json.loads(response.content)
        assert "Invalid interval" in data["error"]

    def test_cleans_up_payment_method_on_pricing_error(
        self,
        user: User,
        rf: RequestFactory,
        settings,
        mock_stripe_api,
    ):
        """Should detach payment method when pricing validation fails."""
        settings.STRIPE_PRODUCT_ID = "prod_test_123"
        settings.STRIPE_MIN_AMOUNT_CENTS = 50
        Customer.get_or_create(subscriber=user)

        request = rf.post(
            "/fake-url/",
            data=json.dumps(
                {
                    "payment_method_id": "pm_test_123",
                    "amount_cents": 10,  # Below minimum - will fail
                    "interval": "year",
                    "interval_count": 1,
                },
            ),
            content_type="application/json",
        )
        request.user = user
        response = create_subscription_view(request)

        # Should fail with bad request
        assert response.status_code == HTTPStatus.BAD_REQUEST

        # Check that detach was called (via mock_stripe_api)
        detach_calls = [
            call for call in mock_stripe_api.calls if "detach" in call.request.url
        ]
        assert len(detach_calls) == 1
