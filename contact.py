"""Optional community links and a rate-limited, plain-text support mailbox."""
import hashlib
import os
import re
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from urllib.parse import urlparse

from typing import Any, Callable, cast
from flask import Flask, Blueprint, current_app, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer
from redis.exceptions import RedisError


def public_link(value: str) -> str:
    try:
        parsed = urlparse(value)
        if (parsed.scheme == "https" and parsed.hostname and not parsed.username
                and not parsed.password and not any(c.isspace() or ord(c) < 32 for c in value)):
            _ = parsed.port
            return value
    except ValueError:
        pass
    return ""


def valid_email(value: str) -> bool:
    # One ASCII mailbox only: no display names, lists, mailto parameters or headers.
    if len(value) > 254 or not value.isascii():
        return False
    return bool(re.fullmatch(
        r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
        r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
        r"[A-Za-z]{2,63}", value
    )) and len(value.split("@")[0]) <= 64


def mail_ready() -> bool:
    cfg = cast(dict[str, Any], current_app.config)
    return bool(
        cfg.get("CONTACT_EMAIL_ENABLED") and valid_email(str(cfg.get("CONTACT_EMAIL", "")))
        and valid_email(str(cfg.get("CONTACT_SMTP_FROM", ""))) and cfg.get("CONTACT_SMTP_HOST")
        and 1 <= int(cfg.get("CONTACT_SMTP_PORT", 0)) <= 65535
        and not (cfg.get("CONTACT_SMTP_USE_TLS") and cfg.get("CONTACT_SMTP_USE_SSL"))
        and (cfg.get("CONTACT_SMTP_USE_TLS") or cfg.get("CONTACT_SMTP_USE_SSL"))
        and bool(cfg.get("CONTACT_SMTP_USERNAME")) == bool(cfg.get("CONTACT_SMTP_PASSWORD"))
    )


def deliver_message(values: dict[str, str]) -> None:
    cfg = cast(dict[str, Any], current_app.config)
    message = EmailMessage()
    message["From"] = cfg["CONTACT_SMTP_FROM"]
    message["To"] = cfg["CONTACT_EMAIL"]
    message["Reply-To"] = values["email"]
    message["Subject"] = "[CatRank support] " + values["subject"]
    message.set_content(f"Name: {values['name']}\nEmail: {values['email']}\n\n{values['message']}")
    context = ssl.create_default_context()
    smtp_class = smtplib.SMTP_SSL if cfg["CONTACT_SMTP_USE_SSL"] else smtplib.SMTP
    options: dict[str, Any] = {"timeout": 10}
    if cfg["CONTACT_SMTP_USE_SSL"]:
        options["context"] = context
    accepted = False
    try:
        with smtp_class(host=str(cfg["CONTACT_SMTP_HOST"]), port=int(cfg["CONTACT_SMTP_PORT"]), **options) as smtp:
            if cfg["CONTACT_SMTP_USE_TLS"]:
                smtp.starttls(context=context)
            if cfg["CONTACT_SMTP_USERNAME"]:
                smtp.login(str(cfg["CONTACT_SMTP_USERNAME"]), str(cfg["CONTACT_SMTP_PASSWORD"]))
            smtp.send_message(message)
            accepted = True
    except (smtplib.SMTPException, OSError):
        if not accepted:
            raise
        # A failed QUIT cannot undo the server's successful DATA acknowledgement.
        current_app.logger.info("Contact mail accepted; SMTP connection cleanup failed")


