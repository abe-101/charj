from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = "monthly"
    protocol = "https"

    def items(self):
        return ["home", "pricing", "about"]

    def location(self, item):
        return reverse(item)
