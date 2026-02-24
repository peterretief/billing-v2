from core.models import UserProfile

from .models import Notification


def onboarding(request):
    if not request.user.is_authenticated:
        return {"show_onboarding_bar": False}

    tasks = Notification.objects.filter(user=request.user, priority=2, is_read=False).order_by("message")

    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    # Explicitly calculate the boolean
    has_tasks = tasks.exists()
    user_wants_tips = profile.show_onboarding_tips
    final_decision = has_tasks and user_wants_tips

    return {
        "onboarding_tasks": tasks,
        "show_onboarding_bar": final_decision,
    }
