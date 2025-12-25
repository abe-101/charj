"""Views for project-level pages."""

from django.contrib.auth.decorators import login_not_required
from django.shortcuts import redirect
from django.shortcuts import render


@login_not_required
def home(request):
    """
    Landing page view.

    If user is authenticated, redirect to cards dashboard.
    Otherwise, show the public landing page.
    """
    if request.user.is_authenticated:
        return redirect("cards:dashboard")
    return render(request, "pages/home.html")
