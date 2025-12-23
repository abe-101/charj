import logging
from typing import Any

import stripe
from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.http import HttpRequest
from djstripe.models import Customer

from .models import User

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


@receiver(signal=user_logged_in)
def create_stripe_customer(
    sender: Any,
    request: HttpRequest,
    user: User,
    **kwargs: dict[str, Any],
) -> None:
    customers = Customer.objects.filter(email=user.email)
    for customer in customers:
        if not customer.subscriber:
            logger.warning(
                "Orphaned Stripe customer attached to user",
                extra={
                    "event": "NEEDS_EVENT",
                    "customer_id": customer.id,
                    "user_id": user.pk,
                    "email": user.email,
                },
            )
            customer.subscriber = user
            customer.save()
    if not customers:
        customer, created = Customer.get_or_create(subscriber=user)
        if created:
            logger.info(
                "Stripe customer created with trial subscription",
                extra={
                    "event": "NEEDS_EVENT",
                    "customer_id": customer.id,
                    "user_id": user.pk,
                    "email": user.email,
                },
            )
