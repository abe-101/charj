# Claude Code / Sandbox Environment Setup

Setup guide for Claude Code on the web and other fresh, network-restricted
sandbox environments. Every hurdle documented here was hit in a real agent
session — follow this file top to bottom and `uv run pytest` and the dev
server will work on a fresh clone.

## 1. System prerequisites

`psycopg-c` is compiled from source during `uv sync` and fails with
`pg_config.h: No such file or directory` unless the PostgreSQL client
headers are installed:

```bash
sudo apt-get install -y libpq-dev
```

## 2. PostgreSQL

The default `DATABASE_URL` is `postgres:///charj` (peer-authenticated local
socket). A fresh container has the cluster stopped and no role or database:

```bash
pg_ctlcluster 16 main start    # adjust version; or: service postgresql start
sudo -u postgres psql -c "CREATE ROLE \"$(whoami)\" SUPERUSER LOGIN;"
sudo -u postgres createdb charj -O "$(whoami)"
```

Then:

```bash
uv sync
uv run python manage.py migrate
```

`uv run pytest` works from this point (tests use `config.settings.test`
with `--reuse-db`).

## 3. Creating a user you can actually log in with

Email verification is mandatory (`ACCOUNT_EMAIL_VERIFICATION = "mandatory"`),
so a user created with `createsuperuser` cannot log in through the UI until
a verified allauth `EmailAddress` exists. Create a ready-to-use account
non-interactively:

```bash
uv run python manage.py shell -c "
from django.contrib.auth import get_user_model
from allauth.account.models import EmailAddress
U = get_user_model()
u, _ = U.objects.get_or_create(email='dev@example.com', defaults={'name': 'Dev'})
u.set_password('dev-pass-123'); u.is_active = True; u.save()
EmailAddress.objects.update_or_create(user=u, email=u.email,
    defaults={'verified': True, 'primary': True})
"
```

## 4. Login calls the Stripe API — pre-seed a Customer

The `user_logged_in` signal (`charj/users/signals.py`) calls
`Customer.get_or_create()`, which makes a **live HTTPS request to
api.stripe.com**. In a sandbox with no network access (or with the dummy
`sk_test_12345` key), **every login returns a 500**.

Workaround: seed a djstripe `Customer` for your test user so the signal's
queryset is non-empty and it never reaches the API:

```bash
uv run python manage.py shell -c "
from django.contrib.auth import get_user_model
from djstripe.models import Customer
u = get_user_model().objects.get(email='dev@example.com')
Customer.objects.get_or_create(id='cus_local_dev',
    defaults={'email': u.email, 'subscriber': u, 'livemode': False})
"
```

## 5. Frontend pages depend on external CDNs

Templates load scripts from `js.stripe.com`, `cdnjs.cloudflare.com`
(Bootstrap), `googletagmanager.com`, and `m.charj.cc`. Restricted network
policies block these, and on the Add Card page the failure is total: the
inline script calls `Stripe(...)` before attaching any event listeners, so
`Stripe is not defined` aborts the script and **the page renders but nothing
responds** (preset buttons, custom amount, summary).

For browser-based verification (Playwright), stub the Stripe script so the
page's own code runs unmodified:

```js
await page.route('https://js.stripe.com/v3/', route => route.fulfill({
  contentType: 'application/javascript',
  body: `window.Stripe = function () { return {
    elements: () => ({ create: () => ({ mount: () => {}, addEventListener: () => {} }) }),
    confirmCardSetup: () => Promise.resolve({})
  }; };`,
}));
```

The other blocked scripts (analytics, Bootstrap JS) only log console errors
and don't break the pricing flow.

## 6. Things that hit the Stripe API and cannot work offline

No workaround exists for these in a sandbox — verify them with unit tests
(which mock Stripe) rather than live:

- Creating a subscription (`/cards/create-subscription/`) — attaches the
  payment method and creates prices/subscriptions in Stripe.
- The Customer Portal redirect (`/cards/customer-portal/`).
- `stripe.confirmCardSetup()` in the browser.
