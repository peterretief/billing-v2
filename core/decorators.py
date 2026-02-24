# core/decorators.py
from functools import wraps

from django.shortcuts import redirect
from django.urls import reverse


def setup_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated:
            # 1. Check if setup is complete
            if not request.user.profile.initial_setup_complete:
                # 2. IMPORTANT: Only redirect if we AREN'T already on the setup page
                # This prevents the "Page isn't redirecting properly" error
                if request.path != reverse("core:initial_setup"):
                    return redirect("core:initial_setup")
        return view_func(request, *args, **kwargs)

    return _wrapped_view