def init_contact(app: Flask, limiter: Any, get_store: Callable[[], Any], env_flag: Callable[[str, Any], Any]) -> None:
    for key in ("TELEGRAM_URL", "DISCORD_URL", "CONTACT_EMAIL", "CONTACT_SMTP_HOST",
                "CONTACT_SMTP_USERNAME", "CONTACT_SMTP_PASSWORD", "CONTACT_SMTP_FROM"):
        app.config[key] = os.getenv(key, "") if key == "CONTACT_SMTP_PASSWORD" else os.getenv(key, "").strip()
    app.config["CONTACT_SMTP_FROM"] = app.config["CONTACT_SMTP_FROM"] or app.config["CONTACT_EMAIL"]
    for key, default in (("CONTACT_EMAIL_ENABLED", False), ("CONTACT_SMTP_USE_TLS", True),
                         ("CONTACT_SMTP_USE_SSL", False)):
        app.config[key] = env_flag(key, default)
    try:
        app.config["CONTACT_SMTP_PORT"] = int(os.getenv("CONTACT_SMTP_PORT") or "587")
    except ValueError:
        app.config["CONTACT_SMTP_PORT"] = 0

    contact = Blueprint("contact", __name__)

    def serializer() -> URLSafeTimedSerializer:
        return URLSafeTimedSerializer(current_app.secret_key or "fallback", salt="contact-form-v1")

    def render_page(values: dict[str, str] | None = None, errors: dict[str, str] | None = None, status: int = 200, sent: bool = False) -> tuple[str, int]:
        available = mail_ready() and get_store() is not None
        token = ""
        if available:
            session.setdefault("contact_csrf", secrets.token_urlsafe(32))
            token = serializer().dumps({"csrf": session["contact_csrf"], "nonce": secrets.token_urlsafe(24), "issued": time.time()})
        cfg = cast(dict[str, Any], current_app.config)
        return render_template(
            "contact.html", telegram_url=public_link(str(cfg.get("TELEGRAM_URL", ""))),
            discord_url=public_link(str(cfg.get("DISCORD_URL", ""))),
            contact_email=str(cfg.get("CONTACT_EMAIL", "")) if valid_email(str(cfg.get("CONTACT_EMAIL", ""))) else "",
            mail_available=available, contact_token=token, values=values or {}, errors=errors or {}, sent=sent,
        ), status

    @contact.get("/contact")
    def page():
        return render_page(sent=session.pop("contact_sent", False))

    @contact.post("/contact")
    @limiter.limit("5 per hour; 2 per minute")  # type: ignore
    def submit():
        if not mail_ready() or get_store() is None:
            return render_page(errors={"form": "Email sending is temporarily unavailable. Please use another contact option."}, status=503)
        # Form URL encoding can use twelve bytes per Unicode character.
        if request.content_length and request.content_length > 64 * 1024:
            return render_page(errors={"form": "Your message is too large. Please shorten it."}, status=413)
        values = {key: request.form.get(key, "").strip() for key in ("name", "email", "subject", "message")}
        errors: dict[str, str] = {}
        for key, maximum in (("name", 80), ("email", 254), ("subject", 120), ("message", 5000)):
            raw = request.form.get(key, "")
            if not values[key] or len(raw) > maximum:
                errors[key] = f"Enter {key} using 1–{maximum} characters."
            if any(ord(c) < 32 and (key != "message" or c not in "\r\n\t") or ord(c) == 127 for c in raw):
                errors[key] = "Remove unsupported control characters."
        if not valid_email(values["email"]):
            errors["email"] = "Enter a valid email address, such as you@example.com."
        
        token: dict[str, Any] = {}
        try:
            token = serializer().loads(request.form.get("contact_token", ""), max_age=3600)
            if not secrets.compare_digest(token.get("csrf", ""), session.get("contact_csrf", "missing")):
                raise BadSignature("Session mismatch")
            if time.time() - token["issued"] < 2 or request.form.get("website"):
                errors["form"] = "Please wait a moment and submit the form again."
        except (BadSignature, KeyError, TypeError, AttributeError):
            errors["form"] = "This form expired or could not be verified. Please try again using the refreshed form."
        if errors:
            return render_page(values, errors, 400)
        # A shared claim prevents double sends across tabs and Gunicorn workers.
        nonce_val = str(token.get("nonce", ""))
        key = "catrank:contact:" + hashlib.sha256(nonce_val.encode()).hexdigest()
        try:
            if not get_store().set(key, "submitted", nx=True, ex=3600):
                return render_page(values, {"form": "This form was already submitted. Check for a confirmation before sending again."}, 409)
        except RedisError:
            current_app.logger.warning("Contact submission storage is unavailable")
            return render_page(values, {"form": "Email sending is temporarily unavailable. Please try again later."}, 503)
        try:
            deliver_message(values)
        except (smtplib.SMTPException, OSError, ValueError) as error:
            # Retain the claim: a lost SMTP acknowledgement may still mean delivery.
            current_app.logger.warning("Contact delivery failed (%s)", type(error).__name__)
            return render_page(values, {"form": "We could not confirm delivery. Please try another contact option or retry later."}, 503)
        session["contact_sent"] = True
        return redirect(url_for("contact.page"), code=303)

    app.register_blueprint(contact)
