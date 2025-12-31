import json
import logging

import stripe
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from djstripe.models import Customer

from charj.cards.pricing_service import InvalidPricingParametersError
from charj.cards.pricing_service import PricingError
from charj.cards.pricing_service import get_or_create_price
from charj.cards.services import get_user_cards

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class DashboardView(TemplateView):
    """Dashboard showing card management options."""

    template_name = "cards/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cards_data = get_user_cards(self.request.user)
        context["cards_data"] = cards_data
        context["has_cards"] = len(cards_data) > 0
        logger.info(
            "Dashboard data loaded",
            extra={"card_count": len(cards_data), "has_cards": len(cards_data) > 0},
        )
        return context


dashboard_view = DashboardView.as_view()


def create_customer_portal_session_view(request):
    """Create a Stripe Customer Portal session and redirect to it."""
    try:
        # Get or create customer
        customer, _ = Customer.get_or_create(subscriber=request.user)

        # Create Customer Portal session
        session = stripe.billing_portal.Session.create(
            customer=customer.id,
            return_url=request.build_absolute_uri(reverse("cards:dashboard")),
        )

        logger.info(
            "Customer Portal session created",
            extra={
                "customer_id": customer.id,
                "user_id": request.user.id,
                "session_id": session.id,
            },
        )

        return redirect(session.url)

    except stripe.error.StripeError:
        logger.exception(
            "Stripe error creating Customer Portal session",
            extra={"user_id": request.user.id},
        )
        # Redirect back to dashboard with error (could add message framework)
        return redirect("cards:dashboard")
    except Exception:
        logger.exception(
            "Unexpected error creating Customer Portal session",
            extra={"user_id": request.user.id},
        )
        return redirect("cards:dashboard")


class AddCardView(TemplateView):
    """Render the add card form page with Stripe Elements."""

    template_name = "cards/add_card.html"

    def get_context_data(self, **kwargs):
        logger.info("Add card page accessed")
        context = super().get_context_data(**kwargs)
        context["stripe_public_key"] = settings.STRIPE_PUBLIC_KEY
        # Pricing configuration for frontend
        context["min_amount_cents"] = getattr(settings, "STRIPE_MIN_AMOUNT_CENTS", 50)
        context["max_amount_cents"] = getattr(
            settings,
            "STRIPE_MAX_AMOUNT_CENTS",
            100000,
        )
        context["allowed_intervals"] = getattr(
            settings,
            "STRIPE_ALLOWED_INTERVALS",
            ["day", "week", "month", "year"],
        )
        context["max_interval_count"] = getattr(
            settings,
            "STRIPE_MAX_INTERVAL_COUNT",
            36,
        )
        # Default values ($1/year)
        context["default_amount_cents"] = 100
        context["default_interval"] = "year"
        context["default_interval_count"] = 1
        return context


add_card_view = AddCardView.as_view()


