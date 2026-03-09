# WebSocket Real-Time Sync Implementation

## Overview

The billing application now includes real-time WebSocket support for automatic event updates when syncing with Google Calendar. When Celery tasks complete a sync, connected clients receive instant notifications and updates without needing manual page refresh.

## Architecture

### Components Installed

1. **Django Channels 4.3.2** - WebSocket support for Django
2. **Channels-Redis 4.3.0** - Redis channel layer for cross-process communication
3. **Daphne 4.2.1** - ASGI server supporting WebSocket (replaced Gunicorn)

### Technology Stack

- **Transport**: Redis (already in use for Celery)
- **Protocol**: WebSocket (ws:// or wss:// for HTTPS)
- **Authentication**: Django user authentication via session
- **Message Format**: JSON

## Configuration Files

### 1. core_project/settings.py

**Added:**
- `"daphne"` to INSTALLED_APPS (first, before Django apps)
- `"channels"` to INSTALLED_APPS (for WebSocket support)

**Channel Layers Configuration:**
```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(REDIS_HOST, int(REDIS_PORT))],
        },
    },
}
```

### 2. core_project/asgi.py

**Updated from WSGI to ASGI:**
- Routes HTTP requests to Django ASGI app
- Routes WebSocket connections to Channels consumer
- Includes authentication middleware
- Origin validation for security

```python
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
    ),
})
```

### 3. events/routing.py

**Created WebSocket URL routing:**
```python
websocket_urlpatterns = [
    path("ws/events/sync/", EventSyncConsumer.as_asgi()),
]
```

### 4. events/consumers.py

**Created WebSocket consumer:**
- Handles client connections/disconnections
- Manages user-specific groups (user_sync_{user_id})
- Receives sync notifications from Celery tasks
- Sends updates to connected clients

### 5. events/tasks.py

**Updated Celery tasks:**
- After sync completes, sends WebSocket message via channel layer
- Includes synced event data, timestamp, and counts
- Graceful fallback if Channels unavailable

### 6. /etc/supervisor/conf.d/billing_v2.conf

**Replaced Gunicorn with Daphne:**
```ini
[program:billing_v2_daphne]
command=/opt/billing_v2/venv/bin/daphne -b 127.0.0.1 -p 8001 core_project.asgi:application
```

## Frontend Implementation

### JavaScript Client: events/static/events/websocket_sync.js

**Features:**
- Auto-connects to WebSocket endpoint on page load
- Automatic reconnection with exponential backoff (max 5 attempts)
- Graceful error handling
- Custom event dispatch for other scripts to listen to
- Debug logging to browser console

**Core Functions:**
- `init()` - Initialize WebSocket connection
- `onOpen()` - Handle successful connection
- `onMessage()` - Parse incoming messages
- `handleSyncUpdate()` - Process sync events
- `updateEventInDOM()` - Refresh event display
- `showNotification()` - Display user feedback

### CSS Styling: events/static/events/websocket_sync.css

**Includes:**
- Notification container styles (success/warning/error/info)
- Mobile responsive design
- Visual highlight for updated events

### Template Integration

**event_list.html:**
- Added `id="sync-notification"` div for notifications
- Added `data-event-id="{{ event.id }}"` to event cards
- Added `data-field="title"` attributes to updateable fields
- Loads WebSocket script for authenticated users

**event_detail.html:**
- Added notification container
- Added `data-event-id="{{ event.id }}"` to main card
- Loads WebSocket script for authenticated users

## How It Works

### 1. Initial Connection
```
User loads /events/ → Page loads for authenticated user → 
JavaScript loads → WebSocket connects to ws://host/ws/events/sync/
```

### 2. Sync Trigger
```
Celery Beat triggers sync task (every 5 minutes) →
Task syncs calendar changes to/from Google →
Task sends WebSocket message to user's group
```

### 3. Real-Time Update
```
WebSocket consumer receives message →
Consumer forwards to user's group →
Connected JavaScript client receives message →
DOM updates automatically with new event data →
User sees "✓ Synced 3 events" notification
```

### 4. Reconnection
```
WebSocket connection drops →
JavaScript attempts reconnect →
Exponential backoff: 3s, 4.5s, 6.75s, 10.1s, ...
Shows warning notification if reconnection fails
```

## Testing

### 1. Verify Components Running

```bash
# Check Daphne is running
sudo supervisorctl status billing_v2_daphne
# Should show: billing_v2_daphne  RUNNING  pid XXX, uptime ...

# Check Celery worker
sudo supervisorctl status celery_worker
# Should show: celery_worker  RUNNING  pid XXX, uptime ...

# Check Celery beat
sudo supervisorctl status celery_beat
# Should show: celery_beat  RUNNING  pid XXX, uptime ...
```

### 2. Manual Sync Test

```bash
cd /opt/billing_v2
source venv/bin/activate

# Open Django shell
python manage.py shell

# Trigger sync for your user
from core.models import User
from events.tasks import sync_user_events_with_calendar
user = User.objects.first()
sync_user_events_with_calendar.delay(user.id)

# In browser, open events page and watch for notification
```

### 3. Browser Testing

1. Open browser Developer Tools (F12)
2. Go to Console tab
3. Load `/events/` page
4. Watch console for logs starting with `[WebSocket]`
5. Expected output:
   ```
   [WebSocket] Attempting to connect to: ws://localhost:8001/ws/events/sync/
   [WebSocket] Connected successfully
   [WebSocket] Received message: {type: 'sync_update', ...}
   [Sync Update] 2 events synced, 0 errors
   ```

### 4. Monitor Flower

```
Open http://localhost:5555 in browser
Watch tasks complete in real-time
Click on tasks to see details
```

## Debugging

### Check WebSocket Connection

**Browser Console:**
```javascript
// Check if WebSocket listener is loaded
console.log(window.WebSocketSyncListener);

// Manually trigger reconnect
window.WebSocketSyncListener.init();

// Check connection state
console.log(window.WebSocketSyncListener.ws?.readyState);
// 0 = CONNECTING, 1 = OPEN, 2 = CLOSING, 3 = CLOSED
```

### Check Redis Channel Layer

```bash
# In Django shell
from channels.layers import get_channel_layer
import asyncio

channel_layer = get_channel_layer()
await channel_layer.group_send(
    f"user_sync_1",
    {"type": "sync_update", "events": [], "timestamp": "2024-01-01T00:00:00Z"}
)
```

### Check Server Logs

```bash
# Daphne logs
tail -f /var/log/billing_v2.out.log | grep -i "websocket\|daphne"

# Celery logs (if running in terminal)
tail -f /var/log/celery.log | grep "sync_user_events"
```

## Troubleshooting

### Issue: WebSocket Connection Fails

**Symptoms:**
- "[WebSocket] Error occurred" in console
- Page shows warning notification

**Solutions:**
1. Verify Daphne is running: `sudo supervisorctl status billing_v2_daphne`
2. Check server is accessible: `curl http://localhost:8001/invoices/`
3. Check Redis is running: `redis-cli ping` → should respond `PONG`
4. Check firewall doesn't block WebSocket: `sudo ufw status`

### Issue: No Real-Time Updates After Sync

**Symptoms:**
- Events sync completes but no notification
- Manual page refresh shows new data

**Solutions:**
1. Check Celery tasks in Flower: http://localhost:5555
2. Verify sync task completed successfully (green checkmark)
3. Check browser console for WebSocket errors
4. Verify database has new sync logs: `python manage.py shell` → `from events.models import EventSyncLog; EventSyncLog.objects.latest('created_at')`

### Issue: Redis Connection Error

**Symptoms:**
- Console shows "ConnectionRefusedError" for Redis
- Settings error about channel layer

**Solutions:**
1. Start Redis: `sudo service redis-server start`
2. Check Redis is listening: `redis-cli ping`
3. Verify Redis port in settings matches: `REDIS_PORT = "6379"`

### Issue: WebSocket Reconnects Repeatedly

**Symptoms:**
- "[Reconnect] Attempt X/5" messages in console
- Connection drops and reconnects frequently

**Solutions:**
1. Check if Daphne is crashing: `sudo supervisorctl tail billing_v2_daphne stderr`
2. Check server error logs: `tail -f /var/log/billing_v2.err.log`
3. Restart Daphne: `sudo supervisorctl restart billing_v2_daphne`

## Performance Considerations

### Message Frequency
- Sync tasks run every 5 minutes (configurable via Celery Beat)
- Each sync sends one WebSocket message per user
- Minimal bandwidth: JSON with event IDs, times, statuses

### Scalability
- Redis channel layer handles cross-process communication
- Scales horizontally with multiple Daphne workers
- WebSocket connections are long-lived but lightweight

### Resource Usage
- Each connected client uses ~100KB memory
- Redis stores group membership data only
- CPU usage negligible outside of sync operations

## Deployment Notes

### Production Considerations

1. **HTTPS/WSS:** Replace `ws://` with `wss://` in production
   ```python
   # In settings.py (for Nginx proxy)
   if not DEBUG:
       ALLOWED_HOSTS = ["yourdomain.com"]
       CSRF_TRUSTED_ORIGINS = ["https://yourdomain.com"]
   ```

2. **Multiple Daphne Workers:**
   ```ini
   [program:billing_v2_daphne]
   command=/opt/billing_v2/venv/bin/daphne -b 0.0.0.0 -p 8001 core_project.asgi:application
   numprocs=3
   process_name=%(program_name)s-%(process_num)d
   ```

3. **Nginx Proxy (for WebSocket):**
   ```nginx
   location / {
       proxy_pass http://127.0.0.1:8001;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
       proxy_set_header X-Forwarded-Proto $scheme;
   }
   ```

### Testing After Deployment

```bash
# Full integration test
1. Connect to events page
2. Check browser console for [WebSocket] Connected message
3. Manually trigger sync in Django shell
4. Verify real-time notification appears
5. Verify event list updates without page refresh
```

## Future Enhancements

1. **WebSocket Compression** - Reduce bandwidth with gzip
2. **Message Queue** - Batch updates if client offline
3. **Presence Tracking** - Show which users are viewing events
4. **Live Collaboration** - Multiple users editing same event
5. **Custom Alerts** - Different notifications for different event types

## References

- [Django Channels Documentation](https://channels.readthedocs.io/)
- [Channels-Redis Documentation](https://channels-redis.readthedocs.io/)
- [Daphne Documentation](https://github.com/django/daphne)
- [WebSocket API Reference](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)

---

**Last Updated:** 2024-03-08  
**Status:** ✅ Production Ready
