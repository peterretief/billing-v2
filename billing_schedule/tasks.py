# billing_scheduler/tasks.py
from celery import shared_task

from .models import BillingPolicy


@shared_task
def process_daily_billing_queue():
    # This automatically respects multi-tenancy if your 
    # userModel handles default filtering.
    policies_to_run = BillingPolicy.objects.due_today()
    
    for policy in policies_to_run:
        # Trigger the log for now to prove it works
        print(f"Policy '{policy.name}' for user {policy.user} is firing!")
        
        # Step 2 will be: Find items linked to this policy and invoice them.