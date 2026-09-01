import os

os.environ.update({
    "APP_ENV": "test",
    "SECRET_KEY": "isolated-tests-not-a-production-secret",
    "SUPABASE_URL": "",
    "SUPABASE_ANON_KEY": "",
    "SUPABASE_SERVICE_KEY": "",
    "SUPABASE_KEY": "",
    "ADMIN_EMAILS": "",
    "ADMIN_EMAIL": "",
    "R2_ACCOUNT_ID": "",
    "R2_ACCESS_KEY_ID": "",
    "R2_SECRET_ACCESS_KEY": "",
    "R2_PUBLIC_DOMAIN": "",
    "RATE_LIMIT_STORAGE_URI": "memory://",
    "ENABLE_DEMO_DATA": "false",
    "FLASK_DEBUG": "false",
    "TRUST_PROXY_HOPS": "0",
    "PUBLIC_SITE_URL": "http://localhost:5000",
})
