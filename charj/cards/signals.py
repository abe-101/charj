import logging
from typing import Any

import stripe
from django.conf import settings
from djstripe.event_handlers import djstripe_receiver
from djstripe.models import Customer
from djstripe.models import Event
from djstripe.models import Subscription

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


@djstripe_receiver("customer.subscription.created")
def handle_subscription_update(
    sender: Any,
    event: Event,
    **kwargs: dict[str, Any],
) -> None:
    customer_id: str = event.data["object"]["customer"]
    customer: Customer = Customer.objects.get(id=customer_id)
    subscription: Subscription = Subscription.objects.get(
        id=event.data["object"]["id"],
    )
    logger.info(
        msg="Customer subscription created",
        extra={
            "customer_id": customer.id,
            "subscription_id": subscription.id,
            "status": subscription.status,
        },
    )
