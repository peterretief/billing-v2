#!/usr/bin/env python
"""
Automated Log Monitoring Script
Monitors email_status.log and other logs for errors/failures
Sends alerts and daily summaries
"""

import os
import sys
import django
from datetime import datetime, timedelta
from pathlib import Path
import json
import re

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_project.settings')
django.setup()

from django.core.mail import send_mail
from django.conf import settings
from invoices.models import Invoice, InvoiceEmailStatusLog

# Configuration
LOG_FILE = '/opt/billing_v2/tmp/email_status.log'
STATE_FILE = '/opt/billing_v2/tmp/.log_monitor_state.json'

# Only alert on ACTUAL errors (ERROR/CRITICAL level logs)
ERROR_LEVELS = ['ERROR', 'CRITICAL']
# Additional patterns to catch specific error scenarios
ERROR_PATTERNS = [
    r'Exception',
    r'Traceback',
    r'error sending',
    r'Failed.*[Tt]ask',
    r'FAILED',
]

ALERT_EMAIL = os.environ.get('ALERT_EMAIL', 'admin@peterretief.org')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'peter@peterretief.org')


class LogMonitor:
    def __init__(self):
        self.log_file = Path(LOG_FILE)
        self.state_file = Path(STATE_FILE)
        self.state = self.load_state()
        self.alerts = []
        self.summary = {
            'total_checked': 0,
            'errors_found': 0,
            'last_run': datetime.now().isoformat(),
        }

    def load_state(self):
        """Load previous state to track what we've already alerted on"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            'last_check': None,
            'last_error_line': 0,
            'alerted_errors': {},
            'last_daily_alert_sent': None,  # Track when last daily alert was sent
        }

    def save_state(self):
        """Save current state"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)

    def check_logs(self):
        """Check log files for errors"""
        print(f"[{datetime.now()}] Starting log check...")

        if not self.log_file.exists():
            print(f"Log file not found: {self.log_file}")
            return

        # Read new lines since last check
        last_line = self.state['last_error_line']
        with open(self.log_file, 'r') as f:
            lines = f.readlines()

        new_lines = lines[last_line:]
        self.summary['total_checked'] = len(new_lines)

        for i, line in enumerate(new_lines, start=last_line):
            is_error = False
            
            # Check for ERROR/CRITICAL log levels
            for level in ERROR_LEVELS:
                if level in line:
                    is_error = True
                    break
            
            # If not already flagged as error, check additional patterns
            if not is_error:
                for pattern in ERROR_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        is_error = True
                        break
            
            # Skip INFO/WARNING/DEBUG messages unless they're actual errors
            if is_error and not any(x in line for x in ['INFO', 'WARNING', 'DEBUG']):
                self.summary['errors_found'] += 1
                error_hash = hash(line)

                # Only alert if we haven't seen this exact error before
                if error_hash not in self.state['alerted_errors']:
                    self.alerts.append({
                        'line': i,
                        'content': line.strip(),
                        'timestamp': datetime.now().isoformat(),
                    })
                    self.state['alerted_errors'][error_hash] = datetime.now().isoformat()

        # Update state
        self.state['last_error_line'] = len(lines)
        self.state['last_check'] = datetime.now().isoformat()

        # Clean up old entries (keep only last 100)
        if len(self.state['alerted_errors']) > 100:
            sorted_errors = sorted(
                self.state['alerted_errors'].items(),
                key=lambda x: x[1],
                reverse=True,
            )
            self.state['alerted_errors'] = dict(sorted_errors[:100])

    def check_email_failures(self):
        """Check for email sending failures in database"""
        failed_logs = InvoiceEmailStatusLog.objects.filter(
            status__in=['error', 'failed', 'bounce'],
        ).order_by('-created_at')[:10]

        if failed_logs.exists():
            self.alerts.append({
                'type': 'EMAIL_FAILURE',
                'count': failed_logs.count(),
                'details': [str(log) for log in failed_logs],
                'timestamp': datetime.now().isoformat(),
            })
            self.summary['errors_found'] += failed_logs.count()

    def check_pending_invoices(self):
        """Check for invoices stuck in PENDING status"""
        from django.utils import timezone
        from datetime import timedelta

        stuck_invoices = Invoice.objects.filter(
            status='PENDING',
            emailed_at__lt=timezone.now() - timedelta(hours=24),
        )

        if stuck_invoices.exists():
            self.alerts.append({
                'type': 'STUCK_INVOICES',
                'count': stuck_invoices.count(),
                'details': [inv.number for inv in stuck_invoices[:5]],
                'timestamp': datetime.now().isoformat(),
            })

    def send_alert_email(self):
        """Send ONE alert email per day with accumulated errors"""
        if not self.alerts:
            return

        # Check if we've already sent an alert today
        today = datetime.now().date().isoformat()
        last_alert_date = self.state.get('last_daily_alert_sent')
        
        if last_alert_date == today:
            print(f"✓ Daily alert already sent today. Skipping. (Errors buffered: {self.summary['errors_found']})")
            return

        subject = f"DAILY ALERT: {self.summary['errors_found']} errors found in billing logs"
        
        alert_text = f"""
        LOG MONITORING - DAILY ALERT
        ============================
        
        Report Date: {datetime.now().strftime('%B %d, %Y')}
        Total Errors Found: {self.summary['errors_found']}
        Lines Scanned: {self.summary['total_checked']}
        
        ERRORS DETECTED:
        """

        for alert in self.alerts[:20]:  # Show first 20 errors only
            if isinstance(alert.get('content'), str):
                alert_text += f"\n  - {alert['content'][:100]}"
            else:
                alert_text += f"\n  - {alert['type']}: {alert.get('count', 'N/A')} issues"
                if alert.get('details'):
                    for detail in alert['details'][:3]:
                        alert_text += f"\n    • {detail[:80]}"

        if len(self.alerts) > 20:
            alert_text += f"\n\n  ... and {len(self.alerts) - 20} more errors"

        alert_text += """
        
        NOTE: This is ONE daily summary sent around this time each day.
        Check logs at: /opt/billing_v2/tmp/email_status.log
        Monitor Flower at: http://127.0.0.1:5555
        """

        try:
            send_mail(
                subject,
                alert_text,
                settings.DEFAULT_FROM_EMAIL,
                [ADMIN_EMAIL],
                fail_silently=False,
            )
            print(f"✓ Daily alert email sent to {ADMIN_EMAIL}")
            self.state['last_daily_alert_sent'] = today
            return True
        except Exception as e:
            print(f"✗ Failed to send alert email: {e}")
            return False

    def send_daily_summary(self):
        """Send daily summary report at midnight"""
        now = datetime.now()
        if now.hour != 0:  # Only send at midnight
            return

        from django.utils import timezone
        yesterday = timezone.now() - timedelta(days=1)

        # Get yesterday's stats
        emails_sent = InvoiceEmailStatusLog.objects.filter(
            created_at__gte=yesterday,
            status__in=['sent', 'delivered'],
        ).count()

        emails_failed = InvoiceEmailStatusLog.objects.filter(
            created_at__gte=yesterday,
            status__in=['error', 'failed', 'bounce'],
        ).count()

        invoices_created = Invoice.objects.filter(
            created_at__gte=yesterday,
        ).count()

        summary_text = f"""
        DAILY SUMMARY REPORT
        {yesterday.strftime('%B %d, %Y')}
        =====================
        
        Emails Sent: {emails_sent}
        Email Failures: {emails_failed}
        New Invoices: {invoices_created}
        
        Log Monitor Status: ✓ ACTIVE
        Last Check: {self.state['last_check']}
        State File: {self.state_file}
        """

        try:
            send_mail(
                f"Daily Billing Summary - {yesterday.strftime('%B %d')}",
                summary_text,
                settings.DEFAULT_FROM_EMAIL,
                [ADMIN_EMAIL],
                fail_silently=False,
            )
            print(f"✓ Daily summary sent to {ADMIN_EMAIL}")
        except Exception as e:
            print(f"✗ Failed to send daily summary: {e}")

    def run(self):
        """Execute full monitoring cycle"""
        try:
            self.check_logs()
            self.check_email_failures()
            self.check_pending_invoices()
            self.check_pending_invoices()

            # Send alerts if errors found
            if self.alerts:
                self.send_alert_email()

            # Send daily summary
            self.send_daily_summary()

            # Save state
            self.save_state()

            print(f"✓ Monitoring complete. Errors found: {self.summary['errors_found']}")
            return 0

        except Exception as e:
            print(f"✗ Monitoring failed: {e}")
            import traceback
            traceback.print_exc()
            return 1


if __name__ == '__main__':
    monitor = LogMonitor()
    sys.exit(monitor.run())
