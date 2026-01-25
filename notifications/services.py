import json
import logging
from django.conf import settings
from google import genai
from google.genai import types
from .models import Notification
from invoices.models import Invoice
from core.models import UserProfile
logger = logging.getLogger(__name__)


from django.contrib.auth import get_user_model
from .models import Notification
from clients.models import Client
from invoices.models import Invoice

def create_onboarding_checklist(user_id):
    User = get_user_model()
    user = User.objects.get(pk=user_id)
    
    # Define the steps and the conditions to check
    # Note: Replace field names like 'business_name' with your actual model fields
    checks = [
        {
            'id': 'profile',
            'message': 'Step 1: Setup your business profile (address, VAT, etc).',
            'complete': bool(getattr(user, 'business_name', False)) 
        },
        {
            'id': 'client',
            'message': 'Step 2: Create your first client.',
            'complete': Client.objects.filter(user=user).exists()
        },
        {
            'id': 'timesheet',
            'message': 'Step 3: Log some work in your timesheets.',
            'complete': False # Add your Timesheet model check here
        }
    ]

    # Only create notifications for incomplete tasks
    for check in checks:
        if not check['complete']:
            # get_or_create prevents duplicate "Step 1" toasts every time the task runs
            Notification.objects.get_or_create(
                user=user,
                message=check['message'],
                priority=2 # Use your 'AI/Quiet' styling
            )


def check_onboarding_status(user):
    from invoices.models import Invoice
    from clients.models import Client
    from notifications.models import Notification
    
    tasks = []
    
    # 1. Check Profile
    if not user.business_name: # Replace with your actual profile fields
        tasks.append("Step 1: Complete your Business Profile to enable professional headers.")
        
    # 2. Check Clients
    if not Client.objects.filter(tenant=user.tenant).exists():
        tasks.append("Step 2: Add your first Client to start tracking work.")
        
    # Create notifications for missing steps
    for task in tasks:
        Notification.objects.get_or_create(
            user=user,
            message=task,
            priority=2  # Uses the 'Quiet' AI styling
        )


def get_gemini_suggestions(user):
    """
    Gets personalized suggestions using the new Unified Google GenAI SDK.
    """
    if not settings.GEMINI_API_KEY:
        return []

    # 1. Initialize the new Client
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    
    # 2. Build context-aware prompt
    profile_info = "Profile not created"
    try:
        if hasattr(user, 'profile'):
            p = user.profile
            profile_info = f"Company: {p.company_name}, VAT: {p.is_vat_registered}"
    except Exception:
        pass

    unpaid_count = Invoice.objects.filter(client__user=user, status='unpaid').count()
    
    prompt = f"""
    User: {user.username}
    Context: {profile_info}
    Unpaid Invoices: {unpaid_count}
    
    Suggest 3 short, actionable notifications for this user.
    Return the response as a simple JSON list of strings.
    Example: ["Update your VAT number", "Follow up on 5 invoices", "Complete your profile"]
    """

    try:
        # 3. Use GenerateContentConfig to enforce JSON response
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.5
            )
        )
        
        # 4. Safe JSON parsing
        return json.loads(response.text)
        
    except Exception as e:
        logger.error(f"Gemini API error for user {user.username}: {e}")
        return []



from .models import Notification

def generate_notifications(user):
    """
    Creates a simple, static onboarding checklist for the user
    AND integrates AI-generated personalized suggestions.
    Only creates the notification if it doesn't already exist.
    """
    # Static onboarding steps
    steps = [
        ("Step 1: Setup your business profile", 2),
        ("Step 2: Create your first client", 2),
        ("Step 3: Log your first timesheet", 2),
    ]

    for message, priority in steps:
        Notification.objects.get_or_create(
            user=user,
            message=message,
            priority=priority,
            defaults={'is_read': False}
        )

    # Integrate AI-generated suggestions
    gemini_suggestions = get_gemini_suggestions(user)
    for suggestion in gemini_suggestions:
        # Give AI suggestions a higher priority or different style
        Notification.objects.get_or_create(
            user=user,
            message=suggestion,
            priority=1, # Assuming 1 is a higher priority for AI suggestions
            defaults={'is_read': False}
        )



