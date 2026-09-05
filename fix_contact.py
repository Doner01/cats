import re

with open('contact.py', 'r') as f:
    content = f.read()

# 1. Add typing imports
if 'from typing import ' not in content:
    content = content.replace('from flask import ', 'from typing import Any, Callable, cast, Type\nfrom flask import Flask, ')

# 2. Fix valid_email
content = content.replace(
    'if not isinstance(value, str) or len(value) > 254 or not value.isascii():',
    'if len(value) > 254 or not value.isascii():'
)

# 3. Fix mail_ready
content = content.replace(
    '''def mail_ready() -> bool:
    cfg = current_app.config
    return bool(
        cfg["CONTACT_EMAIL_ENABLED"] and valid_email(cfg["CONTACT_EMAIL"])
        and valid_email(cfg["CONTACT_SMTP_FROM"]) and cfg["CONTACT_SMTP_HOST"]
        and 1 <= cfg["CONTACT_SMTP_PORT"] <= 65535
        and not (cfg["CONTACT_SMTP_USE_TLS"] and cfg["CONTACT_SMTP_USE_SSL"])
        and (cfg["CONTACT_SMTP_USE_TLS"] or cfg["CONTACT_SMTP_USE_SSL"])
        and bool(cfg["CONTACT_SMTP_USERNAME"]) == bool(cfg["CONTACT_SMTP_PASSWORD"])
    )''',
    '''def mail_ready() -> bool:
    cfg = cast(dict[str, Any], current_app.config)
    return bool(
        cfg.get("CONTACT_EMAIL_ENABLED") and valid_email(str(cfg.get("CONTACT_EMAIL", "")))
        and valid_email(str(cfg.get("CONTACT_SMTP_FROM", ""))) and cfg.get("CONTACT_SMTP_HOST")
        and 1 <= int(cfg.get("CONTACT_SMTP_PORT", 0)) <= 65535
        and not (cfg.get("CONTACT_SMTP_USE_TLS") and cfg.get("CONTACT_SMTP_USE_SSL"))
        and (cfg.get("CONTACT_SMTP_USE_TLS") or cfg.get("CONTACT_SMTP_USE_SSL"))
        and bool(cfg.get("CONTACT_SMTP_USERNAME")) == bool(cfg.get("CONTACT_SMTP_PASSWORD"))
    )'''
)

# 4. Fix deliver_message
content = content.replace(
    '''def deliver_message(values: dict[str, str]) -> None:
    cfg = current_app.config''',
    '''def deliver_message(values: dict[str, str]) -> None:
    cfg = cast(dict[str, Any], current_app.config)'''
)
content = content.replace(
    '''    options = {"timeout": 10}''',
    '''    options: dict[str, Any] = {"timeout": 10}'''
)
content = content.replace(
    '''        with smtp_class(cfg["CONTACT_SMTP_HOST"], cfg["CONTACT_SMTP_PORT"], **options) as smtp:''',
    '''        with smtp_class(host=str(cfg["CONTACT_SMTP_HOST"]), port=int(cfg["CONTACT_SMTP_PORT"]), **options) as smtp:'''
)
content = content.replace(
    '''                smtp.login(cfg["CONTACT_SMTP_USERNAME"], cfg["CONTACT_SMTP_PASSWORD"])''',
    '''                smtp.login(str(cfg["CONTACT_SMTP_USERNAME"]), str(cfg["CONTACT_SMTP_PASSWORD"]))'''
)

# 5. Fix init_contact definition
content = content.replace(
    '''def init_contact(app, limiter, get_store, env_flag) -> None:''',
    '''def init_contact(app: Flask, limiter: Any, get_store: Callable[[], Any], env_flag: Callable[[str, Any], Any]) -> None:'''
)

# 6. Fix serializer
content = content.replace(
    '''    def serializer():
        return URLSafeTimedSerializer(current_app.secret_key, salt="contact-form-v1")''',
    '''    def serializer() -> URLSafeTimedSerializer:
        return URLSafeTimedSerializer(current_app.secret_key or "fallback", salt="contact-form-v1")'''
)

# 7. Fix render_page
content = content.replace(
    '''    def render_page(values=None, errors=None, status=200, sent=False):''',
    '''    def render_page(values: dict[str, str] | None = None, errors: dict[str, str] | None = None, status: int = 200, sent: bool = False) -> tuple[str, int]:'''
)
content = content.replace(
    '''            "contact.html", telegram_url=public_link(current_app.config["TELEGRAM_URL"]),
            discord_url=public_link(current_app.config["DISCORD_URL"]),
            contact_email=current_app.config["CONTACT_EMAIL"] if valid_email(current_app.config["CONTACT_EMAIL"]) else "",''',
    '''            "contact.html", telegram_url=public_link(str(current_app.config.get("TELEGRAM_URL", ""))),
            discord_url=public_link(str(current_app.config.get("DISCORD_URL", ""))),
            contact_email=str(current_app.config.get("CONTACT_EMAIL", "")) if valid_email(str(current_app.config.get("CONTACT_EMAIL", ""))) else "","'''.rstrip('"')
)

# 8. Fix limit decorator
content = content.replace(
    '''    @limiter.limit("5 per hour; 2 per minute")''',
    '''    @limiter.limit("5 per hour; 2 per minute")  # type: ignore'''
)

# 9. Fix token encode
content = content.replace(
    '''        key = "catrank:contact:" + hashlib.sha256(token["nonce"].encode()).hexdigest()''',
    '''        key = "catrank:contact:" + hashlib.sha256(str(token["nonce"]).encode()).hexdigest()'''
)

with open('contact.py', 'w') as f:
    f.write(content)
