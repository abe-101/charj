"""Service layer for card management functionality."""

import logging
from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING

import attrs
from djstripe.models import Customer
from djstripe.models import PaymentMethod

from charj.cards.pricing_service import format_frequency_display
from charj.cards.pricing_service import format_price_display

if TYPE_CHECKING:
    from djstripe.models import Subscription


logger = logging.getLogger(__name__)

# Card brand name mapping: Stripe brand → filename
CARD_BRAND_IMAGES = {
    "visa": "visa.png",
    "mastercard": "mastercard.png",
    "amex": "amex.png",
    "discover": "discover.png",
    # "diners": "diners.png",  # noqa: ERA001
    # "jcb": "jcb.png",  # noqa: ERA001
    # "unionpay": "unionpay.png",  # noqa: ERA001
    # "cartes_bancaires": "cartes_bancaires.png",  # noqa: ERA001
}

FALLBACK_CARD_IMAGE = "card.png"  # Generic card icon fallback


def get_card_brand_image(brand: str) -> str:
    """
    Map Stripe card brand to image filename.

    Args:
        brand: Stripe card brand (e.g., "visa", "mastercard", "amex")

    Returns:
        Image filename with extension
    """
    brand_lower = brand.lower() if brand else ""
    return CARD_BRAND_IMAGES.get(brand_lower, FALLBACK_CARD_IMAGE)


@attrs.define
class CardDisplay:
    """Pure data class representing a card for dashboard display."""

    payment_method_id: str
    brand: str
    brand_image: str
    last4: str
    exp_month: int
    exp_year: int
    is_default: bool
    subscription_status: str | None = None
    subscription_id: str | None = None
    next_billing_date: datetime | None = None
    subscription_amount_cents: int | None = None
    subscription_interval: str | None = None
    subscription_interval_count: int | None = None

    @property
    def has_subscription(self) -> bool:
        """Check if card has a subscription."""
        return self.subscription_id is not None

    @property
    def is_active(self) -> bool:
        """Check if card has active subscription."""
        return self.subscription_status == "active"

    @property
    def subscription_amount_display(self) -> str | None:
        """Return formatted amount like '$5.00' or '$5' for whole dollars."""
        if self.subscription_amount_cents is None:
            return None
        return format_price_display(self.subscription_amount_cents)

    @property
    def subscription_frequency_display(self) -> str | None:
        """Return human-readable frequency like 'monthly' or 'every 3 months'."""
        if not self.subscription_interval:
            return None
        return format_frequency_display(
            self.subscription_interval,
            self.subscription_interval_count or 1,
        )

    @property
    def subscription_price_display(self) -> str | None:
        """Return combined price/frequency like '$5/month'."""
        amount = self.subscription_amount_display
        if not amount:
            return None
        if not self.subscription_interval:
            return amount
        count = self.subscription_interval_count or 1
        if count == 1:
            return f"{amount}/{self.subscription_interval}"
        plural_intervals = {
            "day": "days",
            "week": "weeks",
            "month": "months",
            "year": "years",
        }
        interval_plural = plural_intervals.get(
            self.subscription_interval,
            f"{self.subscription_interval}s",
        )
        return f"{amount} every {count} {interval_plural}"


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
        pm: PaymentMethod  # type hint for IDEs
        card_data = pm.stripe_data.get("card", {})

        # Skip if not a card type
        if pm.type != "card":
            logger.exception(
                msg="Unexpected payment method type",
                extra={"payment_method_id": pm.id, "type": pm.type},
            )
            continue

        # Find subscription using this payment method and extract data
        subscription_status = None
        subscription_id = None
        next_billing_date = None
        subscription_amount_cents = None
        subscription_interval = None
        subscription_interval_count = None

        for sub in customer.subscriptions.all():
            sub: Subscription  # type hint for IDEs
            if sub.default_payment_method == pm.id:
                subscription_status = sub.status
                subscription_id = sub.id

                # Extract next billing date from current_period_end
                current_period_end = sub.current_period_end
                if current_period_end:
                    # current_period_end is Unix timestamp
                    next_billing_date = datetime.fromtimestamp(
                        current_period_end,
                        tz=UTC,
                    )

                # Extract price details from subscription items
                try:
                    sub_items = sub.items.all()
                    if sub_items:
                        first_item = sub_items[0]
                        price = first_item.price
                        if price:
                            subscription_amount_cents = price.unit_amount
                            # Get recurring info from stripe_data
                            recurring = price.stripe_data.get("recurring", {})
                            subscription_interval = recurring.get("interval")
                            subscription_interval_count = recurring.get(
                                "interval_count",
                                1,
                            )
                except (AttributeError, IndexError, TypeError):
                    logger.warning(
                        "Failed to extract price details from subscription",
                        exc_info=True,
                        extra={
                            "subscription_id": subscription_id,
                            "payment_method_id": pm.id,
                        },
                    )

                break

        brand = card_data.get("brand", "card")

        cards.append(
            CardDisplay(
                payment_method_id=pm.id,
                brand=brand,
                brand_image=get_card_brand_image(brand),
                last4=card_data.get("last4", "****"),
                exp_month=card_data.get("exp_month", 0),
                exp_year=card_data.get("exp_year", 0),
                is_default=(pm.id == default_pm_id),
                subscription_status=subscription_status,
                subscription_id=subscription_id,
                next_billing_date=next_billing_date,
                subscription_amount_cents=subscription_amount_cents,
                subscription_interval=subscription_interval,
                subscription_interval_count=subscription_interval_count,
            ),
        )

    return cards
