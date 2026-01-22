from .models import Notification

def onboarding(request):
    if request.user.is_authenticated:
        # Only fetch tasks that have NOT been read/completed
        tasks = Notification.objects.filter(
            user=request.user, 
            priority=2, 
            is_read=False
        ).order_by('message') # Keeps Step 1, 2, 3 in order
        
        return {
            'onboarding_tasks': tasks,
            'onboarding_complete': not tasks.exists(),
        }
    return {}
