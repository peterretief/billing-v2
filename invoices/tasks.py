# /opt/billing_v2/invoices/tasks.py
import logging
from celery import shared_task
from django.contrib.auth import get_user_model
from invoices.models import Invoice
from notifications.models import Notification

logger = logging.getLogger(__name__)


# invoices/tasks.py
from notifications.services import create_onboarding_checklist


@shared_task
def generate_ai_insights_task(user_id):
    create_onboarding_checklist(user_id)

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
        
        # Simple logic for now to see if it's working
        # Later we can add the full Gemini API call here
        msg = f"AI Analysis: System check complete for {user.username}."
        
        Notification.objects.get_or_create(
            user=user,
            message=msg,
            priority=2
        )
        return "Success"
    except Exception as e:
        logger.error(f"Task failed: {e}")
        return "Failed"


#from celery import shared_task
#from google import genai
#from django.conf import settings

#from invoices.models import Invoice
## Change this to point to your specific notifications app
#from notifications.models import Notification

#@shared_task
#def generate_ai_insights_task(user_id):
    # 1. Fetch data safely in the background
#    unpaid_invoices = Invoice.objects.filter(user_id=user_id, status='unpaid')
    
    # 2. Call Gemini (This can now take as long as it needs!)
#    client = genai.Client(api_key=settings.GEMINI_API_KEY)
#    prompt = f"Analyze these {unpaid_invoices.count()} unpaid invoices for cashflow risks."
    
#    response = client.models.generate_content(
##        model="gemini-2.0-flash",
#        contents=prompt
 #   )
#    
    # 3. Save the result as a notification
#    Notification.objects.create(
#        user_id=user_id,
#        message=response.text[:255],
#        priority=2
#    )
#    return "Insight generated"