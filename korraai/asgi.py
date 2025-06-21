# korraai/asgi.py
import os
import django
from django.core.asgi import get_asgi_application

# Setup Django first
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'korraai.settings')
django.setup()

# Now import channels
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Import routing after Django is setup
from conversations import routing

# Create the application
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(routing.websocket_urlpatterns)
    ),
})

print("ASGI application loaded successfully")
print(f"WebSocket routes: {routing.websocket_urlpatterns}")