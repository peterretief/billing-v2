#!/bin/bash

echo "🔄 Restarting Billing System Services..."

# 1. Kill existing processes (Using -9 to ensure they actually die)
echo "Stopping old services..."
pkill -9 -f "manage.py runserver"
pkill -9 -f "celery -A core_project"

# Wait a second for ports to clear
sleep 2

# 2. Start Django Server
echo "🚀 Starting Django Server on port 8003..."
nohup python manage.py runserver 0:8003 > django.log 2>&1 & 

# 3. Start Celery Worker with a UNIQUE name
echo "👷 Starting Celery Worker..."
# The '-n worker1@%h' ensures a unique node name
celery -A core_project worker -l info -n worker1@%h --detach

# 4. Start Celery Beat
echo "⏰ Starting Celery Beat..."
celery -A core_project beat -l info --detach

echo "✅ All services are running in the background."