#!/bin/bash
# 
# cleanup_tmp_files_cron.sh - Monthly cleanup of temporary report files
# 
# Setup:
#   chmod +x /opt/billing_v2/cleanup_tmp_files_cron.sh
#   crontab -e
#   
# Add this line to run monthly (1st day of month at 2 AM):
#   0 2 1 * * /opt/billing_v2/cleanup_tmp_files_cron.sh
#
# Or weekly (every Sunday at 2 AM):
#   0 2 * * 0 /opt/billing_v2/cleanup_tmp_files_cron.sh
#

cd /opt/billing_v2

# Activate virtual environment
source venv/bin/activate

# Run the cleanup command
python manage.py cleanup_tmp_files --days-old 7 >> tmp/cleanup.log 2>&1

# Log rotation (keep only last 12 cleanup logs)
CLEANUP_LOG="tmp/cleanup.log"
if [ -f "$CLEANUP_LOG" ]; then
    LOG_SIZE=$(wc -l < "$CLEANUP_LOG")
    if [ $LOG_SIZE -gt 10000 ]; then
        tail -5000 "$CLEANUP_LOG" > "$CLEANUP_LOG.tmp"
        mv "$CLEANUP_LOG.tmp" "$CLEANUP_LOG"
    fi
fi

echo "Cleanup completed at $(date)" >> tmp/cleanup.log
