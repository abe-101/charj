import pytest
import responses

from charj.tests.fixtures.stripe_responses import CUSTOMER_RESPONSE
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
            json=CUSTOMER_RESPONSE,
            status=200,
        )

        # Mock customer retrieval endpoint
        rsps.add(
            responses.GET,
            "https://api.stripe.com/v1/customers/cus_test_123",
            json=CUSTOMER_RESPONSE,
            status=200,
        )

        yield rsps
