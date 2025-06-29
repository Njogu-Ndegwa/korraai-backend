from django.apps import AppConfig


class ConversationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'conversations'

    def ready(self):
        import conversations.signals  # Import signals when app is ready
