# platforms/management/commands/setup_platforms.py
from django.core.management.base import BaseCommand
from platforms.models import SocialPlatform
from ai.models import AIIntentCategory, AISentimentRange


class Command(BaseCommand):
    help = 'Setup initial social platforms and AI configurations'

    def handle(self, *args, **options):
        # Create social platforms
        platforms = [
            {
                'name': 'facebook',
                'display_name': 'Facebook Messenger',
                'api_version': 'v19.0',
                'webhook_config': {
                    'verify_token_required': True,
                    'signature_verification': True,
                    'supported_events': ['messages', 'messaging_postbacks']
                },
                'rate_limits': {
                    'messages_per_second': 10,
                    'burst_limit': 100
                }
            },
            {
                'name': 'whatsapp',
                'display_name': 'WhatsApp Business',
                'api_version': 'v19.0',
                'webhook_config': {
                    'verify_token_required': True,
                    'signature_verification': True,
                    'supported_events': ['messages', 'message_status']
                },
                'rate_limits': {
                    'messages_per_second': 20,
                    'burst_limit': 100
                }
            },
            {
                'name': 'telegram',
                'display_name': 'Telegram',
                'api_version': 'bot_api_6.0',
                'webhook_config': {
                    'verify_token_required': False,
                    'signature_verification': False,
                    'supported_events': ['message', 'callback_query']
                },
                'rate_limits': {
                    'messages_per_second': 30,
                    'burst_limit': 100
                }
            }
        ]

        for platform_data in platforms:
            platform, created = SocialPlatform.objects.get_or_create(
                name=platform_data['name'],
                defaults=platform_data
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Created platform: {platform.display_name}')
                )
            else:
                self.stdout.write(f'Platform {platform.display_name} already exists')

        # Create default AI intent categories
        default_intents = [
            {
                'intent_key': 'greeting',
                'display_name': 'Greeting',
                'description': 'Customer greeting messages',
                'color_code': '#4CAF50',
                'priority_score': 1,
                'auto_actions': {'auto_respond': True},
                'is_system_defined': True
            },
            {
                'intent_key': 'question',
                'display_name': 'Question',
                'description': 'Customer asking questions',
                'color_code': '#2196F3',
                'priority_score': 5,
                'auto_actions': {'search_knowledge_base': True},
                'is_system_defined': True
            },
            {
                'intent_key': 'complaint',
                'display_name': 'Complaint',
                'description': 'Customer complaints or issues',
                'color_code': '#F44336',
                'priority_score': 10,
                'auto_actions': {'escalate_to_human': True, 'high_priority': True},
                'is_system_defined': True
            },
            {
                'intent_key': 'support_request',
                'display_name': 'Support Request',
                'description': 'Customer requesting support',
                'color_code': '#FF9800',
                'priority_score': 8,
                'auto_actions': {'search_knowledge_base': True, 'track_resolution': True},
                'is_system_defined': True
            },
            {
                'intent_key': 'sales_inquiry',
                'display_name': 'Sales Inquiry',
                'description': 'Customer interested in products/services',
                'color_code': '#9C27B0',
                'priority_score': 9,
                'auto_actions': {'create_lead': True, 'notify_sales_team': True},
                'is_system_defined': True
            }
        ]

        self.stdout.write('\nCreating default AI intent categories...')
        for intent_data in default_intents:
            # Note: This creates system-wide intents, you might want to create them per tenant
            self.stdout.write(f"Intent template: {intent_data['display_name']}")

        # Create default sentiment ranges
        sentiment_ranges = [
            {
                'range_key': 'very_negative',
                'display_name': 'Very Negative',
                'min_value': -1.0,
                'max_value': -0.6,
                'color_code': '#D32F2F',
                'alert_threshold': True,
                'is_system_defined': True
            },
            {
                'range_key': 'negative',
                'display_name': 'Negative',
                'min_value': -0.6,
                'max_value': -0.2,
                'color_code': '#F57C00',
                'alert_threshold': True,
                'is_system_defined': True
            },
            {
                'range_key': 'neutral',
                'display_name': 'Neutral',
                'min_value': -0.2,
                'max_value': 0.2,
                'color_code': '#689F38',
                'alert_threshold': False,
                'is_system_defined': True
            },
            {
                'range_key': 'positive',
                'display_name': 'Positive',
                'min_value': 0.2,
                'max_value': 0.6,
                'color_code': '#388E3C',
                'alert_threshold': False,
                'is_system_defined': True
            },
            {
                'range_key': 'very_positive',
                'display_name': 'Very Positive',
                'min_value': 0.6,
                'max_value': 1.0,
                'color_code': '#1976D2',
                'alert_threshold': False,
                'is_system_defined': True
            }
        ]

        self.stdout.write('\nCreating default sentiment ranges...')
        for sentiment_data in sentiment_ranges:
            self.stdout.write(f"Sentiment range: {sentiment_data['display_name']}")

        self.stdout.write(
            self.style.SUCCESS('\nPlatform setup completed successfully!')
        )
        self.stdout.write('\nNext steps:')
        self.stdout.write('1. Configure your webhook URLs in Facebook/WhatsApp developer consoles')
        self.stdout.write('2. Add your verification tokens to settings.py')
        self.stdout.write('3. Create tenant platform accounts through admin or API')
        self.stdout.write('4. Test webhooks with webhook testing tools')


