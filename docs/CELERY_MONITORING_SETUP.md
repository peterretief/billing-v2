# Celery Monitoring Cron Jobs
# 
# Add these to your crontab to continuously monitor Celery health:
#
# sudo crontab -e
# Then add:

# Daily health check at 8 AM (verify billing queue ran the night before)
0 8 * * * cd /opt/billing_v2 && source venv/bin/activate && python manage.py check_celery_health --hours=25 --alert >> /var/log/celery/health_check.log 2>&1

# Hourly task count verification (early warning system)
0 * * * * cd /opt/billing_v2 && python scripts/check_celery_app_configs.py >> /var/log/celery/app_config_check.log 2>&1

# Daily app config lint check (prevent regression)
0 6 * * * cd /opt/billing_v2 && python scripts/check_celery_app_configs.py >> /var/log/celery/lint_check.log 2>&1


# Alternative: Using systemd timers instead of cron
#
# Create /etc/systemd/system/celery-health-check.service:
#
# [Unit]
# Description=Celery Health Check
# After=network.target
# 
# [Service]
# Type=oneshot
# WorkingDirectory=/opt/billing_v2
# ExecStart=/bin/bash -c 'source venv/bin/activate && python manage.py check_celery_health --hours=25 --alert'
# StandardOutput=journal
# StandardError=journal
#
# [Install]
# WantedBy=multi-user.target


# Then create /etc/systemd/system/celery-health-check.timer:
#
# [Unit]
# Description=Run Celery Health Check Daily
# 
# [Timer]
# OnCalendar=daily
# OnCalendar=*-*-* 08:00:00
# OnBootSec=5min
# 
# [Install]
# WantedBy=timers.target
#
# Enable with: sudo systemctl enable --now celery-health-check.timer
