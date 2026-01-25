from celery import shared_task
from .services import generate_notifications

@shared_task
def generate_notifications_async(user_id):
    """
    Asynchronous task to generate notifications for a user.
    """
    # Import User model inside the task to avoid AppRegistryNotReady error
    from core.models import User
    try:
        user = User.objects.get(pk=user_id)
        generate_notifications(user)
    except User.DoesNotExist:
        print(f"User with id {user_id} not found for notification generation.")
    except Exception as e:
        print(f"Error generating notifications for user {user_id}: {e}")