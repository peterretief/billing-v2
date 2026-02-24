# core/middleware.py
import zoneinfo

from django.utils import timezone


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
