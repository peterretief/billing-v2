"""
WebSocket URL routing for events.
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/events/sync/$", consumers.EventSyncConsumer.as_asgi()),
]
