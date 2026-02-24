from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from invoices.models import InvoiceEmailStatusLog


class Command(BaseCommand):
    help = "Diagnose Brevo webhook delivery issues"

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24, help="Check emails from the last N hours (default: 24)")

    def handle(self, *args, **options):
        hours = options["hours"]
        cutoff_time = timezone.now() - timedelta(hours=hours)

        self.stdout.write(self.style.SUCCESS(f"\n=== Brevo Webhook Diagnostics (last {hours} hours) ===\n"))

        # Get all sent status records
        sent_logs = InvoiceEmailStatusLog.objects.filter(status="sent", created_at__gte=cutoff_time).order_by(
            "-created_at"
        )

        self.stdout.write(f"Total emails sent: {sent_logs.count()}\n")

        # Categorize into groups
        updated_count = 0
        stuck_count = 0
        detailed_info = []

        for log in sent_logs:
            msg_id = log.brevo_message_id
            # Check if this message has any updates beyond 'sent'
            other_logs = InvoiceEmailStatusLog.objects.filter(brevo_message_id=msg_id).exclude(status="sent").exists()

            if other_logs:
                updated_count += 1
            else:
                stuck_count += 1
                age_minutes = (timezone.now() - log.created_at).total_seconds() / 60
                detailed_info.append(
                    {
                        "invoice_id": log.invoice_id,
                        "message_id": msg_id,
                        "created": log.created_at,
                        "age_minutes": age_minutes,
                        "user_id": log.user_id,
                    }
                )

        self.stdout.write(self.style.WARNING(f"Status Updates Received: {updated_count}"))
        self.stdout.write(self.style.ERROR(f'Stuck on "sent": {stuck_count}'))

        if stuck_count > 0:
            self.stdout.write("\n" + self.style.ERROR("=== EMAILS WAITING FOR DELIVERY UPDATES ===\n"))

            # Group by time ranges
            by_age = {"0-5min": [], "5-30min": [], "30-60min": [], "60+ min": []}
            for info in detailed_info:
                age = info["age_minutes"]
                if age < 5:
                    by_age["0-5min"].append(info)
                elif age < 30:
                    by_age["5-30min"].append(info)
                elif age < 60:
                    by_age["30-60min"].append(info)
                else:
                    by_age["60+ min"].append(info)

            for time_range, items in by_age.items():
                if items:
                    self.stdout.write(f"{time_range}: {len(items)} emails")
                    if time_range in ["0-5min", "5-30min"]:
                        self.stdout.write("  (Waiting for Brevo - this is normal)")
                    else:
                        self.stdout.write(self.style.WARNING("  ⚠ DELAYED - Check Brevo webhook configuration"))

            self.stdout.write("\nOldest stuck emails:")
            for info in sorted(detailed_info, key=lambda x: x["created"])[:5]:
                age_str = f"{info['age_minutes']:.1f}min"
                self.stdout.write(f"  Invoice {info['invoice_id']}: {age_str} old")

        self.stdout.write("\n" + self.style.SUCCESS("=== RECOMMENDATIONS ===\n"))

        if stuck_count > 0 and any(info["age_minutes"] > 60 for info in detailed_info):
            self.stdout.write(self.style.ERROR("1. CHECK BREVO WEBHOOK CONFIGURATION"))
            self.stdout.write("   - Go to Brevo account → Settings → Webhooks")
            self.stdout.write("   - Verify webhook URL is correct:")
            self.stdout.write("     https://yourdomain.com/webhooks/brevo/")
            self.stdout.write("   - Check webhook is enabled and events are checked")
            self.stdout.write("   - Check API key is valid\n")

        self.stdout.write(self.style.SUCCESS("2. MANUAL SYNC OPTION"))
        self.stdout.write("   - Use the sync_invoice_status endpoint to manually")
        self.stdout.write("     pull latest delivery status from Brevo API\n")

        if sent_logs.count() > 0 and updated_count == 0:
            self.stdout.write(self.style.ERROR("3. ⚠ CRITICAL: NO WEBHOOKS RECEIVED AT ALL"))
            self.stdout.write("   - Webhooks may be completely disabled")
            self.stdout.write("   - Check Brevo webhook settings immediately\n")

        # Final status
        self.stdout.write(self.style.SUCCESS("\n=== WEBHOOK HEALTH ===\n"))
        if sent_logs.count() == 0:
            self.stdout.write("No emails sent in this period")
        else:
            health_pct = (updated_count / sent_logs.count() * 100) if sent_logs.count() > 0 else 0
            if health_pct >= 80:
                self.stdout.write(self.style.SUCCESS(f"✓ HEALTHY: {health_pct:.0f}% updates received"))
            elif health_pct >= 50:
                self.stdout.write(self.style.WARNING(f"⚠ DEGRADED: {health_pct:.0f}% updates received"))
            else:
                self.stdout.write(self.style.ERROR(f"✗ BROKEN: {health_pct:.0f}% updates received"))
