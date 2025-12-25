from django.urls import path

from .views import add_card_view
from .views import create_customer_portal_session_view
from .views import create_setup_intent_view
from .views import create_subscription_view
from .views import dashboard_view

app_name = "cards"
urlpatterns = [
    path("", view=dashboard_view, name="dashboard"),
    path("add/", view=add_card_view, name="add"),
    path(
        "customer-portal/",
        view=create_customer_portal_session_view,
        name="customer_portal",
    ),
    path(
        "api/create-setup-intent/",
        view=create_setup_intent_view,
        name="create_setup_intent",
    ),
    path(
        "api/create-subscription/",
        view=create_subscription_view,
        name="create_subscription",
    ),
]
