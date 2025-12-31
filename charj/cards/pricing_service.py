"""Pricing service for dynamic subscription price management."""

import logging

import stripe
from django.conf import settings
from djstripe.models import Price

logger = logging.getLogger(__name__)


class PricingError(Exception):
    """Base exception for pricing service errors."""


class InvalidPricingParametersError(PricingError):
    """Exception raised for invalid pricing parameters."""


def validate_pricing_parameters(
    amount_cents: int,
    interval: str,
    interval_count: int,
) -> None:
    """
    Validate pricing parameters against configured constraints.

    Args:
        amount_cents: Amount in cents (minimum 50 cents per Stripe)
        interval: Billing interval ('day', 'week', 'month', 'year')
        interval_count: Number of intervals between billings

    Raises:
        InvalidPricingParametersError: If any parameter is invalid
    """
    # Validate amount
    min_amount = getattr(settings, "STRIPE_MIN_AMOUNT_CENTS", 50)
    max_amount = getattr(settings, "STRIPE_MAX_AMOUNT_CENTS", 100000)

    if not isinstance(amount_cents, int) or amount_cents < min_amount:
        msg = f"Amount must be at least {min_amount} cents (${min_amount / 100:.2f})"
        raise InvalidPricingParametersError(msg)
    if amount_cents > max_amount:
        msg = f"Amount cannot exceed {max_amount} cents (${max_amount / 100:.2f})"
        raise InvalidPricingParametersError(msg)

    # Validate interval
    allowed_intervals = getattr(
        settings,
        "STRIPE_ALLOWED_INTERVALS",
        ["day", "week", "month", "year"],
    )
    if interval not in allowed_intervals:
        allowed = ", ".join(allowed_intervals)
        msg = f"Invalid interval '{interval}'. Must be one of: {allowed}"
        raise InvalidPricingParametersError(msg)

    # Validate interval_count
    max_interval_count = getattr(settings, "STRIPE_MAX_INTERVAL_COUNT", 36)
    if not isinstance(interval_count, int) or interval_count < 1:
        msg = "Interval count must be at least 1"
        raise InvalidPricingParametersError(msg)
    if interval_count > max_interval_count:
        msg = f"Interval count cannot exceed {max_interval_count}"
        raise InvalidPricingParametersError(msg)


def generate_lookup_key(amount_cents: int, interval: str, interval_count: int) -> str:
    """
    Generate a standardized lookup key for a price combination.

    Format: {interval}_{interval_count}_{amount_cents}
    Example: month_1_500 (monthly, $5.00)

    Args:
        amount_cents: Amount in cents
        interval: Billing interval
        interval_count: Number of intervals

    Returns:
        Standardized lookup key string
    """
    return f"{interval}_{interval_count}_{amount_cents}"


def get_or_create_price(
    amount_cents: int,
    interval: str,
    interval_count: int = 1,
) -> str:
    """
    Get or create a Stripe Price for the given parameters.

    Implements three-tier lookup:
    1. Local djstripe cache (fastest)
    2. Stripe API lookup via lookup_key
    3. Dynamic creation if not found

    Args:
        amount_cents: Amount in cents (minimum 50 cents)
        interval: Billing interval ('day', 'week', 'month', 'year')
        interval_count: Number of intervals between billings (default 1)

    Returns:
        Stripe Price ID (e.g., 'price_xxx')

    Raises:
        InvalidPricingParametersError: If parameters are invalid
        PricingError: If price creation fails
    """
    # Validate parameters
    validate_pricing_parameters(amount_cents, interval, interval_count)

    lookup_key = generate_lookup_key(amount_cents, interval, interval_count)

    # Tier 1: Check local djstripe cache
    try:
        local_price = Price.objects.filter(
            lookup_key=lookup_key,
            active=True,
        ).first()

        if local_price:
            logger.info(
                "Price found in local cache",
                extra={
                    "price_id": local_price.id,
                    "lookup_key": lookup_key,
                    "tier": "local_cache",
                },
            )
            return local_price.id
    except Exception:  # noqa: BLE001 - Catch all to ensure Stripe API fallback
        logger.warning(
            "Error checking local price cache",
            exc_info=True,
            extra={"lookup_key": lookup_key},
        )

    # Tier 2: Check Stripe API via lookup_key
    try:
        stripe_prices = stripe.Price.list(lookup_keys=[lookup_key], active=True)
        if stripe_prices.data:
            stripe_price = stripe_prices.data[0]
            logger.info(
                "Price found via Stripe API lookup",
                extra={
                    "price_id": stripe_price.id,
                    "lookup_key": lookup_key,
                    "tier": "stripe_api_lookup",
                },
            )
            # Sync to local database for future lookups
            Price.sync_from_stripe_data(stripe_price)
            return stripe_price.id
    except stripe.error.StripeError:
        logger.warning(
            "Error looking up price via Stripe API",
            exc_info=True,
            extra={"lookup_key": lookup_key},
        )

    # Tier 3: Create new price
    product_id = getattr(settings, "STRIPE_PRODUCT_ID", None)
    if not product_id:
        msg = "STRIPE_PRODUCT_ID not configured. Cannot create dynamic prices."
        raise PricingError(msg)

    try:
        new_price = stripe.Price.create(
            product=product_id,
            unit_amount=amount_cents,
            currency="usd",
            recurring={
                "interval": interval,
                "interval_count": interval_count,
            },
            lookup_key=lookup_key,
            transfer_lookup_key=True,
            metadata={
                "created_by": "charj_pricing_service",
                "amount_cents": str(amount_cents),
                "interval": interval,
                "interval_count": str(interval_count),
            },
        )
    except stripe.error.StripeError as e:
        logger.exception(
            "Failed to create price in Stripe",
            extra={
                "lookup_key": lookup_key,
                "amount_cents": amount_cents,
                "interval": interval,
                "interval_count": interval_count,
                "product_id": product_id,
            },
        )
        msg = f"Failed to create price: {e!s}"
        raise PricingError(msg) from e

    logger.info(
        "New price created",
        extra={
            "price_id": new_price.id,
            "lookup_key": lookup_key,
            "amount_cents": amount_cents,
            "interval": interval,
            "interval_count": interval_count,
            "tier": "created",
        },
    )

    # Sync to local database
    Price.sync_from_stripe_data(new_price)

    return new_price.id


def format_price_display(amount_cents: int) -> str:
    """
    Format amount in cents to display string.

    Args:
        amount_cents: Amount in cents

    Returns:
        Formatted string like '$5.00' or '$5' for whole dollars
    """
    dollars = amount_cents / 100
    if dollars == int(dollars):
        return f"${int(dollars)}"
    return f"${dollars:.2f}"


def format_frequency_display(interval: str, interval_count: int) -> str:
    """
    Format billing frequency to human-readable string.

    Args:
        interval: Billing interval ('day', 'week', 'month', 'year')
        interval_count: Number of intervals

    Returns:
        Human-readable string like 'monthly', 'every 3 months', 'yearly'
    """
    if interval_count == 1:
        interval_names = {
            "day": "daily",
            "week": "weekly",
            "month": "monthly",
            "year": "yearly",
        }
        return interval_names.get(interval, f"every {interval}")

    # Pluralize interval for count > 1
    plural_intervals = {
        "day": "days",
        "week": "weeks",
        "month": "months",
        "year": "years",
    }
    interval_plural = plural_intervals.get(interval, f"{interval}s")
    return f"every {interval_count} {interval_plural}"
