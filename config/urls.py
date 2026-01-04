from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_not_required
from django.contrib.sitemaps.views import sitemap
from django.urls import include
from django.urls import path
from django.views import defaults as default_views
from django.views.generic import TemplateView

from config.sitemaps import sitemaps

urlpatterns = [
    # Public SEO pages
    path(
        "",
        login_not_required(TemplateView.as_view(template_name="pages/home.html")),
        name="home",
    ),
    path(
        "about/",
        login_not_required(TemplateView.as_view(template_name="pages/about.html")),
        name="about",
    ),
    path(
        "features/",
        login_not_required(TemplateView.as_view(template_name="pages/features.html")),
        name="features",
    ),
    path(
        "how-it-works/",
        login_not_required(
            TemplateView.as_view(template_name="pages/how-it-works.html"),
        ),
        name="how-it-works",
    ),
    path(
        "pricing/",
        login_not_required(TemplateView.as_view(template_name="pages/pricing.html")),
        name="pricing",
    ),
    path(
        "sitemap.xml",
        login_not_required(sitemap),
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path(
        "robots.txt",
        login_not_required(
            TemplateView.as_view(template_name="robots.txt", content_type="text/plain"),
        ),
        name="robots",
    ),
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    # User management
    path("users/", include("charj.users.urls", namespace="users")),
    path("accounts/", include("allauth.urls")),
    # Your stuff: custom urls includes go here
    path("cards/", include("charj.cards.urls", namespace="cards")),
    # ...
    path("djstripe/", include("djstripe.urls", namespace="djstripe")),
    # Media files
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]


if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
            *urlpatterns,
        ]
