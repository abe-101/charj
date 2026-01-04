from datetime import UTC
from datetime import datetime

from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    changefreq = "weekly"
    protocol = "https"

    def items(self):
        return [
            {"name": "home", "priority": 1.0},
            {"name": "pricing", "priority": 0.8},
            {"name": "about", "priority": 0.7},
        ]

    def location(self, item):
        return reverse(item["name"])

    def priority(self, item):
        return item["priority"]

    def lastmod(self, item):
        # Return current date for now - in production, track actual page updates
        return datetime(2026, 1, 4, tzinfo=UTC)
