# AGENTS.md

This file provides guidance to agetns when working with code in this repository.

## Project Overview

Charj is a Django application that helps keep credit cards active with automatic $1 annual charges to prevent account closures and protect credit scores. Built with Cookiecutter Django and integrated with Stripe for payment processing via dj-stripe.

## Development Setup

This project uses `uv` for dependency management. Virtual environment is at `.venv/`.

### Running the Development Server

```bash
uv run python manage.py runserver
```

### Creating Superuser

```bash
uv run python manage.py createsuperuser
```

### Database Migrations

```bash
uv run python manage.py makemigrations
uv run python manage.py migrate
```

## Testing & Quality

### Running Tests

```bash
uv run pytest                          # Run all tests
uv run pytest path/to/test_file.py     # Run specific test file
uv run pytest -k test_name             # Run specific test by name
```

### Test Coverage

```bash
uv run coverage run -m pytest
uv run coverage html
uv run open htmlcov/index.html
```

### Type Checking

```bash
uv run mypy charj
```

### Linting & Formatting

```bash
uv run ruff check .                    # Check for issues
uv run ruff check --fix .              # Auto-fix issues
uv run ruff format .                   # Format code
```

### Template Linting

```bash
uv run djlint charj/templates --reformat  # Format templates
uv run djlint charj/templates             # Check templates
```

### Pre-commit Hooks

```bash
pre-commit install          # Install hooks
pre-commit run --all-files  # Run manually
```

## Architecture

### Settings Configuration

Django settings are split across multiple environment-specific files in `config/settings/`:
- `base.py` - Shared settings for all environments
- `local.py` - Development environment (default via `manage.py`)
- `test.py` - Test environment
- `production.py` - Production environment

The `DJANGO_SETTINGS_MODULE` defaults to `config.settings.local`.

### Custom User Model

Uses a custom User model (`charj.users.User`) with email-based authentication instead of username:
- Located in `charj/users/models.py`
- `USERNAME_FIELD = "email"`
- No username, first_name, or last_name fields
- Single `name` CharField for full name

### Authentication

- Uses django-allauth for authentication with MFA support
- Email verification is mandatory (`ACCOUNT_EMAIL_VERIFICATION = "mandatory"`)
- Custom adapters and forms in `charj/users/`
- Login redirect goes to `users:redirect`

### Stripe Integration

- Uses dj-stripe (>= 2.10.3) for Stripe integration
- Stripe customer creation handled via Django signals in `charj/users/signals.py`
- On user login, checks for orphaned Stripe customers and creates new customer if needed
- Configuration in `config/settings/base.py`:
  - `DJSTRIPE_SUBSCRIBER_MODEL = "users.User"`
  - `DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"`
  - `STRIPE_LIVE_MODE = False` (test mode by default)
- Stripe dashboard accessible at `/djstripe/` (requires djstripe namespace)

### URL Structure

Main URL configuration in `config/urls.py`:
- `/` - Home page
- `/about/` - About page
- `/admin/` - Django admin
- `/users/` - User management URLs
- `/accounts/` - django-allauth authentication URLs
- `/djstripe/` - dj-stripe dashboard

### Django Apps

Local apps are in the `charj/` directory:
- `charj.users` - Custom user model and authentication
- `charj.contrib.sites` - Custom sites migration module

### Templates

Templates are in `charj/templates/`:
- `base.html` - Base template for inheritance
- `pages/` - Static pages (home, about)
- `users/` - User-related templates
- `account/` - django-allauth templates
- Error pages (403.html, 404.html, 500.html, etc.)

### Static Files & Media

- Static files collected to `staticfiles/` in production
- Static source files in `charj/static/`
- Media uploads in `charj/media/`
- WhiteNoise handles static file serving

## Environment Variables

Key environment variables (configured in `.env` file):
- `DATABASE_URL` - PostgreSQL connection string (defaults to `postgres:///charj`)
- `DJANGO_READ_DOT_ENV_FILE` - Set to `True` to read `.env` file
- `STRIPE_TEST_SECRET_KEY` - Stripe test secret key
- `STRIPE_TEST_PUBLIC_KEY` - Stripe test public key
- `REDIS_URL` - Redis connection string (defaults to `redis://localhost:6379/0`)
- `DJANGO_SECRET_KEY` - Django secret key (has default for local dev)
- `DJANGO_DEBUG` - Debug mode flag
- `DJANGO_ACCOUNT_ALLOW_REGISTRATION` - Allow user registration

## Email in Development

Mailpit is used for local email testing:
1. Download Mailpit binary to project root
2. Make executable: `chmod +x mailpit`
3. Run: `./mailpit`
4. View emails at http://127.0.0.1:8025/

Email configuration in local settings:
- `EMAIL_HOST = "localhost"`
- `EMAIL_PORT = 2525`

## Code Style

### Python

- Python 3.13 required (`requires-python = "==3.13.*"`)
- Ruff for linting and formatting with extensive rule set
- Force single-line imports (`force-single-line = true`)
- MyPy for type checking with Django plugin
- Migrations and tests excluded from certain checks

### Templates

- djLint for Django template linting/formatting
- Bootstrap 5 for styling (crispy-bootstrap5)
- Max line length: 119 characters
- 2-space indentation

## Important Patterns

### User Signals

The `charj/users/signals.py` file contains critical Stripe customer creation logic that runs on user login. When modifying user authentication flow, ensure this signal continues to work correctly.

### Settings Pattern

Environment-specific settings import from base: `from .base import *`. Always add new shared settings to `base.py` and override only what's needed in environment files.

### Migration Modules

Custom sites migrations are in `charj/contrib/sites/migrations/` due to `MIGRATION_MODULES` setting. Don't create migrations in the default Django sites app location.

## Testing Configuration

Tests use:
- `--ds=config.settings.test` - Test settings module
- `--reuse-db` - Reuse test database between runs
- `--import-mode=importlib` - Import mode
- Coverage plugin: django_coverage_plugin
- Test files: `tests.py` or `test_*.py`
- Factory Boy for test fixtures