@require_POST
def create_setup_intent_view(request):
    """Create a Stripe SetupIntent for collecting payment method."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        customer, _ = Customer.get_or_create(subscriber=request.user)

        setup_intent = stripe.SetupIntent.create(
            customer=customer.id,
            payment_method_types=["card"],
            metadata={
                "user_id": request.user.id,
                "user_email": request.user.email,
            },
        )

        logger.info(
            "SetupIntent created",
            extra={
                "setup_intent_id": setup_intent.id,
                "customer_id": customer.id,
                "user_id": request.user.id,
            },
        )

        return JsonResponse({"clientSecret": setup_intent.client_secret})

    except stripe.error.StripeError:
        logger.exception(
            "Stripe error creating SetupIntent",
            extra={"user_id": request.user.id},
        )
        return JsonResponse(
            {"error": "Failed to initialize payment method setup"},
            status=500,
        )
    except Exception:
        logger.exception(
            "Unexpected error creating SetupIntent",
            extra={"user_id": request.user.id},
        )
        return JsonResponse({"error": "An unexpected error occurred"}, status=500)


def _cleanup_payment_method(payment_method_id: str, user_id: int) -> None:
    """
    Detach a payment method from the customer to clean up after failed subscription.

    Args:
        payment_method_id: The Stripe payment method ID to detach
        user_id: The user ID for logging purposes
    """
    try:
        stripe.PaymentMethod.detach(payment_method_id)
        logger.info(
            "Payment method detached after subscription failure",
            extra={
                "payment_method_id": payment_method_id,
                "user_id": user_id,
            },
        )
    except stripe.error.StripeError:
        logger.warning(
            "Failed to detach payment method after subscription failure",
            exc_info=True,
            extra={
                "payment_method_id": payment_method_id,
                "user_id": user_id,
            },
        )


@require_POST
def create_subscription_view(request):  # noqa: PLR0911, C901
    """Create subscription with custom pricing after payment method is confirmed."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    payment_method_id = None  # Track for cleanup on failure

    try:
        data = json.loads(request.body)
        payment_method_id = data.get("payment_method_id")

        if not payment_method_id:
            return JsonResponse({"error": "payment_method_id is required"}, status=400)

        # Extract pricing parameters with defaults ($1/year)
        amount_cents = data.get("amount_cents", 100)
        interval = data.get("interval", "year")
        interval_count = data.get("interval_count", 1)

        # Validate types
        try:
            amount_cents = int(amount_cents)
            interval_count = int(interval_count)
        except (TypeError, ValueError):
            _cleanup_payment_method(payment_method_id, request.user.id)
            return JsonResponse(
                {"error": "amount_cents and interval_count must be integers"},
                status=400,
            )

        try:
            customer = Customer.objects.get(subscriber=request.user)
        except Customer.DoesNotExist:
            logger.exception(
                "Customer not found for user",
                extra={"user_id": request.user.id},
            )
            _cleanup_payment_method(payment_method_id, request.user.id)
            return JsonResponse(
                {"error": "Customer account not found"},
                status=404,
            )

        # Verify payment method belongs to this customer
        payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
        if payment_method.customer != customer.id:
            logger.warning(
                "Payment method customer mismatch",
                extra={
                    "payment_method_id": payment_method_id,
                    "pm_customer": payment_method.customer,
                    "expected_customer": customer.id,
                    "user_id": request.user.id,
                },
            )
            _cleanup_payment_method(payment_method_id, request.user.id)
            return JsonResponse({"error": "Invalid payment method"}, status=403)

        # Get or create price for the requested parameters
        try:
            price_id = get_or_create_price(
                amount_cents=amount_cents,
                interval=interval,
                interval_count=interval_count,
            )
        except InvalidPricingParametersError as e:
            logger.warning(
                "Invalid pricing parameters",
                extra={
                    "user_id": request.user.id,
                    "amount_cents": amount_cents,
                    "interval": interval,
                    "interval_count": interval_count,
                    "error": str(e),
                },
            )
            _cleanup_payment_method(payment_method_id, request.user.id)
            return JsonResponse({"error": str(e)}, status=400)
        except PricingError as e:
            logger.exception(
                "Pricing service error",
                extra={
                    "user_id": request.user.id,
                    "amount_cents": amount_cents,
                    "interval": interval,
                    "interval_count": interval_count,
                },
            )
            _cleanup_payment_method(payment_method_id, request.user.id)
            return JsonResponse(
                {"error": f"Failed to configure pricing: {e!s}"},
                status=500,
            )

        # Create subscription with dynamic price
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": price_id}],
            default_payment_method=payment_method_id,
            metadata={
                "user_id": request.user.id,
                "user_email": request.user.email,
                "payment_method_id": payment_method_id,
                "amount_cents": str(amount_cents),
                "interval": interval,
                "interval_count": str(interval_count),
            },
        )

        logger.info(
            "Subscription created successfully",
            extra={
                "subscription_id": subscription.id,
                "customer_id": customer.id,
                "payment_method_id": payment_method_id,
                "user_id": request.user.id,
                "price_id": price_id,
                "amount_cents": amount_cents,
                "interval": interval,
                "interval_count": interval_count,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "subscription_id": subscription.id,
                "status": subscription.status,
            },
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except stripe.error.StripeError as e:
        logger.exception(
            "Stripe error creating subscription",
            extra={"user_id": request.user.id},
        )
        if payment_method_id:
            _cleanup_payment_method(payment_method_id, request.user.id)
        return JsonResponse(
            {"error": f"Failed to create subscription: {e!s}"},
            status=500,
        )
    except Exception:
        logger.exception(
            "Unexpected error creating subscription",
            extra={"user_id": request.user.id},
        )
        if payment_method_id:
            _cleanup_payment_method(payment_method_id, request.user.id)
        return JsonResponse({"error": "An unexpected error occurred"}, status=500)