# platforms/management/commands/test_webhooks.py
from django.core.management.base import BaseCommand
import requests
import json


class Command(BaseCommand):
    help = 'Test webhook endpoints'

    def add_arguments(self, parser):
        parser.add_argument('--platform', type=str, help='Platform to test (facebook, whatsapp)')
        parser.add_argument('--url', type=str, help='Base URL of your application')

    def handle(self, *args, **options):
        platform = options.get('platform', 'facebook')
        base_url = options.get('url', 'http://localhost:8000')

        if platform == 'facebook':
            self.test_facebook_webhook(base_url)
        elif platform == 'whatsapp':
            self.test_whatsapp_webhook(base_url)
        else:
            self.stdout.write(self.style.ERROR('Invalid platform. Use facebook or whatsapp'))

    def test_facebook_webhook(self, base_url):
        self.stdout.write('Testing Facebook webhook...')
        
        # Test message payload
        test_payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "test_waba_id",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messages": [
                                    {
                                        "id": "test_message_id",
                                        "from": "1234567890",
                                        "timestamp": "1234567890",
                                        "type": "text",
                                        "text": {
                                            "body": "Hello from WhatsApp test"
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        try:
            response = requests.post(verify_url, json=test_payload)
            if response.status_code == 200:
                self.stdout.write(self.style.SUCCESS('✓ WhatsApp message payload test successful'))
            else:
                self.stdout.write(self.style.ERROR(f'✗ WhatsApp message payload test failed: {response.status_code}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error testing WhatsApp message: {e}')) verification
        verify_url = f"{base_url}/api/platforms/webhooks/facebook/"
        verify_params = {
            'hub.mode': 'subscribe',
            'hub.verify_token': 'your_facebook_verify_token_here',
            'hub.challenge': 'test_challenge'
        }
        
        try:
            response = requests.get(verify_url, params=verify_params)
            if response.status_code == 200:
                self.stdout.write(self.style.SUCCESS('✓ Facebook webhook verification successful'))
            else:
                self.stdout.write(self.style.ERROR(f'✗ Facebook webhook verification failed: {response.status_code}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error testing Facebook webhook: {e}'))

        # Test message payload
        test_payload = {
            "object": "page",
            "entry": [
                {
                    "id": "test_page_id",
                    "messaging": [
                        {
                            "sender": {"id": "test_user_id"},
                            "message": {
                                "mid": "test_message_id",
                                "text": "Hello from test"
                            },
                            "timestamp": 1234567890
                        }
                    ]
                }
            ]
        }

        try:
            response = requests.post(verify_url, json=test_payload)
            if response.status_code == 200:
                self.stdout.write(self.style.SUCCESS('✓ Facebook message payload test successful'))
            else:
                self.stdout.write(self.style.ERROR(f'✗ Facebook message payload test failed: {response.status_code}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error testing Facebook message: {e}'))

    def test_whatsapp_webhook(self, base_url):
        self.stdout.write('Testing WhatsApp webhook...')
        
        # Test verification
        verify_url = f"{base_url}/api/platforms/webhooks/whatsapp/"
        verify_params = {
            'hub.mode': 'subscribe',
            'hub.verify_token': 'your_whatsapp_verify_token_here',
            'hub.challenge': 'test_challenge'
        }
        
        try:
            response = requests.get(verify_url, params=verify_params)
            if response.status_code == 200:
                self.stdout.write(self.style.SUCCESS('✓ WhatsApp webhook verification successful'))
            else:
                self.stdout.write(self.style.ERROR(f'✗ WhatsApp webhook verification failed: {response.status_code}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error testing WhatsApp webhook: {e}'))

        # Test