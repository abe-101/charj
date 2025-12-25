"""Service layer for card management functionality."""

import attrs
from djstripe.models import Customer
from djstripe.models import PaymentMethod


@attrs.define
class CardDisplay:
    """Pure data class representing a card for dashboard display."""

    payment_method_id: str
    brand: str
    last4: str
    exp_month: int
    exp_year: int
    is_default: bool
    subscription_status: str | None = None
    subscription_id: str | None = None

    @property
    def has_subscription(self) -> bool:
        """Check if card has a subscription."""
        return self.subscription_id is not None

    @property
    def is_active(self) -> bool:
        """Check if card has active subscription."""
        return self.subscription_status == "active"


def get_user_cards(user) -> list[CardDisplay]:
    """
    Fetch and build card display data for a user.

    Args:
        user: The Django user object

    Returns:
        List of CardDisplay objects with payment method and subscription info
    """
    # Get or create customer
    customer, _ = Customer.get_or_create(subscriber=user)

    # Get all payment methods
    payment_methods = PaymentMethod.objects.filter(customer=customer).order_by(
        "-created",
    )

    # Get customer's default payment method
    default_pm_id = customer.stripe_data.get("default_payment_method")

    # Build card display objects
    cards = []
    for pm in payment_methods:
        card_data = pm.stripe_data.get("card", {})

        # Skip if not a card type
        if pm.stripe_data.get("type") != "card":
            continue

        # Find subscription using this payment method and extract data
        subscription_status = None
        subscription_id = None
        for sub in customer.subscriptions.all():
            if sub.stripe_data.get("default_payment_method") == pm.id:
                subscription_status = sub.stripe_data.get("status")
                subscription_id = sub.id
                break

        cards.append(
            CardDisplay(
                payment_method_id=pm.id,
                brand=card_data.get("brand", "card"),
                last4=card_data.get("last4", "****"),
                exp_month=card_data.get("exp_month", 0),
                exp_year=card_data.get("exp_year", 0),
                is_default=(pm.id == default_pm_id),
                subscription_status=subscription_status,
                subscription_id=subscription_id,
            ),
        )

    return cards
