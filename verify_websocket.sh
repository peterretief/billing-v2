#!/bin/bash
# WebSocket Real-Time Sync - Verification Script
# This script verifies that all WebSocket components are properly set up

set -e

echo "=================================="
echo "WebSocket Real-Time Sync Verification"
echo "=================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_component() {
    local name="$1"
    local command="$2"
    
    echo -n "Checking $name... "
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${NC}"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        return 1
    fi
}

# 1. Check Python packages
echo "1. Python Packages"
echo "---"
check_component "Django Channels" "python -c 'import channels; print(channels.__version__)'"
check_component "Channels-Redis" "python -c 'import channels_redis'"
check_component "Daphne" "python -c 'import daphne'"
echo ""

# 2. Check Django Settings
echo "2. Django Configuration"
echo "---"
echo -n "Checking INSTALLED_APPS... "
if grep -q "'channels'" core_project/settings.py && grep -q "'daphne'" core_project/settings.py; then
    echo -e "${GREEN}✓ OK${NC}"
else
    echo -e "${RED}✗ Missing${NC}"
fi

echo -n "Checking CHANNEL_LAYERS... "
if grep -q "CHANNEL_LAYERS" core_project/settings.py; then
    echo -e "${GREEN}✓ OK${NC}"
else
    echo -e "${RED}✗ Missing${NC}"
fi
echo ""

# 3. Check Core Project Files
echo "3. Core Project Files"
echo "---"
check_component "ASGI configured" "grep -q 'ProtocolTypeRouter' core_project/asgi.py"
check_component "Events routing" "test -f events/routing.py"
check_component "Events consumer" "test -f events/consumers.py"
echo ""

# 4. Check Frontend Files
echo "4. Frontend Static Files"
echo "---"
check_component "WebSocket JS" "test -f events/static/events/websocket_sync.js"
check_component "WebSocket CSS" "test -f events/static/events/websocket_sync.css"
echo ""

# 5. Check Runtime Services
echo "5. Runtime Services"
echo "---"
echo -n "Checking Redis... "
if redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not Running${NC}"
fi

echo -n "Checking Daphne... "
if sudo supervisorctl status billing_v2_daphne 2>/dev/null | grep -q "RUNNING"; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${YELLOW}⚠ Check manually${NC}"
fi

echo -n "Checking Celery Worker... "
if sudo supervisorctl status celery_worker 2>/dev/null | grep -q "RUNNING"; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${YELLOW}⚠ Check manually${NC}"
fi

echo -n "Checking Celery Beat... "
if sudo supervisorctl status celery_beat 2>/dev/null | grep -q "RUNNING"; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${YELLOW}⚠ Check manually${NC}"
fi
echo ""

# 6. Check HTTP Connectivity
echo "6. HTTP Connectivity"
echo "---"
echo -n "Testing Daphne HTTP... "
if curl -s http://127.0.0.1:8001/invoices/ -w "%{http_code}" -o /dev/null | grep -qE "(200|301|302|401)"; then
    echo -e "${GREEN}✓ Responding${NC}"
else
    echo -e "${RED}✗ Not responding${NC}"
fi
echo ""

# 7. Summary
echo "7. Summary"
echo "---"
echo "WebSocket Endpoint: ws://localhost:8001/ws/events/sync/"
echo "HTTP Endpoint: http://localhost:8001/"
echo "Flower Dashboard: http://localhost:5555"
echo ""
echo "Testing Steps:"
echo "1. Open http://localhost:8001/events/ in browser"
echo "2. Open Developer Tools (F12) → Console"
echo "3. Look for '[WebSocket] Connected successfully' message"
echo "4. Manually trigger sync: python manage.py shell"
echo "5. Watch for real-time notification in browser"
echo ""

echo -e "${GREEN}Verification complete!${NC}"
echo ""
