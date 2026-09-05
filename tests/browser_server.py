"""Local browser fixtures. Never loads .env or contacts deployed services."""
from unittest.mock import Mock
from flask import abort
from tests.support import isolated_app

application = isolated_app()
application.ENABLE_DEMO_DATA = True
application.PUBLIC_SITE_URL = 'http://127.0.0.1:5099'
application.SUPABASE_URL = 'https://auth.example.test'
application.SUPABASE_ANON_KEY = 'public-test-key'
application.GOOGLE_AUTH_ENABLED = True
application.app.config.update(
    CONTACT_EMAIL_ENABLED=True, CONTACT_EMAIL='support@example.test',
    CONTACT_SMTP_FROM='support@example.test', CONTACT_SMTP_HOST='smtp.example.test',
    CONTACT_SMTP_PORT=587, CONTACT_SMTP_USERNAME='', CONTACT_SMTP_PASSWORD='',
    CONTACT_SMTP_USE_TLS=True, CONTACT_SMTP_USE_SSL=False,
    TELEGRAM_URL='https://t.me/test_fixture', DISCORD_URL='https://discord.gg/test_fixture',
)
application.redis_cache = Mock()
application.redis_cache.get.return_value = None
application.redis_cache.set.return_value = True
import contact
contact.deliver_message = Mock()

@application.app.get('/__test/error/<int:code>')
def fixture_error(code):
    abort(code)

if __name__ == '__main__':
    application.app.run(host='127.0.0.1', port=5099, debug=False, use_reloader=False)
