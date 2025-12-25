import pytest
import responses

from charj.tests.fixtures import stripe_responses as stripe_fixtures
from charj.users.models import User
from charj.users.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def _media_storage(settings, tmpdir) -> None:
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture
def user(db) -> User:
    return UserFactory()


@pytest.fixture(autouse=True)
def mock_stripe_api():
    """
    Session-wide mock for Stripe API requests.
    Uses response fixtures from charj.tests.fixtures.stripe_responses.
    """
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        # Mock customer creation endpoint
        rsps.add(
            responses.POST,
            "https://api.stripe.com/v1/customers",
            json=stripe_fixtures.CUSTOMER_RESPONSE,
            status=200,
        )

        # Mock customer retrieval endpoint
        rsps.add(
            responses.GET,
            "https://api.stripe.com/v1/customers/cus_test_123",
            json=stripe_fixtures.CUSTOMER_RESPONSE,
            status=200,
        )

        # Mock SetupIntent creation
        rsps.add(
            responses.POST,
            "https://api.stripe.com/v1/setup_intents",
            json=stripe_fixtures.SETUP_INTENT_RESPONSE,
            status=200,
        )

        # Mock PaymentMethod retrieval
        rsps.add(
            responses.GET,
            "https://api.stripe.com/v1/payment_methods/pm_test_123",
            json=stripe_fixtures.PAYMENT_METHOD_RESPONSE,
            status=200,
        )

        # Mock Subscription creation
        rsps.add(
            responses.POST,
            "https://api.stripe.com/v1/subscriptions",
            json=stripe_fixtures.SUBSCRIPTION_RESPONSE,
            status=200,
        )

        # Mock Customer Portal Session creation
        rsps.add(
            responses.POST,
            "https://api.stripe.com/v1/billing_portal/sessions",
            json=stripe_fixtures.CUSTOMER_PORTAL_SESSION_RESPONSE,
            status=200,
        )

        yield rsps
