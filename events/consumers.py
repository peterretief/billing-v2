"""
WebSocket consumer for real-time event sync notifications.
"""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


class EventSyncConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer that sends real-time notifications when calendar events are synced.
    
    Clients connect and join a user-specific group to receive sync updates.
    """
    
    async def connect(self):
        """Accept WebSocket connection and add to user's group."""
        self.user = self.scope["user"]
        
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Create user-specific group name
        self.group_name = f"user_sync_{self.user.id}"
        
        # Add this connection to the group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"WebSocket connected for user {self.user.username}")
    
    async def disconnect(self, close_code):
        """Remove from group when disconnecting."""
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        logger.info(f"WebSocket disconnected for user {self.user.username}")
    
    async def sync_update(self, event):
        """
        Handle sync_update events sent from the group.
        Sends notification to the WebSocket client.
        """
        message = event.get('message', {})
        
        await self.send(text_data=json.dumps({
            'type': 'sync_update',
            'events': message.get('events', []),
            'timestamp': message.get('timestamp'),
            'success_count': message.get('synced_count', 0),
            'error_count': message.get('failed_count', 0),
        }))
        
        logger.debug(f"Sent sync update to {self.user.username}: {message.get('synced_count', 0)} events synced")
