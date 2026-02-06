import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import get_random_string

# Import your verified billing logic and the new models
from items.services import import_recurring_to_invoices
from items.utils import is_first_working_day

from .models import BillingBatch

logger = logging.getLogger(__name__)
User = get_user_model()


def create_and_invite_tenant(request, ops_user, username, email, company_name, **extra_profile_data):
    """
    Ops Manager Tenant Onboarding Service.

    This service function orchestrates the tenant invitation workflow as depicted
    in the user flow diagram. It handles the initial creation of the user and
    their associated profile data, and then dispatches a password reset email,
    which acts as a secure invitation link.

    **Workflow Steps:**
    1.  **Create User & Partial Profile:** An Ops Manager provides essential details
        (username, email, company). A new `User` account is created with a secure,
        unusable password.
    2.  **Trigger Reset Request:** The service automatically generates a password
        reset token and sends an email to the new tenant. This leverages
        Django's built-in, secure password reset functionality.
    3.  **Tenant Clicks Link:** The tenant follows the link in the email to a
        secure page to set their password.
    4.  **Tenant Sets Password & Finalizes Data:** After setting their password,
        the tenant should be redirected to their profile page to confirm or
        update their business details (address, tax info, etc.).
    5.  **Review & Approval:** The `verified_by` field on the profile creates a
        digital paper trail, showing which Ops Manager initiated the setup.
        A future enhancement would be to add a `status` field (e.g., 'INVITED',
        'ACTIVE', 'LOCKED') to the UserProfile model for more formal review
        processes.

    Args:
        request (HttpRequest): The Django request object, needed for generating
                               absolute URLs in the password reset email.
        ops_user (User): The authenticated operations user performing the action.
        username (str): The desired username for the new tenant.
        email (str): The new tenant's email address.
        company_name (str): The name of the tenant's company.
        **extra_profile_data: A dictionary of additional optional data to
                                pre-populate the user's profile, such as
                                currency, vat_number, etc.

    Returns:
        The newly created User instance if successful.

    Raises:
        ValueError: If a user with the given username or email already exists.
        Exception: Propagates any other exceptions that occur during the transaction
                   to be handled by the calling view or task.
    """
    # Prevent IntegrityError by checking for existing users first.
    if User.objects.filter(username=username).exists():
        raise ValueError(f"A user with the username '{username}' already exists.")
    if User.objects.filter(email=email).exists():
        raise ValueError(f"A user with the email '{email}' already exists.")

    try:
        with transaction.atomic():
            # Step 1: Create User with a temporary, unusable password.
            # The user will never see or use this password.
            temp_password = get_random_string(40)
            user = User.objects.create_user(
                username=username,
                email=email,
                password=temp_password
            )

            # Step 2: Pre-populate the UserProfile with data from the Ops Manager.
            # The UserProfile is created automatically via a post-save signal.
            profile = user.profile
            profile.company_name = company_name
            # Note: To fully implement the "Lock" feature, a 'settings_locked'
            # boolean field could be added to the UserProfile model.
            profile.currency = extra_profile_data.get('currency', 'GBP')
            profile.vat_number = extra_profile_data.get('vat_number', '')
            profile.vat_rate = extra_profile_data.get('vat_rate', 20.00)

            # Step 5 (Partial): Mark who initiated this account for audit purposes.
            # A full implementation would involve a status field on the profile.
            profile.verified_by = ops_user
            profile.save()

            # Step 3: Trigger the password reset email, which serves as the invite.
            form = PasswordResetForm({'email': user.email})
            if form.is_valid():
                form.save(
                    email_template_name='ops/emails/invite_email.html',
                    subject_template_name='ops/emails/invite_subject.txt',
                    request=request
                )
            else:
                # This case should ideally not be reached if email is valid
                raise Exception("Failed to initialize password reset for the new user.")

            logger.info(
                f"Ops User '{ops_user.username}' successfully invited tenant "
                f"'{username}' ({email})."
            )
            return user

    except Exception as e:
        logger.error(
            f"Error during tenant invitation for email '{email}': {str(e)}",
            exc_info=True  # Log the full traceback for debugging
        )
        # Re-raise the exception to be handled by the caller.
        raise e


def populate_monthly_batch():
    """
    Identifies all active users and creates a queue entry for today.
    Typically called by a Celery task on the First Working Day.
    """
    today = timezone.now().date()

    # Optional: Safety check to ensure we only run on the first working day
    if not is_first_working_day(today):
        logger.info(f"Skipping batch population: {today} is not the first working day.")
        return 0

    active_users = User.objects.filter(is_active=True)
    queued_count = 0

    for user in active_users:
        # get_or_create prevents duplicate queue items if the task re-runs
        batch_item, created = BillingBatch.objects.get_or_create(
            user=user,
            scheduled_date=today
        )
        if created:
            queued_count += 1

    logger.info(f"Created {queued_count} billing queue items for {today}")
    return queued_count


def process_ops_queue(limit=50):
    """
    The 'Worker' service. Picks up unprocessed items from the BillingBatch
    and executes the actual invoicing logic.
    """
    # Grab a batch of unprocessed items
    pending_items = BillingBatch.objects.filter(
        is_processed=False,
        scheduled_date=timezone.now().date()
    ).select_related('user', 'user__userprofile')[:limit]

    processed_count = 0

    for item in pending_items:
        try:
            with transaction.atomic():
                # 1. Trigger the heavy lifting logic we already tested
                # This creates invoices, emails them, and returns the list
                results = import_recurring_to_invoices(item.user)

                # 2. Mark this user as finished in the Ops Queue
                item.is_processed = True
                item.processed_at = timezone.now()
                item.metadata = {
                    'invoices_created': len(results),
                    'currency_used': getattr(item.user.profile, 'currency', 'USD')
                }
                item.save()
                processed_count += 1

                logger.info(f"Ops Queue: Successfully processed billing for {item.user.username}")

        except Exception as e:
            item.error_message = str(e)
            item.save()
            logger.error(f"Ops Queue Error for {item.user.username}: {str(e)}")

    return processed_count