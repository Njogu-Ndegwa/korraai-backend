# routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/qa/(?P<conversation_id>[0-9a-f-]+)/$', consumers.QAWebSocket.as_asgi()),
]
