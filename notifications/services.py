import json
import logging

from django.conf import settings
from google import genai
from google.genai import types

from invoices.models import Invoice

from .models import Notification

logger = logging.getLogger(__name__)


from django.contrib.auth import get_user_model

from clients.models import Client


def create_onboarding_checklist(user_id):
    User = get_user_model()
    user = User.objects.get(pk=user_id)

    # Import models for checklist
    from items.models import Item
    from timesheets.models import TimesheetEntry

    # Define the steps and the conditions to check
    checks = [
        {
            "id": "profile",
            "message": "Step 1: Setup your business profile (address, VAT, etc).",
            "complete": bool(getattr(user, "business_name", False)),
        },
        {
            "id": "client",
            "message": "Step 2: Create your first client.",
            "complete": Client.objects.filter(user=user).exists(),
        },
        {"id": "item", "message": "Step 3: Add your first item.", "complete": Item.objects.filter(user=user).exists()},
        {
            "id": "timesheet",
            "message": "Step 4: Log some work in your timesheets.",
            "complete": TimesheetEntry.objects.filter(user=user).exists(),
        },
    ]

    # Only create notifications for incomplete tasks
    for check in checks:
        if not check["complete"]:
            # get_or_create prevents duplicate "Step 1" toasts every time the task runs
            Notification.objects.get_or_create(
                user=user,
                message=check["message"],
                priority=2,  # Use your 'AI/Quiet' styling
            )


def check_onboarding_status(user):
    from clients.models import Client
    from notifications.models import Notification

    tasks = []

    # 1. Check Profile
    if not user.business_name:  # Replace with your actual profile fields
        tasks.append("Step 1: Complete your Business Profile to enable professional headers.")

    # 2. Check Clients
    if not Client.objects.filter(tenant=user.tenant).exists():
        tasks.append("Step 2: Add your first Client to start tracking work.")

    # Create notifications for missing steps
    for task in tasks:
        Notification.objects.get_or_create(
            user=user,
            message=task,
            priority=2,  # Uses the 'Quiet' AI styling
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
        if hasattr(user, "profile"):
            p = user.profile
            profile_info = f"Company: {p.company_name}, VAT: {p.is_vat_registered}"
    except Exception:
        pass

    unpaid_count = Invoice.objects.filter(client__user=user, status="unpaid").count()

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
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.5),
        )

        # 4. Safe JSON parsing
        return json.loads(response.text)

    except Exception as e:
        logger.error(f"Gemini API error for user {user.username}: {e}")
        return []


def generate_notifications(user):
    """
    Creates a simple, static onboarding checklist for the user
    AND integrates AI-generated personalized suggestions.
    Only creates the notification if it doesn't already exist.
    """
    # Import models for checklist
    from items.models import Item
    from timesheets.models import TimesheetEntry

    # Define the steps and the conditions to check
    steps = [
        {
            "message": "Step 1: Setup your business profile (address, VAT, etc).",
            "priority": 2,
            "complete": bool(getattr(user, "business_name", False)),
        },
        {
            "message": "Step 2: Create your first client.",
            "priority": 2,
            "complete": Client.objects.filter(user=user).exists(),
        },
        {"message": "Step 3: Add your first item.", "priority": 2, "complete": Item.objects.filter(user=user).exists()},
        {
            "message": "Step 4: Log some work in your timesheets.",
            "priority": 2,
            "complete": TimesheetEntry.objects.filter(user=user).exists(),
        },
    ]

    for step in steps:
        if not step["complete"]:
            Notification.objects.get_or_create(
                user=user, message=step["message"], priority=step["priority"], defaults={"is_read": False}
            )

    # Integrate AI-generated suggestions
    gemini_suggestions = get_gemini_suggestions(user)
    for suggestion in gemini_suggestions:
        # Give AI suggestions a higher priority or different style
        Notification.objects.get_or_create(
            user=user,
            message=suggestion,
            priority=1,  # Assuming 1 is a higher priority for AI suggestions
            defaults={"is_read": False},
        )
