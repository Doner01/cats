import os

bind = f"0.0.0.0:{int(os.getenv('PORT', '8000'))}"
workers = int(os.getenv('WEB_CONCURRENCY', '1'))
threads = int(os.getenv('GUNICORN_THREADS', '4'))
timeout = 60
graceful_timeout = 30
accesslog = '-'
errorlog = '-'
max_requests = 1000
max_requests_jitter = 100
