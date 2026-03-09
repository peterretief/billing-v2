# Automated Log Monitoring System

## Overview
The monitoring system automatically checks logs every **10 minutes** for errors and failures, sends **immediate alerts** when problems are found, and generates **daily summaries**.

## Components

### 1. Main Script: `/opt/billing_v2/log_monitor.py`
- Parses email_status.log for errors
- Checks database for email failures
- Identifies stuck invoices
- Sends emails when issues found
- Maintains state to avoid duplicate alerts

### 2. Django Management Command
```bash
python manage.py monitor_logs
```

### 3. Automated Scheduling
**Cron job runs every 10 minutes:**
```
*/10 * * * * cd /opt/billing_v2 && /opt/billing_v2/venv/bin/python log_monitor.py
```

## What Gets Monitored

### Error Detection
- ERROR, CRITICAL, Exception, Failed patterns in logs
- Email delivery failures in database
- Invoices stuck in PENDING status for > 24 hours

### Alerts Sent To
- Default: `peter@peterretief.org`
- Configure via: `ADMIN_EMAIL` environment variable

## Log Files

**Monitoring output:**
- `/opt/billing_v2/tmp/log_monitor_cron.log` - Cron execution log
- `/opt/billing_v2/tmp/.log_monitor_state.json` - State tracking (prevents duplicate alerts)

**Original logs monitored:**
- `/opt/billing_v2/tmp/email_status.log` - All email/task logs

## Daily Summary

Automatically sent at **midnight** containing:
- Emails sent yesterday
- Email failures yesterday  
- New invoices created
- Monitoring system status

## Manual Run

Test monitoring immediately:
```bash
cd /opt/billing_v2
/opt/billing_v2/venv/bin/python log_monitor.py
```

## View Recent Alerts

```bash
# See cron execution history
tail -f /opt/billing_v2/tmp/log_monitor_cron.log

# See last 50 log entries checked
tail /opt/billing_v2/tmp/email_status.log

# Check alert state (prevents duplicate alerts)
cat /opt/billing_v2/tmp/.log_monitor_state.json
```

## Disable/Enable

**Disable monitoring:**
```bash
crontab -e
# Comment out or delete the */10 line
```

**Re-enable monitoring:**
```bash
(crontab -l 2>/dev/null | grep -v log_monitor; echo "*/10 * * * * cd /opt/billing_v2 && /opt/billing_v2/venv/bin/python log_monitor.py >> /opt/billing_v2/tmp/log_monitor_cron.log 2>&1") | crontab -
```

## Environment Variables

Edit `/opt/billing_v2/.env`:
```
ADMIN_EMAIL=your-email@example.com
ALERT_EMAIL=alerts@example.com
```

## How It Works

1. **Every 10 minutes** cron triggers the script
2. **Log parsing** - Scans new lines since last check
3. **Error detection** - Looks for known error patterns
4. **State tracking** - Remembers what's been alerted (hash-based)
5. **Email alert** - If new errors found, sends email with details
6. **Daily summary** - At midnight, sends comprehensive report

## Preventing Alert Fatigue

- Only alerts on **NEW errors** (uses hash-based state tracking)
- Keeps state file to avoid duplicate alerts for same error
- Automatically cleans up state (keeps last 100 errors)
- Can review failed alerts without re-alerting

## Example Alert

```
Subject: ALERT: 5 errors found in billing logs

LOG MONITORING ALERT
===================

Check Time: 2026-03-04 13:50:00
Lines Checked: 245
Errors Found: 5

ERRORS:
  - ERROR: Email delivery failed for invoice ABC-123
  - Exception: Celery task timeout on send_invoice_async
  - ...

Check logs at: /opt/billing_v2/tmp/email_status.log
Monitor Flower at: http://127.0.0.1:5555
```

## Troubleshooting

**Not receiving emails?**
- Check: `/opt/billing_v2/tmp/log_monitor_cron.log`
- Verify SMTP settings in Django settings
- Test manually: `/opt/billing_v2/venv/bin/python log_monitor.py`

**Too many alerts?**
- This is expected on first run as it processes old logs
- Subsequent runs will only alert on NEW errors
- Check state file: `cat /opt/billing_v2/tmp/.log_monitor_state.json`

**Want to modify alert rules?**
- Edit `/opt/billing_v2/log_monitor.py`
- Change `ERROR_PATTERNS` list to customize what triggers alerts
- Restart cron: `crontab -e`
