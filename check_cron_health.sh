#!/bin/bash
# Diagnostic script to verify cron job setup isn't broken

echo "=== CRON JOB HEALTH CHECK ==="
echo ""

# 1. Check if cron job exists
echo "1. Checking if monitoring is in crontab..."
CRON_ENTRY=$(crontab -l 2>/dev/null | grep "log_monitor.py" | wc -l)
if [ $CRON_ENTRY -eq 0 ]; then
    echo "   ✗ ERROR: log_monitor.py not found in crontab!"
    echo "   Run: (crontab -l 2>/dev/null; echo '*/10 * * * * cd /opt/billing_v2 && /opt/billing_v2/venv/bin/python log_monitor.py >> /opt/billing_v2/tmp/log_monitor_cron.log 2>&1') | crontab -"
    exit 1
else
    echo "   ✓ Found in crontab"
    crontab -l | grep "log_monitor"
fi
echo ""

# 2. Check file permissions
echo "2. Checking file permissions..."
if [ ! -w /opt/billing_v2/tmp/ ]; then
    echo "   ✗ ERROR: Cannot write to /opt/billing_v2/tmp/"
    exit 1
else
    echo "   ✓ /opt/billing_v2/tmp/ is writable"
fi

if [ ! -r /opt/billing_v2/log_monitor.py ]; then
    echo "   ✗ ERROR: Cannot read /opt/billing_v2/log_monitor.py"
    exit 1
else
    echo "   ✓ /opt/billing_v2/log_monitor.py is readable"
fi
echo ""

# 3. Check Python venv
echo "3. Checking Python environment..."
if [ ! -f /opt/billing_v2/venv/bin/python ]; then
    echo "   ✗ ERROR: Python venv not found at /opt/billing_v2/venv/bin/python"
    exit 1
else
    echo "   ✓ Python venv exists"
    /opt/billing_v2/venv/bin/python --version
fi
echo ""

# 4. Check recent cron execution
echo "4. Checking recent cron execution..."
LAST_RUN=$(tail -1 /opt/billing_v2/tmp/log_monitor_cron.log | grep -oP '\d{4}-\d{2}-\d{2}' | tail -1)
CURRENT_DATE=$(date +%Y-%m-%d)

if [ "$LAST_RUN" != "$CURRENT_DATE" ]; then
    echo "   ⚠ WARNING: Last cron run was on $LAST_RUN (today is $CURRENT_DATE)"
    echo "   The job may not have run today"
else
    echo "   ✓ Cron ran today"
    tail -1 /opt/billing_v2/tmp/log_monitor_cron.log
fi
echo ""

# 5. Check state file
echo "5. Checking state file..."
if [ ! -f /opt/billing_v2/tmp/.log_monitor_state.json ]; then
    echo "   ⚠ WARNING: State file doesn't exist yet (will be created on first run)"
else
    echo "   ✓ State file exists"
    echo "   Last alert sent: $(grep 'last_daily_alert_sent' /opt/billing_v2/tmp/.log_monitor_state.json)"
fi
echo ""

# 6. Check log file exists
echo "6. Checking email status log..."
if [ ! -f /opt/billing_v2/tmp/email_status.log ]; then
    echo "   ⚠ WARNING: /opt/billing_v2/tmp/email_status.log doesn't exist"
else
    LOG_SIZE=$(wc -l < /opt/billing_v2/tmp/email_status.log)
    echo "   ✓ Log file exists ($LOG_SIZE lines)"
fi
echo ""

echo "=== HEALTH CHECK COMPLETE ==="
echo ""
echo "If all checks passed, cron monitoring is working correctly!"
echo "If any failed, fix the issue and re-run this script."
