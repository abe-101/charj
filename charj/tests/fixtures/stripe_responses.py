"""Stripe API response fixtures for testing."""

# Customer creation/retrieval response
CUSTOMER_RESPONSE = {
    "id": "cus_test_123",
    "object": "customer",
    "email": None,
    "name": None,
    "description": None,
    "metadata": {},
    "livemode": False,
    "created": 1234567890,
    "balance": 0,
    "currency": "usd",
    "delinquent": False,
    "discount": None,
    "invoice_prefix": "TEST",
    "invoice_settings": {
        "custom_fields": None,
        "default_payment_method": None,
        "footer": None,
    },
    "preferred_locales": [],
    "tax_exempt": "none",
}
