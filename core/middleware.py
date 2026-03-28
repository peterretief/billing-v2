# core/middleware.py
import zoneinfo

from django.utils import timezone
from .current_user import set_current_user, clear_current_user


class TenantMiddleware:
    """
    Sets the current user in thread-local storage so that TenantManager
    can automatically filter queries.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            set_current_user(request.user)
        else:
            set_current_user(None)

        try:
            response = self.get_response(request)
        finally:
            clear_current_user()

        return response


class UserTimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Start with a safe default
        tzname = "Africa/Johannesburg"

        # 2. Only try to customize if the user is logged in
        if request.user.is_authenticated:
            try:
                # 3. Check if the profile exists and has a timezone
                if hasattr(request.user, "userprofile") and request.user.userprofile.timezone:
                    tzname = request.user.userprofile.timezone
            except Exception:
                # If anything goes wrong, fall back to default instead of crashing
                pass

        try:
            timezone.activate(zoneinfo.ZoneInfo(tzname))
        except zoneinfo.ZoneInfoNotFoundError:
            timezone.activate(zoneinfo.ZoneInfo("UTC"))

        return self.get_response(request)
