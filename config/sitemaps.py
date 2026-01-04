"""
Sitemap configuration for charj.cc

This module defines the sitemaps for SEO optimization,
helping search engines discover and index all public pages.
"""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    """Sitemap for static pages that don't have database models."""

    protocol = "https"

    def items(self):
        """Return list of URL names for static pages."""
        return [
            "home",
            "about",
            "features",
            "how-it-works",
            "pricing",
        ]

    def location(self, item):
        """Return the URL for each item."""
        return reverse(item)

    def priority(self, item):
        """Set priority based on page importance."""
        priorities = {
            "home": 1.0,
            "about": 0.7,
            "features": 0.8,
            "how-it-works": 0.8,
            "pricing": 0.9,
        }
        return priorities.get(item, 0.5)

    def changefreq(self, item):
        """Set change frequency based on page type."""
        if item == "home":
            return "weekly"
        return "monthly"


sitemaps = {
    "static": StaticViewSitemap,
}
