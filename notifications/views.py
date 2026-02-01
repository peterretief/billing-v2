from django.http import JsonResponse

from .models import Notification


def get_notifications(request):
    if not request.user.is_authenticated:
        return JsonResponse([], safe=False)

    # Get the 5 most recent notifications for the logged-in user
    notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-id')[:5]

    # Convert to a list of dictionaries for JSON
    data = [
        {
            "id": n.id,
            "message": n.message,
            "priority": getattr(n, 'priority', 1), # Default to 1 if field missing
        } 
        for n in notifications
    ]
    
    return JsonResponse(data, safe=False)
