import hashlib
import json
import os
import re
import uuid
import secrets
import importlib
from collections import OrderedDict
from io import BytesIO
from functools import lru_cache, wraps
from datetime import datetime, timezone, timedelta
from time import monotonic
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple, cast
from urllib.parse import quote, urlparse

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, g, Response, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from supabase import create_client, Client, ClientOptions
from postgrest.types import CountMethod
from werkzeug.exceptions import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

BASE_DIR: Path = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

app: Flask = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
    static_url_path="/static"
)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = (4 * 1024 * 1024 + 128 * 1024) if os.getenv("VERCEL") == "1" else 6 * 1024 * 1024                                
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["RATELIMIT_HEADERS_ENABLED"] = True


@lru_cache(maxsize=128)
def asset_fingerprint(filename: str) -> str:
    directory = (BASE_DIR / "static").resolve()
    path = (directory / filename).resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise ValueError("Static asset is missing or outside the static directory")
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def asset_url(filename: str) -> str:
    return url_for("static", filename=filename, v=asset_fingerprint(filename))

def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

SUPABASE_URL: str = (os.getenv("SUPABASE_URL") or "").strip()
SUPABASE_ANON_KEY: str = (os.getenv("SUPABASE_ANON_KEY") or "").strip()
SUPABASE_SERVICE_KEY: str = (os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY") or "").strip()
ADMIN_EMAIL_CONFIG: str = os.getenv("ADMIN_EMAILS", os.getenv("ADMIN_EMAIL", "")).strip().lower()
PUBLIC_SITE_URL: str = (os.getenv("PUBLIC_SITE_URL") or "").strip().rstrip("/")
ENABLE_DEMO_DATA: bool = env_flag("ENABLE_DEMO_DATA", False)
APP_ENV: str = (os.getenv("APP_ENV") or "development").strip().lower()
IS_PRODUCTION: bool = APP_ENV == "production"
GOOGLE_AUTH_ENABLED: bool = env_flag("GOOGLE_AUTH_ENABLED", False)
PHONE_AUTH_ENABLED: bool = env_flag("PHONE_AUTH_ENABLED", False)
ALLOWED_COUNTRIES = frozenset(code.strip().upper() for code in os.getenv("ALLOWED_COUNTRIES", "").split(",") if code.strip())
COUNTRY_ACCESS_ENABLED: bool = env_flag("COUNTRY_ACCESS_ENABLED", False)
if COUNTRY_ACCESS_ENABLED and (not ALLOWED_COUNTRIES or any(not re.fullmatch(r"[A-Z]{2}", c) for c in ALLOWED_COUNTRIES)):
    raise RuntimeError("Country access requires a nonempty list of two-letter country codes")
if COUNTRY_ACCESS_ENABLED and os.getenv("VERCEL") != "1":
    raise RuntimeError("Country access currently requires the trusted Vercel geo header")
RATE_LIMIT_STORAGE_URI: str = (os.getenv("RATE_LIMIT_STORAGE_URI") or "memory://").strip()
try:
    _trust_proxy_hops = max(0, int(os.getenv("TRUST_PROXY_HOPS", "0")))
except ValueError:
    _trust_proxy_hops = 0
TRUST_PROXY_HOPS: int = _trust_proxy_hops
app.config["SESSION_COOKIE_SECURE"] = IS_PRODUCTION
if TRUST_PROXY_HOPS:
                                                                                    
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=TRUST_PROXY_HOPS, x_proto=TRUST_PROXY_HOPS)

def validate_production_configuration() -> None:
    if not IS_PRODUCTION:
        return

    errors: List[str] = []
    configured_secret = (os.getenv("SECRET_KEY") or "").strip()
    if len(configured_secret) < 32:
        errors.append("SECRET_KEY must be set to at least 32 characters")
    if not SUPABASE_URL:
        errors.append("SUPABASE_URL is required")
    if not SUPABASE_ANON_KEY:
        errors.append("SUPABASE_ANON_KEY is required")
    if not SUPABASE_SERVICE_KEY:
        errors.append("SUPABASE_SERVICE_KEY is required")
    if not PUBLIC_SITE_URL:
        errors.append("PUBLIC_SITE_URL is required")
    else:
        try:
            parsed_public = urlparse(PUBLIC_SITE_URL)
            if (
                parsed_public.scheme != "https"
                or not parsed_public.netloc
                or parsed_public.username
                or parsed_public.password
                or parsed_public.path not in {"", "/"}
                or parsed_public.params
                or parsed_public.query
                or parsed_public.fragment
            ):
                errors.append("PUBLIC_SITE_URL must be a clean HTTPS origin with no path/query/fragment")
        except ValueError:
            errors.append("PUBLIC_SITE_URL is invalid")

    if SUPABASE_URL:
        try:
            parsed_supabase = urlparse(SUPABASE_URL)
            if parsed_supabase.scheme != "https" or not parsed_supabase.netloc:
                errors.append("SUPABASE_URL must use HTTPS in production")
        except ValueError:
            errors.append("SUPABASE_URL is invalid")
    if ENABLE_DEMO_DATA:
        errors.append("ENABLE_DEMO_DATA must be false")
    if env_flag("FLASK_DEBUG", False):
        errors.append("FLASK_DEBUG must be false")

    r2_settings = [os.getenv(key, "").strip() for key in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_PUBLIC_DOMAIN")]
    if any(r2_settings) and not all(r2_settings):
        errors.append("Set all R2 credentials and R2_PUBLIC_DOMAIN, or leave them all empty")
    if r2_settings[-1]:
        try:
            origin = urlparse(r2_settings[-1])
            if origin.scheme != "https" or not origin.netloc or origin.username or origin.password or origin.query or origin.fragment:
                errors.append("R2_PUBLIC_DOMAIN must be a public HTTPS URL")
        except ValueError:
            errors.append("R2_PUBLIC_DOMAIN is invalid")
    if errors:
        raise RuntimeError("Invalid production configuration: " + "; ".join(errors))

validate_production_configuration()

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=RATE_LIMIT_STORAGE_URI,
    in_memory_fallback_enabled=True,
)
if IS_PRODUCTION and RATE_LIMIT_STORAGE_URI.startswith("memory://"):
    app.logger.warning("RATE_LIMIT_STORAGE_URI uses memory:// in production; use shared Redis for multi-worker/multi-replica deployments.")

# Reuse the same Redis endpoint for application caching unless a dedicated
# CACHE_REDIS_URL is provided. If Redis is unavailable, every helper below
# fails open and the app continues to query Supabase normally.
CACHE_REDIS_URL: str = (os.getenv("CACHE_REDIS_URL") or RATE_LIMIT_STORAGE_URI).strip()
redis_cache: Any = None
if CACHE_REDIS_URL.startswith(("redis://", "rediss://")):
    try:
        redis_module: Any = importlib.import_module("redis")
        redis_cache = redis_module.from_url(
            CACHE_REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            health_check_interval=30,
        )
        app.logger.info("Redis application cache configured")
    except Exception as redis_err:
        app.logger.warning("Redis application cache could not be initialized (%s)", type(redis_err).__name__)

CACHE_PREFIX = "catrank:v4"
cache_retry_after = 0.0
FEED_CACHE_TTL = 15
LEADERBOARD_CACHE_TTL = 45
CAT_CACHE_TTL = 45
PROFILE_CACHE_TTL = 45
IDENTITY_CACHE_TTL = 60

def make_cache_key(*parts: Any) -> str:
    cleaned = [str(part).replace(" ", "_") for part in parts]
    return ":".join([CACHE_PREFIX, *cleaned])

def cache_get(key: str) -> Any:
    global cache_retry_after
    client = redis_cache
    if client is None or monotonic() < cache_retry_after:
        return None
    try:
        raw = client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        cache_retry_after = monotonic() + 15
        app.logger.debug("Redis cache read failed for %s: %s", key, exc)
        return None

def cache_get_dict(key: str) -> Optional[Dict[str, Any]]:
    value = cache_get(key)
    return cast(Dict[str, Any], value) if isinstance(value, dict) else None

def cache_set(key: str, value: Any, seconds: int) -> None:
    global cache_retry_after
    client = redis_cache
    if client is None or monotonic() < cache_retry_after:
        return
    try:
        client.setex(key, max(1, int(seconds)), json.dumps(value, default=str, separators=(",", ":")))
    except Exception as exc:
        cache_retry_after = monotonic() + 15
        app.logger.debug("Redis cache write failed for %s: %s", key, exc)

def cache_delete(*keys: str) -> None:
    client = redis_cache
    clean_keys = [key for key in keys if key]
    if client is None or not clean_keys or monotonic() < cache_retry_after:
        return
    try:
        client.delete(*clean_keys)
    except Exception as exc:
        app.logger.debug("Redis cache delete failed: %s", exc)

def cache_counter_value(name: str) -> int:
    value = cache_get(make_cache_key("version", name))
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

def bump_cache_counter(name: str) -> None:
    client = redis_cache
    if client is None or monotonic() < cache_retry_after:
        return
    try:
        client.incr(make_cache_key("version", name))
    except Exception as exc:
        app.logger.debug("Redis cache version bump failed for %s: %s", name, exc)

def invalidate_profile_cache(user_id: Any) -> None:
    uid = str(user_id or "").strip()
    if not uid:
        return
    cache_delete(
        make_cache_key("profile", uid),
        make_cache_key("identity", uid),
    )

def invalidate_attribution(user_id: Any) -> None:
    invalidate_profile_cache(user_id)
    user_avatar_cache.pop(str(user_id), None)
    bump_cache_counter("cats")
    bump_cache_counter("attribution")

def invalidate_comments(cat_id: Any) -> None:
    bump_cache_counter(f"comments:{cat_id}")

def invalidate_cat_content(*, cat_id: Any = None, user_id: Any = None) -> None:
    # Feed and leaderboard keys include this generation number, so bumping it
    # makes every older cached feed/ranking entry unreachable immediately.
    bump_cache_counter("cats")
    cid = str(cat_id or "").strip()
    if cid:
        cache_delete(make_cache_key("cat", cid))
    if user_id:
        invalidate_profile_cache(user_id)

if not os.getenv("SECRET_KEY"):
    app.logger.warning("SECRET_KEY is not set; generated an ephemeral key for this process.")
if not (SUPABASE_URL and SUPABASE_ANON_KEY):
    app.logger.warning("Supabase public configuration is incomplete; browser auth will be unavailable.")
if not SUPABASE_SERVICE_KEY:
    app.logger.warning("SUPABASE_SERVICE_KEY is not set; privileged backend database operations will be unavailable.")

supabase_admin: Optional[Client] = None
supabase_auth: Optional[Client] = None

try:
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY, options=ClientOptions(persist_session=False, auto_refresh_token=False))
except Exception as init_err:
    app.logger.warning("Failed to init supabase_admin: %s", init_err)

try:
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        supabase_auth = create_client(SUPABASE_URL, SUPABASE_ANON_KEY, options=ClientOptions(persist_session=False, auto_refresh_token=False))
except Exception as init_err:
    app.logger.warning("Failed to init supabase_auth: %s", init_err)

R2_ACCOUNT_ID: str = os.getenv("R2_ACCOUNT_ID", "").strip()
R2_ACCESS_KEY_ID: str = os.getenv("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_ACCESS_KEY: str = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET_NAME: str = os.getenv("R2_BUCKET_NAME", "cat-images").strip()
R2_PUBLIC_DOMAIN: str = os.getenv("R2_PUBLIC_DOMAIN", "").strip().rstrip("/")

r2_client: Any = None
_r2_init_lock = Lock()


def get_r2_client() -> Any:
    global r2_client
    if r2_client is not None:
        return r2_client
    if not (R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY):
        return None
    with _r2_init_lock:
        if r2_client is not None:
            return r2_client
        try:
            boto3_module: Any = importlib.import_module("boto3")
            config_module: Any = importlib.import_module("botocore.config")
            r2_client = boto3_module.client(
                service_name="s3",
                endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
                aws_access_key_id=R2_ACCESS_KEY_ID,
                aws_secret_access_key=R2_SECRET_ACCESS_KEY,
                region_name="auto",
                config=config_module.Config(
                    signature_version="s3v4", connect_timeout=3, read_timeout=10,
                    retries={"mode": "standard", "total_max_attempts": 2},
                ),
            )
        except Exception as exc:
            app.logger.warning("Could not initialize image storage (%s)", type(exc).__name__)
    return r2_client

STORAGE_BUCKET: str = "cat-images"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "jfif", "gif"}
MAX_FILE_SIZE: int = (4 if os.getenv("VERCEL") == "1" else 5) * 1024 * 1024        

MOCK_CATS: List[Dict[str, Any]] = [
    {
        "id": "cat-mock-1",
        "user_id": "user-mock-1",
        "user_name": "WhiskersFan",
        "user_avatar": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=150&q=80",
        "name": "Mochi the Fluff",
        "bio": "A playful Scottish Fold who loves chasing laser pointers.",
        "description": "A playful Scottish Fold who loves chasing laser pointers.",
        "image_url": "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?auto=format&fit=crop&w=1000&q=80",
        "likes_count": 42,
        "created_at": "2026-08-28T10:00:00Z"
    },
    {
        "id": "cat-mock-2",
        "user_id": "user-mock-2",
        "user_name": "CatMaster",
        "user_avatar": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=150&q=80",
        "name": "Luna Starry",
        "bio": "Sleeps 18 hours a day, purrs like an engine.",
        "description": "Sleeps 18 hours a day, purrs like an engine.",
        "image_url": "https://images.unsplash.com/photo-1573865526739-10659fec78a5?auto=format&fit=crop&w=1000&q=80",
        "likes_count": 38,
        "created_at": "2026-08-27T14:30:00Z"
    },
    {
        "id": "cat-mock-3",
        "user_id": "user-mock-3",
        "user_name": "FelineKing",
        "user_avatar": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=150&q=80",
        "name": "Simba Majestic",
        "bio": "The king of the living room rug.",
        "description": "The king of the living room rug.",
        "image_url": "https://images.unsplash.com/photo-1533738363-b7f9aef128ce?auto=format&fit=crop&w=1000&q=80",
        "likes_count": 29,
        "created_at": "2026-08-26T09:15:00Z"
    }
]

MOCK_LIKES: List[Dict[str, Any]] = []
MOCK_COMMENTS: List[Dict[str, Any]] = []
MOCK_NOTIFICATIONS: List[Dict[str, Any]] = []
user_avatar_cache: "OrderedDict[str, str]" = OrderedDict()
USER_AVATAR_CACHE_MAX: int = 2048

def cache_user_avatar(user_id: Any, avatar_url: str) -> None:
    key = str(user_id or "")
    if not key:
        return
    user_avatar_cache[key] = avatar_url
    user_avatar_cache.move_to_end(key)
    while len(user_avatar_cache) > USER_AVATAR_CACHE_MAX:
        user_avatar_cache.popitem(last=False)

def is_allowed_file(filename: Optional[str]) -> bool:
    if not filename or "." not in str(filename):
        return False
    ext: str = str(filename).rsplit(".", 1)[-1].lower()
    return ext in ALLOWED_EXTENSIONS

def validate_image_file(file_bytes: bytes, filename: Optional[str]) -> Tuple[bool, str]:
    if not filename or "." not in str(filename):
        return False, "File has no valid extension."
    ext: str = str(filename).rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Invalid extension '.{ext}'. Allowed formats: PNG, JPG, JPEG, WEBP, GIF, JFIF."
    if len(file_bytes) > MAX_FILE_SIZE:
        return False, "File size exceeds 5MB limit."
    if len(file_bytes) < 12:
        return False, "Corrupted or empty image file."

    try:
        with Image.open(BytesIO(file_bytes)) as img:
            detected = (img.format or "").upper()
            if detected not in {"JPEG", "PNG", "WEBP", "GIF"}:
                return False, "Unsupported image format."
            width, height = img.size
            if width < 32 or height < 32:
                return False, "Image is too small (minimum 32x32)."
            if width * height > 25_000_000:
                return False, "Image dimensions are too large."
            if detected == "GIF":
                frames = getattr(img, "n_frames", 1)
                if frames > 200 or width * height * frames > 100_000_000:
                    return False, "Animation is too large. Use a shorter or smaller GIF."
                for frame in range(frames):
                    img.seek(frame)
                    img.load()
            else:
                img.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return False, "Uploaded file is not a valid image."

    return True, ""

def optimize_image_file(file_bytes: bytes, *, avatar: bool = False) -> Tuple[bytes, str, str]:
    """Normalize static uploads for faster delivery and lower storage usage.

    Animated GIFs are preserved. Other supported images are orientation-corrected,
    resized to a sane maximum dimension, and encoded as WebP.
    """
    with Image.open(BytesIO(file_bytes)) as img:
        if not avatar and (img.format or "").upper() == "GIF" and getattr(img, "is_animated", False):
            return file_bytes, "gif", "image/gif"

        img = ImageOps.exif_transpose(img)
        max_side = 512 if avatar else 2048
        if max(img.size) > max_side:
            img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

        if img.mode not in {"RGB", "RGBA"}:
            img = img.convert("RGBA" if "transparency" in img.info else "RGB")

        out = BytesIO()
        img.save(out, format="WEBP", quality=84 if avatar else 86, method=4)
        return out.getvalue(), "webp", "image/webp"

def upload_file_to_storage(file_bytes: bytes, unique_path: str, content_type: str, bucket_name: str = STORAGE_BUCKET) -> str:
    storage_client = get_r2_client() if R2_BUCKET_NAME and R2_PUBLIC_DOMAIN else None
    if storage_client is not None:
        try:
            storage_client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=unique_path,
                Body=file_bytes,
                ContentType=content_type,
                CacheControl="public, max-age=31536000, immutable"
            )
            return f"{R2_PUBLIC_DOMAIN}/{unique_path}"
        except Exception as r2_e:
            app.logger.warning("Cloudflare R2 upload error: %s", r2_e)

    if supabase_admin:
        try:
            supabase_admin.storage.from_(bucket_name).upload(
                path=unique_path,
                file=file_bytes,
                file_options={"content-type": content_type, "cache-control": "31536000"}
            )
            return str(supabase_admin.storage.from_(bucket_name).get_public_url(unique_path) or "")
        except Exception as se:
            app.logger.warning("Supabase storage upload error: %s", se)

    return ""

def delete_file_from_storage(
    public_url: str,
    bucket_name: str = STORAGE_BUCKET,
    *,
    allowed_prefix: Optional[str] = None,
) -> None:
    """Best-effort cleanup for files that are provably managed by this app.

    Never derive a storage key from a look-alike external URL. When an ownership
    prefix is supplied, only objects inside that user's generated namespace can
    be removed.
    """
    url = str(public_url or "").strip()
    if not url:
        return

    try:
        parsed = urlparse(url)
        key = ""
        backend = ""
        admin = supabase_admin

        if R2_PUBLIC_DOMAIN:
            r2_origin = urlparse(R2_PUBLIC_DOMAIN)
            if (
                parsed.scheme == r2_origin.scheme
                and parsed.netloc == r2_origin.netloc
                and parsed.scheme in {"http", "https"}
            ):
                base_path = r2_origin.path.rstrip("/")
                prefix_path = f"{base_path}/" if base_path else "/"
                if parsed.path.startswith(prefix_path):
                    key = parsed.path[len(prefix_path):].lstrip("/")
                    backend = "r2"

        if not backend and admin is not None and SUPABASE_URL:
            supabase_origin = urlparse(SUPABASE_URL)
            storage_prefix = f"/storage/v1/object/public/{bucket_name}/"
            if (
                parsed.scheme == supabase_origin.scheme
                and parsed.netloc == supabase_origin.netloc
                and parsed.path.startswith(storage_prefix)
            ):
                key = parsed.path[len(storage_prefix):].lstrip("/")
                backend = "supabase"

        if not backend or not key or key.startswith("/") or ".." in key.split("/"):
            return
        if allowed_prefix and not key.startswith(allowed_prefix):
            app.logger.warning("Skipped storage cleanup outside allowed prefix: %s", key)
            return

        if backend == "r2":
            storage_client = get_r2_client()
            if storage_client is not None:
                storage_client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
        elif backend == "supabase" and admin is not None:
            admin.storage.from_(bucket_name).remove([key])
    except Exception as exc:
        app.logger.warning("Storage cleanup failed for managed object: %s", exc)

def generate_default_avatar(name: str) -> str:
    safe_name = quote((name.strip() or "Cat")[:80], safe="")
    return f"https://api.dicebear.com/7.x/bottts/svg?seed={safe_name}&backgroundColor=b6e3f4,c0aede,d1d4f9"

def resolve_user_avatar(user_id: Optional[str], user_name: Optional[str], existing_avatar: Optional[str] = None) -> str:
                                                                                        
    if existing_avatar and str(existing_avatar).strip():
        avatar_str = sanitize_image_url(existing_avatar, fallback_name=str(user_name or "Cat"))
        if user_id:
            cache_user_avatar(user_id, avatar_str)
        return avatar_str

    safe_uname = str(user_name or "").strip() or "Cat"
    avatar_url = generate_default_avatar(safe_uname)
    if user_id:
        cache_user_avatar(user_id, avatar_url)
    return avatar_url

def is_admin_user(user: Any) -> bool:
    """Admin authorization must only trust server-controlled claims/config.

    Never trust user_metadata for roles: users can edit their own user_metadata.
    """
    if not user:
        return False
    user_email = str(getattr(user, "email", "") or "").strip().lower()
    admin_emails = {e.strip().lower() for e in ADMIN_EMAIL_CONFIG.split(",") if e.strip()}
    if user_email and user_email in admin_emails:
        return True

    raw_app_meta = getattr(user, "app_metadata", {})
    app_meta: Dict[str, Any] = cast(Dict[str, Any], raw_app_meta) if isinstance(raw_app_meta, dict) else {}
    return str(app_meta.get("role", "")).strip().lower() == "admin"

def sanitize_nullable_str(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in ("none", "null", "undefined", ""):
        return None
    return s

def clean_text(value: Any, *, max_length: int, fallback: str = "") -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or "")).strip()
    return (text[:max_length] or fallback).strip()

def sanitize_image_url(value: Any, *, fallback_name: str = "Cat") -> str:
    url = str(value or "").strip()
    if not url or len(url) > 2048 or any(ch in url for ch in ('"', "'", '<', '>', '\\')) or any(ch.isspace() for ch in url):
        return generate_default_avatar(fallback_name)
    try:
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.netloc and not parsed.username and not parsed.password:
            return url
    except ValueError:
        pass
    return generate_default_avatar(fallback_name)

def get_canonical_user_identity(user: Any) -> Tuple[str, str, str]:
    """Return server-trusted display name/avatar for content attribution.

    Auth user_metadata is user-editable and is never trusted for attribution.
    The profiles table is canonical; deterministic email-based values are fallback only.
    Successful canonical profile lookups are cached briefly in shared Redis.
    """
    user_id = str(getattr(user, "id", "") or "")
    email = str(getattr(user, "email", "") or "")

    fallback_name = clean_text(email.split("@")[0] if "@" in email else "Cat Lover", max_length=40, fallback="Cat Lover")
    fallback_avatar = generate_default_avatar(fallback_name)

    if supabase_admin and user_id:
        identity_key = make_cache_key("identity", user_id)
        cached_identity = cache_get_dict(identity_key)
        if cached_identity is not None:
            cached_name = clean_text(cached_identity.get("name"), max_length=40, fallback=fallback_name)
            cached_avatar = sanitize_image_url(cached_identity.get("avatar"), fallback_name=cached_name)
            return user_id, cached_name, cached_avatar

        try:
            result = supabase_admin.table("profiles").select("display_name,avatar_url").eq("id", user_id).limit(1).execute()
            rows = getattr(result, "data", []) or []
            if rows:
                row = rows[0]
                name = clean_text(row.get("display_name"), max_length=40, fallback=fallback_name)
                avatar = sanitize_image_url(row.get("avatar_url"), fallback_name=name)
                cache_set(identity_key, {"name": name, "avatar": avatar}, IDENTITY_CACHE_TTL)
                return user_id, name, avatar
        except Exception as exc:
            app.logger.warning("Could not load canonical profile identity for %s: %s", user_id, exc)

    return user_id, fallback_name, fallback_avatar

def public_site_url() -> str:

    return PUBLIC_SITE_URL or request.url_root.rstrip("/")

def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

def as_row_list(value: Any) -> List[Dict[str, Any]]:
    """Narrow a Supabase/PostgREST JSON result to a list of object rows."""
    if not isinstance(value, list):
        return []
    items: List[Any] = cast(List[Any], value)
    return [cast(Dict[str, Any], item) for item in items if isinstance(item, dict)]

def fetch_all_rows(query_factory: Callable[[], Any]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    while True:
        response = query_factory().range(len(result), len(result) + 499).execute()
        rows = as_row_list(getattr(response, "data", None))
        result.extend(rows)
        if len(rows) < 500:
            return result

def get_db_row(query: Any) -> Optional[Dict[str, Any]]:
    rows = getattr(query.limit(1).execute(), "data", []) or []
    return rows[0] if rows else None

def safe_db_insert(table_name: str, payload: Dict[str, Any]) -> Any:
    if not supabase_admin:
        return None
    try:
        return supabase_admin.table(table_name).insert(payload).execute()
    except Exception as e:
        app.logger.warning("Database insert failed on %s: %s", table_name, e)
        return None

def safe_db_update(table_name: str, payload: Dict[str, Any], id_column: str, id_value: Any) -> Any:
    if not supabase_admin:
        return None
    try:
        return supabase_admin.table(table_name).update(payload).eq(id_column, id_value).execute()
    except Exception as e:
        app.logger.warning("Database update failed on %s: %s", table_name, e)
        return None

def push_notification(user_id: str, actor_id: str, actor_name: str, actor_avatar: str, notif_type: str, cat_id: str, message: str, cat_name: Optional[str] = None, cat_image: Optional[str] = None, comment_id: Optional[str] = None) -> None:
    if not user_id or str(user_id) == str(actor_id):
        return

    clean_actor_avatar = resolve_user_avatar(actor_id, actor_name, actor_avatar)
    notif_data: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "actor_avatar": clean_actor_avatar,
        "type": notif_type,
        "cat_id": cat_id,
        "cat_name": cat_name or "Cat",
        "cat_image": cat_image or "",
        "comment_id": comment_id,
        "message": message,
        "is_read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    if supabase_admin:
        safe_db_insert("notifications", notif_data)
    elif ENABLE_DEMO_DATA:
        MOCK_NOTIFICATIONS.insert(0, notif_data)

def require_auth(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized. Please sign in."}), 401

        token = auth_header[7:].strip()
        if not token or " " in token:
            return jsonify({"error": "Malformed authorization token."}), 401

        if not supabase_auth and not supabase_admin:
            return jsonify({"error": "Authentication service is not configured."}), 503

        auth_user = None
        last_error: Optional[Exception] = None
        for client in (supabase_auth, supabase_admin):
            if not client:
                continue
            try:
                user_res: Any = client.auth.get_user(token)
                auth_user = getattr(user_res, "user", None) or getattr(user_res, "data", None)
                if auth_user:
                    break
            except Exception as exc:
                last_error = exc

        if not auth_user:
            if last_error:
                app.logger.info("Rejected invalid auth token: %s", type(last_error).__name__)
            return jsonify({"error": "Invalid or expired session. Please sign in again."}), 401

        g.user = auth_user
        return f(*args, **kwargs)
    return decorated_function

def authenticated_user_rate_key() -> str:
    """Rate-limit authenticated actions by account instead of shared Wi-Fi IP."""
    user = getattr(g, "user", None)
    user_id = str(getattr(user, "id", "") or "").strip()
    if user_id:
        return f"user:{user_id}"
    return f"ip:{get_remote_address()}"

@app.before_request
def assign_request_id() -> None:
    supplied = (request.headers.get("X-Request-ID") or "").strip()
    g.request_id = supplied if re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", supplied) else str(uuid.uuid4())
    if COUNTRY_ACCESS_ENABLED and request.path not in {"/livez", "/healthz"} and not request.path.startswith("/static/"):
        country = request.headers.get("X-Vercel-IP-Country", "").strip().upper()
        if country not in ALLOWED_COUNTRIES:
            from flask import abort
            abort(403, description="CatRank is not available in your country or your location could not be verified.")
    if request.path.startswith("/api/") and not ENABLE_DEMO_DATA:
        for key, value in (request.view_args or {}).items():
            if key.endswith("_id"):
                try:
                    uuid.UUID(str(value))
                except (ValueError, TypeError):
                    from flask import abort
                    abort(404)

@app.after_request
def apply_response_headers(response: Response) -> Response:
    response.headers["X-Request-ID"] = str(getattr(g, "request_id", ""))
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer" if request.path in {"/auth/callback", "/reset-password"} else "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' https: data: blob:; "
        f"font-src 'self'; connect-src 'self' {SUPABASE_URL} {SUPABASE_URL.replace('https://', 'wss://')}; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elif request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
    else:
        response.headers["Cache-Control"] = "no-store"
    return response

@app.errorhandler(429)
def rate_limit_exceeded(_error: Any) -> Any:
    if request.path.startswith("/api/"):
        return jsonify({"error": "Too many requests. Please try again shortly."}), 429
    return Response("Too many requests. Please try again shortly.", status=429, mimetype="text/plain")

@app.errorhandler(413)
def request_too_large(_error: Any) -> Any:
    if request.path.startswith("/api/"):
        return jsonify({"error": f"Upload is too large. Maximum image size is {MAX_FILE_SIZE // (1024 * 1024)}MB."}), 413
    return Response("Request is too large.", status=413, mimetype="text/plain")

@app.errorhandler(HTTPException)
def http_error(error: HTTPException) -> Any:
    if request.path.startswith("/api/"):
        response = error.get_response()
        response.data = app.json.dumps({"error": error.description if error.code == 403 else error.name})
        response.content_type = "application/json"
        return response
    return render_template("error.html", status=error.code, message=error.description), error.code

@app.errorhandler(500)
def server_error(error: Any) -> Any:
    if request.path.startswith("/api/"):
        return jsonify({"error": "Something went wrong. Please try again."}), 500
    return render_template("error.html", status=500, message="Something went wrong. Please try again."), 500

@app.context_processor
def shared_template_context() -> Dict[str, Any]:
    return {"supabase_url": SUPABASE_URL, "supabase_anon_key": SUPABASE_ANON_KEY,
            "google_auth_enabled": GOOGLE_AUTH_ENABLED, "phone_auth_enabled": PHONE_AUTH_ENABLED,
            "asset_url": asset_url}

@app.route("/livez")
def livez() -> Any:
    return jsonify({"status": "ok"})

@app.route("/healthz")
def healthz() -> Any:
    admin = supabase_admin
    auth_client = supabase_auth
    ready = admin is not None and auth_client is not None
    if admin is not None and auth_client is not None:
        try:
            admin.table("profiles").select("id").limit(1).execute()
        except Exception:
            ready = False
    return jsonify({"status": "ok" if ready else "unavailable"}), (200 if ready else 503)

@app.route("/favicon.ico")
def favicon() -> Response:
    return Response(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">🐱</text></svg>',
        mimetype="image/svg+xml"
    )

@app.route("/")
def index() -> Any:
    page = max(1, min(request.args.get("page", 1, type=int), 10000))
    sort = request.args.get("sort", "newest")
    sort = sort if sort in {"newest", "top"} else "newest"
    query_text = clean_text(request.args.get("q"), max_length=80)
    page_size = 24
    cats: List[Dict[str, Any]] = []
    top_cat: Optional[Dict[str, Any]] = None
    unavailable = False
    admin = supabase_admin

    if admin is not None:
        cats_version = cache_counter_value("cats")
        query_hash = hashlib.sha256(query_text.encode("utf-8")).hexdigest()[:16] if query_text else "all"
        feed_key = make_cache_key("feed", cats_version, page, sort, query_hash)
        cached_feed = cache_get_dict(feed_key)

        if cached_feed is not None:
            cats = as_row_list(cached_feed.get("cats"))
            cached_top = cached_feed.get("top_cat")
            top_cat = cast(Dict[str, Any], cached_top) if isinstance(cached_top, dict) else None
        else:
            try:
                query = admin.table("cats").select("*")
                if query_text:
                    query = query.ilike("name", "%" + escape_like(query_text) + "%")
                if sort == "top":
                    query = query.order("likes_count", desc=True)
                cats_response = query.order("created_at", desc=True).order("id").range((page - 1) * page_size, page * page_size).execute()
                cats = as_row_list(getattr(cats_response, "data", None))
                top_response = admin.table("cats").select("*").order("likes_count", desc=True).order("created_at", desc=True).limit(1).execute()
                top_rows = as_row_list(getattr(top_response, "data", None))
                top_cat = top_rows[0] if top_rows else None
                cache_set(feed_key, {"cats": cats, "top_cat": top_cat}, FEED_CACHE_TTL)
            except Exception:
                app.logger.exception("Could not load community feed")
                unavailable = True
    elif ENABLE_DEMO_DATA:
        all_cats = [dict(c) for c in MOCK_CATS if query_text.lower() in c["name"].lower()]
        all_cats.sort(key=lambda c: (c["likes_count"] if sort == "top" else c["created_at"], c["id"]), reverse=True)
        cats = all_cats[(page - 1) * page_size:page * page_size + 1]
        top_cat = max(MOCK_CATS, key=lambda c: c["likes_count"], default=None)
    else:
        unavailable = True

    has_next = len(cats) > page_size
    cats = cats[:page_size]
    for cat in cats + ([top_cat] if top_cat else []):
        cat["user_avatar"] = resolve_user_avatar(cat.get("user_id"), cat.get("user_name"), cat.get("user_avatar"))
        cat["image_url"] = sanitize_image_url(cat.get("image_url"), fallback_name=cat.get("name", "Cat"))
    return render_template("index.html", cats=cats, top_cat=top_cat, page=page,
                           sort=sort, query=query_text, has_next=has_next,
                           unavailable=unavailable), (503 if unavailable else 200)

@app.route("/leaderboard")
def leaderboard_page() -> Any:
    leaderboard: List[Dict[str, Any]] = []

    if supabase_admin:
        cats_version = cache_counter_value("cats")
        leaderboard_key = make_cache_key("leaderboard", cats_version)
        cached_leaderboard = cache_get(leaderboard_key)
        if isinstance(cached_leaderboard, list):
            leaderboard = as_row_list(cached_leaderboard)
        else:
            try:
                raw_res: Any = getattr(supabase_admin.table("cats").select("*").order("likes_count", desc=True).order("created_at", desc=True).limit(10).execute(), "data", [])
                leaderboard = cast(List[Dict[str, Any]], raw_res) if isinstance(raw_res, list) else []
                cache_set(leaderboard_key, leaderboard, LEADERBOARD_CACHE_TTL)
            except Exception:
                app.logger.exception("Could not load leaderboard")
                return render_template("error.html", status=503, message="The rankings are temporarily unavailable. Please try again."), 503
    elif not ENABLE_DEMO_DATA:
        return render_template("error.html", status=503, message="The rankings are temporarily unavailable. Please try again."), 503

    if not leaderboard and ENABLE_DEMO_DATA:
        leaderboard = sorted(list(MOCK_CATS), key=lambda c: int(c.get("likes_count", 0) or 0), reverse=True)[:10]

    for c in leaderboard:
        c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))

    return render_template(
        "leaderboard.html",
        leaderboard=leaderboard,
        supabase_url=SUPABASE_URL,
        supabase_anon_key=SUPABASE_ANON_KEY
    )

@app.route("/upload")
def upload_page() -> str:
    return render_template("upload.html", supabase_url=SUPABASE_URL, supabase_anon_key=SUPABASE_ANON_KEY)

@app.route("/login")
def login_page() -> str:
    return render_template("login.html", supabase_url=SUPABASE_URL, supabase_anon_key=SUPABASE_ANON_KEY)

@app.route("/register")
def register_page() -> str:
    return render_template("register.html", supabase_url=SUPABASE_URL, supabase_anon_key=SUPABASE_ANON_KEY)

@app.route("/forgot-password")
def forgot_password_page() -> str:
    return render_template("forgot_password.html", supabase_url=SUPABASE_URL, supabase_anon_key=SUPABASE_ANON_KEY)

@app.route("/reset-password")
def reset_password_page() -> str:
    return render_template("reset_password.html", supabase_url=SUPABASE_URL, supabase_anon_key=SUPABASE_ANON_KEY)

@app.route("/profile")
def profile_page() -> str:
    return render_template("profile.html", view_user_id="", supabase_url=SUPABASE_URL, supabase_anon_key=SUPABASE_ANON_KEY)

@app.route("/user/<user_id>")
def public_user_profile_page(user_id: str) -> str:
    return render_template("profile.html", view_user_id=user_id, supabase_url=SUPABASE_URL, supabase_anon_key=SUPABASE_ANON_KEY)

@app.route("/admin")
def admin_page() -> str:
    return render_template("admin.html", supabase_url=SUPABASE_URL, supabase_anon_key=SUPABASE_ANON_KEY)

@app.route("/api/cats/upload", methods=["POST"])
@require_auth
@limiter.limit("10 per minute", key_func=authenticated_user_rate_key)
def upload_cat() -> Any:
    try:
        user = getattr(g, "user", None)
        user_id, user_name, avatar_url = get_canonical_user_identity(user)

        file = request.files.get("file")
        if not file or not getattr(file, "filename", None):
            return jsonify({"error": "No image file provided."}), 400
        if not supabase_admin and not ENABLE_DEMO_DATA:
            return jsonify({"error": "Database service is not configured."}), 503

        cat_name = clean_text(request.form.get("name"), max_length=80, fallback="Whiskers")
        cat_bio = clean_text(request.form.get("bio") or request.form.get("description"), max_length=1000)
        filename_str: str = str(getattr(file, "filename", "") or "")

        file_bytes: bytes = file.read()
        is_valid_img, img_err = validate_image_file(file_bytes, filename_str)
        if not is_valid_img:
            return jsonify({"error": img_err}), 400

        optimized_bytes, clean_ext, content_type = optimize_image_file(file_bytes, avatar=False)
        unique_path = f"{user_id}/{uuid.uuid4()}.{clean_ext}"
        public_url = upload_file_to_storage(optimized_bytes, unique_path, content_type, STORAGE_BUCKET)

        if not public_url:
            return jsonify({"error": "Image storage is unavailable. Nothing was saved; please try again."}), 503

        cat_id = str(uuid.uuid4())
        cat_record: Dict[str, Any] = {
            "id": cat_id,
            "user_id": user_id,
            "user_name": user_name,
            "user_avatar": avatar_url,
            "name": cat_name,
            "bio": cat_bio,
            "description": cat_bio,
            "image_url": public_url,
            "likes_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        if supabase_admin:
            if safe_db_insert("cats", cat_record) is None:
                delete_file_from_storage(public_url, STORAGE_BUCKET, allowed_prefix=f"{user_id}/")
                return jsonify({"error": "Database write failed. The uploaded image was rolled back."}), 503
        elif ENABLE_DEMO_DATA:
            MOCK_CATS.insert(0, cat_record)

        invalidate_cat_content(cat_id=cat_id, user_id=user_id)
        return jsonify({
            "message": "Cat uploaded successfully!",
            "cat": cat_record
        }), 201

    except Exception:
        app.logger.exception("Cat upload failed")
        return jsonify({"error": "Upload failed unexpectedly. Please try again."}), 500

@app.route("/api/cats/<cat_id>", methods=["GET"])
@limiter.limit("240 per minute")
def get_cat_details(cat_id: str) -> Any:
    cat_record: Optional[Dict[str, Any]] = None
    cat_key = make_cache_key("cat", cat_id, cache_counter_value("cats"))
    cached_cat = cache_get(cat_key)
    if isinstance(cached_cat, dict):
        cat_record = cast(Dict[str, Any], cached_cat)

    if cat_record is None and supabase_admin:
        try:
            raw_data = get_db_row(supabase_admin.table("cats").select("*").eq("id", cat_id))
            if raw_data:
                cat_record = raw_data
                cache_set(cat_key, cat_record, CAT_CACHE_TTL)
        except Exception:
            app.logger.exception("Could not load cat %s", cat_id)
            return jsonify({"error": "Cat service is unavailable."}), 503
    elif cat_record is None and not ENABLE_DEMO_DATA:
        return jsonify({"error": "Cat service is unavailable."}), 503

    if cat_record is None and ENABLE_DEMO_DATA:
        mock_match = next((c for c in MOCK_CATS if str(c.get("id")) == str(cat_id)), None)
        cat_record = dict(mock_match) if mock_match else None

    if not cat_record:
        return jsonify({"error": "Cat not found."}), 404

    cat_record = dict(cat_record)
    cat_record["user_avatar"] = resolve_user_avatar(cat_record.get("user_id"), cat_record.get("user_name"), cat_record.get("user_avatar"))
    return jsonify({"cat": cat_record}), 200

@app.route("/api/cats/<cat_id>", methods=["PUT"])
@require_auth
@limiter.limit("30 per hour", key_func=authenticated_user_rate_key)
def edit_cat(cat_id: str) -> Any:
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        is_admin = is_admin_user(getattr(g, "user", None))
        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}

        new_name = clean_text(data.get("name"), max_length=80)
        new_bio = clean_text(data.get("bio") or data.get("description"), max_length=1000)
        updates: Dict[str, Any] = {}
        if new_name:
            updates["name"] = new_name
        if "bio" in data or "description" in data:
            updates["bio"] = new_bio
            updates["description"] = new_bio
        if not updates:
            return jsonify({"error": "No updates provided."}), 400

        owner_user_id = ""
        if supabase_admin:
            try:
                cat_row = get_db_row(supabase_admin.table("cats").select("id,user_id").eq("id", cat_id))
            except Exception:
                cat_row = None
            if not cat_row:
                return jsonify({"error": "Cat not found."}), 404
            if str(cat_row.get("user_id")) != user_id and not is_admin:
                return jsonify({"error": "Permission denied. You can only edit your own cats."}), 403
            owner_user_id = str(cat_row.get("user_id") or "")
            if safe_db_update("cats", updates, "id", cat_id) is None:
                return jsonify({"error": "Database update failed."}), 503
        elif ENABLE_DEMO_DATA:
            match = next((c for c in MOCK_CATS if str(c.get("id")) == str(cat_id)), None)
            if not match:
                return jsonify({"error": "Cat not found."}), 404
            if str(match.get("user_id")) != user_id and not is_admin:
                return jsonify({"error": "Permission denied. You can only edit your own cats."}), 403
            owner_user_id = str(match.get("user_id") or "")
            match.update(updates)
        else:
            return jsonify({"error": "Database service is not configured."}), 503

        invalidate_cat_content(cat_id=cat_id, user_id=owner_user_id)
        return jsonify({"message": "Cat updated successfully."}), 200
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid update values."}), 400
    except Exception:
        app.logger.exception("Failed to edit cat %s", cat_id)
        return jsonify({"error": "Unable to update cat right now."}), 500

@app.route("/api/cats/<cat_id>", methods=["DELETE"])
@require_auth
@limiter.limit("20 per hour", key_func=authenticated_user_rate_key)
def delete_cat(cat_id: str) -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    is_admin = is_admin_user(getattr(g, "user", None))

    if not supabase_admin:
        if ENABLE_DEMO_DATA:
            match = next((c for c in MOCK_CATS if str(c.get("id")) == str(cat_id)), None)
            if not match:
                return jsonify({"error": "Cat not found."}), 404
            if str(match.get("user_id")) != user_id and not is_admin:
                return jsonify({"error": "Permission denied. You can only delete your own cats."}), 403
            owner_user_id = str(match.get("user_id") or "")
            MOCK_CATS[:] = [c for c in MOCK_CATS if str(c.get("id")) != str(cat_id)]
            MOCK_LIKES[:] = [l for l in MOCK_LIKES if str(l.get("cat_id")) != str(cat_id)]
            MOCK_COMMENTS[:] = [cm for cm in MOCK_COMMENTS if str(cm.get("cat_id")) != str(cat_id)]
            invalidate_cat_content(cat_id=cat_id, user_id=owner_user_id)
            return jsonify({"message": "Cat deleted successfully."}), 200
        return jsonify({"error": "Database service is unavailable."}), 503

    try:
        cat_row = get_db_row(supabase_admin.table("cats").select("id,user_id,image_url").eq("id", cat_id))
        if not cat_row:
            return jsonify({"error": "Cat not found."}), 404
        if str(cat_row.get("user_id")) != user_id and not is_admin:
            return jsonify({"error": "Permission denied. You can only delete your own cats."}), 403

        img_url = str(cat_row.get("image_url", ""))
        supabase_admin.table("cats").delete().eq("id", cat_id).execute()                         

        try:
            delete_file_from_storage(img_url, STORAGE_BUCKET, allowed_prefix=f"{str(cat_row.get('user_id') or '')}/")
        except Exception:
            app.logger.warning("Cat row deleted but image cleanup failed for %s", cat_id)

        invalidate_cat_content(cat_id=cat_id, user_id=cat_row.get("user_id"))
        return jsonify({"message": "Cat deleted successfully."}), 200
    except Exception:
        app.logger.exception("Failed to delete cat %s", cat_id)
        return jsonify({"error": "Unable to delete cat right now."}), 503

@app.route("/api/admin/cats/<cat_id>/force-delete", methods=["DELETE", "POST"])
@require_auth
@limiter.limit("30 per minute", key_func=authenticated_user_rate_key)
def admin_force_delete(cat_id: str) -> Any:
    if not is_admin_user(getattr(g, "user", None)):
        return jsonify({"error": "Admin access required."}), 403
    if not supabase_admin:
        return jsonify({"error": "Database service is unavailable."}), 503

    try:
        cat_row = get_db_row(supabase_admin.table("cats").select("id,user_id,image_url").eq("id", cat_id))
        if not cat_row:
            return jsonify({"error": "Cat not found."}), 404
        img_url = str(cat_row.get("image_url", ""))
        supabase_admin.table("cats").delete().eq("id", cat_id).execute()
        try:
            delete_file_from_storage(img_url, STORAGE_BUCKET, allowed_prefix=f"{str(cat_row.get('user_id') or '')}/")
        except Exception:
            app.logger.warning("Admin deleted cat %s but storage cleanup failed", cat_id)
        invalidate_cat_content(cat_id=cat_id, user_id=cat_row.get("user_id"))
        return jsonify({"message": "Cat force deleted by admin successfully."}), 200
    except Exception:
        app.logger.exception("Admin force-delete failed for cat %s", cat_id)
        return jsonify({"error": "Unable to delete cat right now."}), 503

@app.route("/api/cats/<cat_id>/like", methods=["POST"])
@require_auth
@limiter.limit("180 per minute", key_func=authenticated_user_rate_key)
def toggle_like(cat_id: str) -> Any:
    user = getattr(g, "user", None)
    user_id, user_name, actor_avatar = get_canonical_user_identity(user)

    if not supabase_admin:
        return jsonify({"error": "Voting service is unavailable."}), 503

    try:
        cat_row = get_db_row(supabase_admin.table("cats").select("id,user_id,name,image_url,likes_count").eq("id", cat_id))
        if not cat_row:
            return jsonify({"error": "Cat not found."}), 404

        rpc_result = supabase_admin.rpc(
            "toggle_cat_like",
            {"p_cat_id": cat_id, "p_user_id": user_id},
        ).execute()
        rpc_rows = as_row_list(getattr(rpc_result, "data", None))
        if not rpc_rows:
            return jsonify({"error": "Voting transaction did not complete."}), 503
        status = str(rpc_rows[0].get("action", ""))
        new_count = int(rpc_rows[0].get("likes_count", 0) or 0)
        if status not in {"liked", "unliked"}:
            return jsonify({"error": "Voting transaction returned an invalid state."}), 503

        if status == "liked":
            push_notification(
                user_id=str(cat_row.get("user_id", "")),
                actor_id=user_id,
                actor_name=user_name,
                actor_avatar=actor_avatar,
                notif_type="like",
                cat_id=cat_id,
                cat_name=str(cat_row.get("name", "Cat")),
                cat_image=str(cat_row.get("image_url", "")),
                message=f"{user_name} liked your cat {cat_row.get('name', 'Cat')}!",
            )

        invalidate_cat_content(cat_id=cat_id, user_id=cat_row.get("user_id"))
        return jsonify({"status": status, "likes_count": new_count}), 200
    except Exception:
        app.logger.exception("Failed to toggle like for cat %s", cat_id)
        return jsonify({"error": "Unable to update vote right now."}), 503

COMMENT_COLUMNS = "id,cat_id,user_id,user_name,user_avatar,parent_id,reply_to_id,reply_to_name,comment,created_at,updated_at,likes_count"


@app.route("/api/cats/<cat_id>/comments", methods=["GET"])
@limiter.limit("120 per minute")
def get_comments(cat_id: str) -> Any:
    cursor = request.args.get("cursor", "")
    if len(cursor) > 1000:
        return jsonify({"error": "Invalid comment cursor."}), 400
    serializer = URLSafeTimedSerializer(cast(str, app.config["SECRET_KEY"]), salt="comments-page")
    after = None
    if cursor:
        try:
            value = serializer.loads(cursor, max_age=86400)
            if value["cat"] != cat_id:
                raise ValueError("Wrong cat")
            after = (datetime.fromisoformat(value["created_at"]).isoformat(), str(uuid.UUID(value["id"])))
        except (BadSignature, SignatureExpired, ValueError, KeyError, TypeError):
            return jsonify({"error": "This comment page has expired. Reload the comments."}), 400
    key = make_cache_key("comments", cat_id, cache_counter_value(f"comments:{cat_id}"), cache_counter_value("attribution"), hashlib.sha256(cursor.encode()).hexdigest())
    cached = cache_get_dict(key)
    if cached is not None:
        return jsonify(dict(cached, server_time=datetime.now(timezone.utc).isoformat()))
    total = None
    page_size = 30
    try:
        if supabase_admin:
            query = supabase_admin.table("comments").select(COMMENT_COLUMNS, count=CountMethod.exact if not after else None).eq("cat_id", cat_id)
            if after:
                stamp, ident = after
                query = query.or_(f"created_at.gt.{stamp},and(created_at.eq.{stamp},id.gt.{ident})")
            result = query.order("created_at").order("id").limit(page_size + 1).execute()
            rows = as_row_list(getattr(result, "data", None))
            total = getattr(result, "count", None) if not after else None
        elif ENABLE_DEMO_DATA:
            all_rows = sorted((dict(c) for c in MOCK_COMMENTS if str(c.get("cat_id")) == cat_id), key=lambda c: (c["created_at"], c["id"]))
            total = len(all_rows) if not after else None
            rows = [c for c in all_rows if not after or (c["created_at"], c["id"]) > after][:page_size + 1]
        else:
            return jsonify({"error": "Comments service is unavailable."}), 503
        has_more = len(rows) > page_size
        rows = rows[:page_size]
        for row in rows:
            row.pop("user_email", None)
            row["user_avatar"] = sanitize_image_url(row.get("user_avatar"), fallback_name=str(row.get("user_name") or "Cat Lover"))
        next_cursor = None
        if has_more:
            last = rows[-1]
            next_cursor = serializer.dumps({"cat": cat_id, "created_at": last["created_at"], "id": last["id"]})
        payload = {"comments": rows, "total": total, "next_cursor": next_cursor, "has_more": has_more}
        cache_set(key, payload, 15)
        return jsonify(dict(payload, server_time=datetime.now(timezone.utc).isoformat()))
    except Exception:
        app.logger.exception("Could not load comments for cat %s", cat_id)
        return jsonify({"error": "Comments service is unavailable."}), 503

@app.route("/api/cats/<cat_id>/comments", methods=["POST"])
@require_auth
@limiter.limit("6 per minute; 60 per hour", key_func=authenticated_user_rate_key)
def add_comment(cat_id: str) -> Any:
    try:
        user = getattr(g, "user", None)
        user_id, user_name, avatar_url = get_canonical_user_identity(user)
        user_email = clean_text(getattr(user, "email", ""), max_length=254)

        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}
        raw_comment = data.get("comment")
        if not isinstance(raw_comment, str) or not 1 <= len(raw_comment.strip()) <= 300:
            return jsonify({"error": "Comments must contain 1–300 characters."}), 400
        comment_text = clean_text(raw_comment, max_length=300)
        parent_id = sanitize_nullable_str(data.get("parent_id"))
        reply_to_name = None
        reply_to_id = parent_id

        if not comment_text:
            return jsonify({"error": "Comment text cannot be empty."}), 400
        if not supabase_admin and not ENABLE_DEMO_DATA:
            return jsonify({"error": "Comments service is unavailable."}), 503

        cat_row_for_notification: Optional[Dict[str, Any]] = None
        parent_row_for_notification: Optional[Dict[str, Any]] = None
        if supabase_admin:
            try:
                cat_row_for_notification = get_db_row(
                    supabase_admin.table("cats").select("id,user_id,name,image_url").eq("id", cat_id)
                )
            except Exception:
                cat_row_for_notification = None
            if not cat_row_for_notification:
                return jsonify({"error": "Cat not found."}), 404

            if parent_id:
                try:
                    parent_row_for_notification = get_db_row(
                        supabase_admin.table("comments")
                        .select("id,cat_id,user_id,user_name,parent_id")
                        .eq("id", parent_id)
                    )
                except Exception:
                    parent_row_for_notification = None
                if not parent_row_for_notification or str(parent_row_for_notification.get("cat_id")) != str(cat_id):
                    return jsonify({"error": "Invalid reply target."}), 400
                reply_to_name = clean_text(parent_row_for_notification.get("user_name"), max_length=40, fallback="Cat Lover")
                root = parent_row_for_notification
                seen: set[str] = set()
                while root.get("parent_id"):
                    if str(root["id"]) in seen or len(seen) >= 30:
                        return jsonify({"error": "Invalid reply thread."}), 400
                    seen.add(str(root["id"]))
                    ancestor = get_db_row(supabase_admin.table("comments").select("id,cat_id,parent_id").eq("id", root["parent_id"]))
                    if not ancestor or str(ancestor.get("cat_id")) != str(cat_id):
                        return jsonify({"error": "Reply thread no longer exists."}), 400
                    root = ancestor
                parent_id = str(root["id"])
            since = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
            duplicate = get_db_row(supabase_admin.table("comments").select("id").eq("cat_id", cat_id).eq("user_id", user_id).eq("comment", comment_text).gte("created_at", since))
            if duplicate:
                return jsonify({"error": "You just posted this comment. Please wait before repeating it."}), 429

        comment_id = str(uuid.uuid4())
        comment_payload: Dict[str, Any] = {
            "id": comment_id,
            "cat_id": cat_id,
            "user_id": user_id,
            "user_name": user_name,
            "user_avatar": avatar_url,
            "user_email": user_email,
            "parent_id": parent_id,
            "reply_to_id": reply_to_id,
            "reply_to_name": reply_to_name,
            "comment": comment_text,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        if supabase_admin:
            if safe_db_insert("comments", comment_payload) is None:
                return jsonify({"error": "Could not save comment."}), 503

            try:
                cat_row = cat_row_for_notification
                if cat_row:
                    cat_owner_id = str(cat_row.get("user_id", ""))
                    cat_name = str(cat_row.get("name", "Cat"))
                    cat_image = str(cat_row.get("image_url", ""))

                    if parent_id and parent_row_for_notification:
                        parent_user_id = str(parent_row_for_notification.get("user_id", ""))
                        push_notification(
                            user_id=parent_user_id,
                            actor_id=user_id,
                            actor_name=user_name,
                            actor_avatar=avatar_url,
                            notif_type="reply",
                            cat_id=cat_id,
                            cat_name=cat_name,
                            cat_image=cat_image,
                            comment_id=comment_id,
                            message=f"{user_name} replied to your comment on {cat_name}!"
                        )
                    if not parent_row_for_notification or str(parent_row_for_notification.get("user_id")) != cat_owner_id:
                        push_notification(
                            user_id=cat_owner_id,
                            actor_id=user_id,
                            actor_name=user_name,
                            actor_avatar=avatar_url,
                            notif_type="comment",
                            cat_id=cat_id,
                            cat_name=cat_name,
                            cat_image=cat_image,
                            comment_id=comment_id,
                            message=f"{user_name} commented on your cat {cat_name}!"
                        )
            except Exception as ne:
                app.logger.warning("Supabase comment notification failed: %s", ne)

        if ENABLE_DEMO_DATA and not supabase_admin:
            MOCK_COMMENTS.append(comment_payload)

        invalidate_comments(cat_id)
        return jsonify({
            "message": "Comment posted successfully!",
            "comment": {k: v for k, v in comment_payload.items() if k != "user_email"}
        }), 201

    except Exception:
        app.logger.exception("Could not add comment to cat %s", cat_id)
        return jsonify({"error": "Could not post comment right now."}), 500

def mutate_comment(comment_id: str, *, delete: bool = False, admin_only: bool = False) -> Any:
    user = g.user
    admin = is_admin_user(user)
    if admin_only and not admin:
        return jsonify({"error": "Admin access required."}), 403
    if not supabase_admin:
        return jsonify({"error": "Comments service is unavailable."}), 503
    try:
        row = get_db_row(supabase_admin.table("comments").select("id,user_id,cat_id").eq("id", comment_id))
        if not row:
            return jsonify({"error": "Comment not found."}), 404
        if str(row.get("user_id")) != str(user.id) and not admin:
            return jsonify({"error": "You can only change your own comments."}), 403
        if delete:
            supabase_admin.table("comments").delete().eq("id", comment_id).execute()
            invalidate_comments(row.get("cat_id"))
            return jsonify({"message": "Comment deleted.", "comment_id": comment_id})
        raw = request_json().get("comment")
        if not isinstance(raw, str) or not raw.strip() or len(raw.strip()) > 300:
            return jsonify({"error": "Comments must contain 1–300 characters."}), 400
        text = clean_text(raw, max_length=300)
        result = supabase_admin.rpc("edit_comment_with_window", {"p_comment_id": comment_id, "p_user_id": str(user.id), "p_comment": text, "p_admin": admin}).execute()
        rows = as_row_list(result.data)
        if not rows:
            return jsonify({"error": "Comment not found."}), 404
        updated = rows[0]
        status = str(updated.get("status", ""))
        if status == "expired":
            return jsonify({"error": "Comments can only be edited during the first two minutes after posting.", "code": "edit_window_expired"}), 409
        if status == "forbidden":
            return jsonify({"error": "You can only change your own comments."}), 403
        if status != "updated":
            return jsonify({"error": "Comment not found."}), 404
        invalidate_comments(updated.get("cat_id"))
        return jsonify({"message": "Comment updated.", "comment_id": comment_id, "comment": updated["comment"], "updated_at": updated["updated_at"]})
    except Exception:
        app.logger.exception("Could not change comment %s", comment_id)
        return jsonify({"error": "Could not change this comment. Please retry."}), 503


@app.route("/api/comments/<comment_id>", methods=["PUT", "DELETE"])
@require_auth
@limiter.limit("30 per minute", key_func=authenticated_user_rate_key)
def delete_comment(comment_id: str) -> Any:
    return mutate_comment(comment_id, delete=request.method == "DELETE")


@app.route("/api/admin/comments/<comment_id>", methods=["PUT"])
@require_auth
@limiter.limit("60 per minute", key_func=authenticated_user_rate_key)
def admin_edit_comment(comment_id: str) -> Any:
    return mutate_comment(comment_id, admin_only=True)


@app.route("/api/admin/comments/<comment_id>", methods=["DELETE", "POST"])
@require_auth
@limiter.limit("60 per minute", key_func=authenticated_user_rate_key)
def admin_delete_comment(comment_id: str) -> Any:
    return mutate_comment(comment_id, delete=True, admin_only=True)

@app.route("/api/notifications", methods=["GET"])
@require_auth
def get_notifications() -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    notifications: List[Dict[str, Any]] = []

    if supabase_admin:
        try:
            raw_res = getattr(
                supabase_admin.table("notifications").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(50).execute(),
                "data",
                [],
            )
            notifications = cast(List[Dict[str, Any]], raw_res) if isinstance(raw_res, list) else []
        except Exception:
            app.logger.exception("Could not load notifications for user %s", user_id)
            return jsonify({"error": "Notifications service is unavailable."}), 503
    elif ENABLE_DEMO_DATA:
        notifications = [n for n in MOCK_NOTIFICATIONS if str(n.get("user_id")) == user_id]
    else:
        return jsonify({"error": "Notifications service is unavailable."}), 503

    for n in notifications:
        n["actor_avatar"] = resolve_user_avatar(n.get("actor_id"), n.get("actor_name"), n.get("actor_avatar"))

    unread_count = sum(1 for n in notifications if not n.get("is_read", False))
    return jsonify({"notifications": notifications, "unread_count": unread_count}), 200

@app.route("/api/notifications/<notif_id>/read", methods=["POST"])
@require_auth
@limiter.limit("120 per minute", key_func=authenticated_user_rate_key)
def mark_notification_read(notif_id: str) -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    if supabase_admin:
        try:
            supabase_admin.table("notifications").update({"is_read": True}).eq("id", notif_id).eq("user_id", user_id).execute()
        except Exception:
            app.logger.exception("Failed to mark notification read")
            return jsonify({"error": "Could not update notification."}), 503
    elif not ENABLE_DEMO_DATA:
        return jsonify({"error": "Notifications service is unavailable."}), 503

    for n in MOCK_NOTIFICATIONS:
        if str(n.get("id")) == str(notif_id) and str(n.get("user_id")) == user_id:
            n["is_read"] = True
    return jsonify({"message": "Marked as read."}), 200

@app.route("/api/notifications/read-all", methods=["POST"])
@require_auth
@limiter.limit("60 per minute", key_func=authenticated_user_rate_key)
def mark_all_notifications_read() -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    if supabase_admin:
        if safe_db_update("notifications", {"is_read": True}, "user_id", user_id) is None:
            return jsonify({"error": "Could not update notifications."}), 503
    elif not ENABLE_DEMO_DATA:
        return jsonify({"error": "Notifications service is unavailable."}), 503

    for n in MOCK_NOTIFICATIONS:
        if str(n.get("user_id")) == user_id:
            n["is_read"] = True
    return jsonify({"message": "All marked as read."}), 200

@app.route("/api/notifications/clear-all", methods=["DELETE", "POST"])
@require_auth
@limiter.limit("30 per minute", key_func=authenticated_user_rate_key)
def clear_all_notifications() -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    if supabase_admin:
        try:
            supabase_admin.table("notifications").delete().eq("user_id", user_id).execute()
        except Exception:
            app.logger.exception("Failed to clear notifications for user %s", user_id)
            return jsonify({"error": "Could not clear notifications."}), 503
    elif not ENABLE_DEMO_DATA:
        return jsonify({"error": "Notifications service is unavailable."}), 503

    MOCK_NOTIFICATIONS[:] = [n for n in MOCK_NOTIFICATIONS if str(n.get("user_id")) != user_id]
    return jsonify({"message": "Notifications cleared."}), 200

@app.route("/api/user/avatar", methods=["POST"])
@require_auth
@limiter.limit("15 per hour", key_func=authenticated_user_rate_key)
def upload_user_avatar() -> Any:
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        file = request.files.get("avatar") or request.files.get("file")
        if not file or not getattr(file, "filename", None):
            return jsonify({"error": "No avatar image provided."}), 400
        if not supabase_admin:
            return jsonify({"error": "Profile service is unavailable."}), 503

        filename_str = str(getattr(file, "filename", "") or "")
        file_bytes: bytes = file.read()
        is_valid_img, img_err = validate_image_file(file_bytes, filename_str)
        if not is_valid_img:
            return jsonify({"error": img_err}), 400

        old_avatar_url = ""
        try:
            old_profile = getattr(supabase_admin.table("profiles").select("avatar_url").eq("id", user_id).limit(1).execute(), "data", []) or []
            if old_profile:
                old_avatar_url = str(old_profile[0].get("avatar_url") or "")
        except Exception as exc:
            app.logger.warning("Could not read previous avatar for %s: %s", user_id, exc)

        optimized_bytes, clean_ext, content_type = optimize_image_file(file_bytes, avatar=True)
        avatar_path = f"avatars/{user_id}/{uuid.uuid4()}.{clean_ext}"
        public_url = upload_file_to_storage(optimized_bytes, avatar_path, content_type, "avatars")

        if not public_url:
            return jsonify({"error": "Avatar storage is unavailable. Nothing was saved."}), 503

        profile_update = safe_db_update(
            "profiles",
            {"avatar_url": public_url, "updated_at": datetime.now(timezone.utc).isoformat()},
            "id",
            user_id,
        )
        if profile_update is None or not getattr(profile_update, "data", None):
            delete_file_from_storage(public_url, "avatars", allowed_prefix=f"avatars/{user_id}/")
            return jsonify({"error": "Could not save the avatar. The upload was rolled back."}), 503

        cache_user_avatar(user_id, public_url)
        invalidate_attribution(user_id)
        try:
            supabase_admin.auth.admin.update_user_by_id(user_id, {"user_metadata": {"avatar_url": public_url}})
        except Exception as exc:
            app.logger.warning("Could not synchronize avatar into auth metadata for %s: %s", user_id, exc)

        if old_avatar_url and old_avatar_url != public_url:
            delete_file_from_storage(old_avatar_url, "avatars", allowed_prefix=f"avatars/{user_id}/")

        return jsonify({"message": "Avatar uploaded successfully.", "avatar_url": public_url}), 200

    except Exception:
        app.logger.exception("Avatar upload failed")
        return jsonify({"error": "Avatar upload failed unexpectedly."}), 500

def signup_rate_key() -> str:
    """Separate signup limits by email so shared university Wi-Fi is not a problem."""
    raw_json: Any = request.get_json(silent=True)
    data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}
    email = str(data.get("email", "") or "").strip().lower()

    if email:
        email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
        return f"signup-email:{email_hash}"

    return f"signup-ip:{get_remote_address()}"

@app.route("/api/auth/register", methods=["POST"])
@limiter.limit("10 per hour", key_func=signup_rate_key)
@limiter.limit("30 per hour", key_func=get_remote_address)
def register_user() -> Any:
    try:
        if not supabase_auth:
            return jsonify({"error": "Registration service is not configured."}), 503

        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}
        email = clean_text(data.get("email"), max_length=254).lower()
        password = data.get("password", "")
        if not isinstance(password, str):
            return jsonify({"error": "Invalid password."}), 400
        display_name = clean_text(data.get("display_name"), max_length=40, fallback=email.split("@")[0] if "@" in email else "Cat Lover")
        phone = clean_text(data.get("phone"), max_length=30)
        bio = clean_text(data.get("bio"), max_length=150)
        avatar_url = sanitize_image_url(data.get("avatar_url"), fallback_name=display_name)

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return jsonify({"error": "Invalid email address."}), 400
        if len(password) < 8:
            return jsonify({"error": "Password must be at least 8 characters."}), 400
        if len(password) > 128:
            return jsonify({"error": "Password is too long."}), 400

        if supabase_admin:
            try:
                existing = getattr(supabase_admin.table("profiles").select("id").ilike("email", escape_like(email)).limit(1).execute(), "data", [])
                if existing:
                    return jsonify({"error": "An account with this email already exists."}), 409
            except Exception:
                app.logger.warning("Could not pre-check duplicate email during registration")

        options: Dict[str, Any] = {
            "data": {
                "display_name": display_name,
                "phone_number": phone,
                "bio": bio,
                "avatar_url": avatar_url,
            },
            "email_redirect_to": f"{public_site_url()}/login?confirmed=1",
        }
        signup_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY, options=ClientOptions(persist_session=False, auto_refresh_token=False))
        signup_credentials: Any = {
            "email": email,
            "password": password,
            "options": options,
        }
        result: Any = signup_client.auth.sign_up(signup_credentials)
        user = getattr(result, "user", None)
        session = getattr(result, "session", None)
        if user and getattr(user, "identities", None) == [] and session is None:
            return jsonify({"error": "An account with this email already exists."}), 409
        if not user:
            return jsonify({"error": "Registration did not complete. Please try again."}), 400

        return jsonify({
            "message": "Account created. Check your email to confirm it before signing in." if not session else "Account created successfully.",
            "email": email,
            "requires_email_confirmation": session is None,
        }), 201
    except Exception as exc:
        msg = str(exc)
        low = msg.lower()
        if "already registered" in low or "already exists" in low or "user already registered" in low:
            return jsonify({"error": "An account with this email already exists."}), 409
        if "rate limit" in low or "429" in low:
            return jsonify({"error": "Too many signup emails were requested. Please try again later."}), 429
        app.logger.exception("Registration failed")
        return jsonify({"error": "Registration failed. Please try again."}), 400

@app.route("/api/user/email", methods=["PUT"])
@require_auth
def update_user_email() -> Any:

    return jsonify({
        "error": "Email changes must use the verified Supabase email-change flow."
    }), 409

@app.route("/api/user/profile", methods=["PUT"])
@require_auth
@limiter.limit("30 per hour", key_func=authenticated_user_rate_key)
def sync_user_profile() -> Any:
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}

        if not supabase_admin and not ENABLE_DEMO_DATA:
            return jsonify({"error": "Profile service is unavailable."}), 503

        has_name = "display_name" in data
        if "avatar_url" in data:
            return jsonify({"error": "Avatar URLs cannot be set directly. Upload an image or request a default-avatar reset."}), 400
        reset_avatar = data.get("reset_avatar") is True
        has_avatar = reset_avatar
        has_phone = "phone" in data or "phone_number" in data
        has_bio = "bio" in data

        new_name = clean_text(data.get("display_name"), max_length=40) if has_name else ""
        if has_name and not new_name:
            return jsonify({"error": "Display name cannot be empty."}), 400

        auth_email = str(getattr(getattr(g, "user", None), "email", "") or "")
        default_avatar_name = new_name if has_name else (auth_email.split("@", 1)[0] if "@" in auth_email else "Cat Lover")
        new_avatar = generate_default_avatar(default_avatar_name) if has_avatar else ""
        raw_phone = data.get("phone") if "phone" in data else data.get("phone_number")
        new_phone = clean_text(raw_phone, max_length=30) if has_phone else ""
        new_bio = clean_text(data.get("bio"), max_length=150) if has_bio else ""

        old_avatar_url = ""
        if supabase_admin and has_avatar:
            try:
                old_rows = getattr(supabase_admin.table("profiles").select("avatar_url,display_name").eq("id", user_id).limit(1).execute(), "data", []) or []
                existing_name = ""
                if old_rows:
                    old_avatar_url = str(old_rows[0].get("avatar_url") or "")
                    existing_name = clean_text(old_rows[0].get("display_name"), max_length=40)
                avatar_name = new_name if has_name else (existing_name or "Cat Lover")
                new_avatar = generate_default_avatar(avatar_name)
            except Exception as exc:
                app.logger.warning("Could not read existing avatar during profile sync for %s: %s", user_id, exc)
                return jsonify({"error": "Could not reset avatar right now."}), 503

        if supabase_admin:
            profile_data: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
            if has_name:
                profile_data["display_name"] = new_name
            if has_avatar and new_avatar:
                profile_data["avatar_url"] = new_avatar
            if has_phone:
                profile_data["phone"] = new_phone or None
            if has_bio:
                profile_data["bio"] = new_bio or None
            profile_result = safe_db_update("profiles", profile_data, "id", user_id)
            if profile_result is None or not getattr(profile_result, "data", None):
                return jsonify({"error": "Could not save profile changes."}), 503

            try:
                auth_meta: Dict[str, Any] = {}
                if has_name:
                    auth_meta["display_name"] = new_name
                if has_avatar and new_avatar:
                    auth_meta["avatar_url"] = new_avatar
                if has_phone:
                    auth_meta["phone_number"] = new_phone
                if has_bio:
                    auth_meta["bio"] = new_bio
                if auth_meta:
                    supabase_admin.auth.admin.update_user_by_id(user_id, {"user_metadata": auth_meta})
            except Exception as exc:
                app.logger.warning("Auth metadata update failed for %s: %s", user_id, exc)

            if has_avatar and new_avatar and old_avatar_url and old_avatar_url != new_avatar:
                delete_file_from_storage(old_avatar_url, "avatars", allowed_prefix=f"avatars/{user_id}/")

        invalidate_attribution(user_id)

        if ENABLE_DEMO_DATA and not supabase_admin:
            for c in MOCK_CATS:
                if str(c.get("user_id")) == user_id:
                    if has_name:
                        c["user_name"] = new_name
                    if has_avatar and new_avatar:
                        c["user_avatar"] = new_avatar

        return jsonify({
            "message": "User profile synchronized successfully.",
            "display_name": new_name if has_name else None,
            "avatar_url": new_avatar if has_avatar else None,
            "phone": new_phone if has_phone else None,
            "bio": new_bio if has_bio else None,
        }), 200
    except Exception:
        app.logger.exception("Profile synchronization failed")
        return jsonify({"error": "Could not save profile changes right now."}), 500

@app.route("/api/admin/users/<user_id>/profile", methods=["PUT"])
@require_auth
@limiter.limit("30 per minute", key_func=authenticated_user_rate_key)
def admin_edit_user_profile(user_id: str) -> Any:
    try:
        if not is_admin_user(getattr(g, "user", None)):
            return jsonify({"error": "Admin access required."}), 403
        if not supabase_admin:
            return jsonify({"error": "Database service is unavailable."}), 503

        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}

        has_name = "display_name" in data
        has_avatar = "avatar_url" in data
        has_email = "email" in data
        has_phone = "phone" in data or "phone_number" in data
        has_bio = "bio" in data
        has_role = "role" in data

        new_name = clean_text(data.get("display_name"), max_length=40) if has_name else ""
        if has_name and not new_name:
            return jsonify({"error": "Display name cannot be empty."}), 400

        new_email = clean_text(data.get("email"), max_length=254).lower() if has_email else ""
        if has_email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", new_email):
            return jsonify({"error": "Invalid email address."}), 400

        raw_phone = data.get("phone") if "phone" in data else data.get("phone_number")
        new_phone = clean_text(raw_phone, max_length=30) if has_phone else ""
        new_bio = clean_text(data.get("bio"), max_length=150) if has_bio else ""
        new_role = clean_text(data.get("role"), max_length=20).lower() if has_role else ""
        if has_role and new_role not in {"user", "admin"}:
            return jsonify({"error": "Role must be 'user' or 'admin'."}), 400

        avatar_fallback_name = new_name or "Cat Lover"
        new_avatar = sanitize_image_url(data.get("avatar_url"), fallback_name=avatar_fallback_name) if has_avatar and data.get("avatar_url") else ""

        old_avatar_url = ""
        try:
            old_rows = getattr(
                supabase_admin.table("profiles").select("avatar_url").eq("id", user_id).limit(1).execute(),
                "data",
                [],
            ) or []
            if old_rows:
                old_avatar_url = str(old_rows[0].get("avatar_url") or "")
        except Exception as exc:
            app.logger.warning("Could not read old admin-edited avatar for %s: %s", user_id, exc)

        profile_data: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if has_name:
            profile_data["display_name"] = new_name
        if has_avatar and new_avatar:
            profile_data["avatar_url"] = new_avatar
        if has_phone:
            profile_data["phone"] = new_phone or None
        if has_bio:
            profile_data["bio"] = new_bio or None
        if has_role:
            profile_data["role"] = new_role

        auth_update: Dict[str, Any] = {}
        meta_update: Dict[str, Any] = {}
        if has_name:
            meta_update["display_name"] = new_name
        if has_avatar and new_avatar:
            meta_update["avatar_url"] = new_avatar
        if has_phone:
            meta_update["phone_number"] = new_phone
        if has_bio:
            meta_update["bio"] = new_bio
        if meta_update:
            auth_update["user_metadata"] = meta_update
        if has_role:
            auth_update["app_metadata"] = {"role": new_role}
        if has_email:
            current_user = supabase_admin.auth.admin.get_user_by_id(user_id).user
            if new_email != str(current_user.email or "").lower():
                return jsonify({"error": "Users must confirm email changes from their own account settings."}), 409

        if auth_update:
            try:
                supabase_admin.auth.admin.update_user_by_id(user_id, cast(Any, auth_update))
            except Exception:
                app.logger.exception("Admin Auth update failed for user %s", user_id)
                return jsonify({"error": "Could not update the account. Please try again."}), 503

        updated_profile = safe_db_update("profiles", profile_data, "id", user_id)
        if updated_profile is None or not getattr(updated_profile, "data", None):
            return jsonify({"error": "Could not update the profile record."}), 503
        if has_avatar and new_avatar:
            cache_user_avatar(user_id, new_avatar)
            if old_avatar_url and old_avatar_url != new_avatar:
                delete_file_from_storage(old_avatar_url, "avatars", allowed_prefix=f"avatars/{user_id}/")

        invalidate_attribution(user_id)
        return jsonify({
            "message": "User profile updated by admin successfully.",
            "user_id": user_id,
            "display_name": new_name if has_name else None,
            "email": new_email if has_email else None,
            "phone": new_phone if has_phone else None,
            "role": new_role if has_role else None,
        }), 200
    except Exception:
        app.logger.exception("Admin user profile update failed for %s", user_id)
        return jsonify({"error": "Could not update this user right now."}), 500

@app.route("/api/admin/users/<user_id>/force-delete", methods=["DELETE", "POST"])
@require_auth
@limiter.limit("10 per hour", key_func=authenticated_user_rate_key)
def admin_force_delete_user(user_id: str) -> Any:
    try:
        if not is_admin_user(getattr(g, "user", None)):
            return jsonify({"error": "Admin access required."}), 403
        admin = supabase_admin
        if admin is None and not ENABLE_DEMO_DATA:
            return jsonify({"error": "Database service is unavailable."}), 503

        if str(getattr(g.user, "id", "")) == user_id:
            return jsonify({"error": "You cannot delete your own administrator account."}), 409
        if admin is not None:
            try:
                user_cats = fetch_all_rows(lambda: admin.table("cats").select("id,image_url").eq("user_id", user_id).order("id"))
                profile_response = admin.table("profiles").select("avatar_url").eq("id", user_id).limit(1).execute()
                profile_rows = as_row_list(getattr(profile_response, "data", None))
                admin.auth.admin.delete_user(user_id)
                for cat in user_cats:
                    delete_file_from_storage(str(cat.get("image_url", "")), STORAGE_BUCKET, allowed_prefix=f"{user_id}/")
                    cache_delete(make_cache_key("cat", cat.get("id", "")))
                if profile_rows:
                    delete_file_from_storage(str(profile_rows[0].get("avatar_url", "")), "avatars", allowed_prefix=f"avatars/{user_id}/")
            except Exception:
                app.logger.exception("Admin failed to delete user %s", user_id)
                return jsonify({"error": "Could not delete this account."}), 503

        user_cat_ids = {str(c.get("id")) for c in MOCK_CATS if str(c.get("user_id")) == str(user_id)}
        MOCK_CATS[:] = [c for c in MOCK_CATS if str(c.get("user_id")) != str(user_id)]
        MOCK_COMMENTS[:] = [cm for cm in MOCK_COMMENTS if str(cm.get("user_id")) != str(user_id) and str(cm.get("cat_id")) not in user_cat_ids]
        MOCK_LIKES[:] = [l for l in MOCK_LIKES if str(l.get("user_id")) != str(user_id) and str(l.get("cat_id")) not in user_cat_ids]
        MOCK_NOTIFICATIONS[:] = [n for n in MOCK_NOTIFICATIONS if str(n.get("user_id")) != str(user_id) and str(n.get("actor_id")) != str(user_id) and str(n.get("cat_id")) not in user_cat_ids]
        user_avatar_cache.pop(user_id, None)
        for deleted_cat_id in user_cat_ids:
            cache_delete(make_cache_key("cat", deleted_cat_id))
        invalidate_cat_content(user_id=user_id)

        return jsonify({"message": "User and all associated data deleted successfully.", "user_id": user_id}), 200
    except Exception:
        app.logger.exception("Unexpected force-delete failure for user %s", user_id)
        return jsonify({"error": "Could not delete this account right now."}), 500

@app.route("/api/user/<user_id>/profile", methods=["GET"])
def get_public_profile(user_id: str) -> Any:
    profile_key = make_cache_key("profile", user_id, cache_counter_value("cats"))
    cached_profile = cache_get_dict(profile_key)
    if cached_profile is not None:
        return jsonify(cached_profile), 200

    cats: List[Dict[str, Any]] = []
    user_name = ""
    user_avatar = ""
    user_bio = ""
    user_found = False

    admin = supabase_admin
    if admin is not None:
        try:
            p_res = admin.table("profiles").select("id,display_name,bio,avatar_url").eq("id", user_id).limit(1).execute()
            p_data = as_row_list(getattr(p_res, "data", None))
            if p_data:
                profile = p_data[0]
                user_found = True
                user_name = clean_text(profile.get("display_name"), max_length=40, fallback="Cat Lover")
                user_avatar = sanitize_image_url(profile.get("avatar_url"), fallback_name=user_name)
                user_bio = clean_text(profile.get("bio"), max_length=150)

            cats = fetch_all_rows(lambda: admin.table("cats").select("*").eq("user_id", user_id).order("created_at", desc=True).order("id"))
            if cats:
                user_found = True

            if not user_found:
                try:
                    u_obj: Any = admin.auth.admin.get_user_by_id(user_id)
                    u_data: Any = getattr(u_obj, "user", None) or getattr(u_obj, "data", None)
                    if u_data:
                        user_found = True
                        auth_email = str(getattr(u_data, "email", "") or "")
                        if isinstance(u_data, dict):
                            u_data_map = cast(Dict[str, Any], u_data)
                            auth_email = str(u_data_map.get("email") or auth_email)
                        email_local = auth_email.split("@", 1)[0] if "@" in auth_email else "Cat Lover"
                        user_name = clean_text(email_local, max_length=40, fallback="Cat Lover")
                        user_avatar = generate_default_avatar(user_name)
                        user_bio = ""
                except Exception:
                    pass
        except Exception:
            app.logger.exception("Could not load public profile %s", user_id)
            return jsonify({"error": "Profile service is unavailable."}), 503

    elif not ENABLE_DEMO_DATA:
        return jsonify({"error": "Profile service is unavailable."}), 503

    if not user_found and ENABLE_DEMO_DATA:
        mock_cats = [
            c for c in MOCK_CATS
            if str(c.get("user_id", "")).lower() == str(user_id).lower()
            or str(c.get("user_name", "")).lower() == str(user_id).lower()
        ]
        if mock_cats:
            cats = [dict(c) for c in mock_cats]
            user_found = True
        elif user_id in ("user-mock-1", "user-mock-2", "user-mock-3", "WhiskersFan", "CatMaster", "FelineKing"):
            user_found = True
            user_name = user_id
            user_avatar = generate_default_avatar(user_name)

    if not user_found:
        return jsonify({"error": "User not found"}), 404

    for c in cats:
        c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))
    if not user_name and cats:
        user_name = clean_text(cats[0].get("user_name"), max_length=40, fallback="Cat Lover")
    if not user_avatar and cats:
        user_avatar = sanitize_image_url(cats[0].get("user_avatar"), fallback_name=user_name or "Cat Lover")
    if not user_name:
        user_name = "Cat Lover"
    if not user_avatar:
        user_avatar = resolve_user_avatar(user_id, user_name, None)

    payload: Dict[str, Any] = {
        "user_id": user_id,
        "cats_count": len(cats),
        "user_name": user_name,
        "user_avatar": user_avatar,
        "bio": user_bio,
        "total_likes": sum(int(c.get("likes_count", 0) or 0) for c in cats),
        "cats": cats,
    }
    cache_set(profile_key, payload, PROFILE_CACHE_TTL)
    return jsonify(payload), 200

@app.route("/api/user/my-cats", methods=["GET"])
@require_auth
def get_my_cats() -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    admin = supabase_admin
    if admin is None:
        if ENABLE_DEMO_DATA:
            return jsonify({"cats": [c for c in MOCK_CATS if str(c.get("user_id")) == user_id]}), 200
        return jsonify({"error": "Database service is unavailable."}), 503

    try:
        cats = fetch_all_rows(lambda: admin.table("cats").select("*").eq("user_id", user_id).order("created_at", desc=True).order("id"))
        return jsonify({"cats": cats}), 200
    except Exception:
        app.logger.exception("Could not load cats for user %s", user_id)
        return jsonify({"error": "Could not load your cats right now."}), 503

@app.route("/api/user/liked-cats", methods=["GET"])
@require_auth
def get_user_liked_cats() -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    admin = supabase_admin
    if admin is None:
        if ENABLE_DEMO_DATA:
            liked = [str(l.get("cat_id")) for l in MOCK_LIKES if str(l.get("user_id")) == user_id]
            return jsonify({"liked_cat_ids": liked}), 200
        return jsonify({"error": "Database service is unavailable."}), 503

    try:
        raw_data = fetch_all_rows(lambda: admin.table("likes").select("cat_id").eq("user_id", user_id).order("id"))
        liked_cat_ids = [str(item.get("cat_id")) for item in raw_data if item.get("cat_id")]
        return jsonify({"liked_cat_ids": liked_cat_ids}), 200
    except Exception:
        app.logger.exception("Could not load liked cats for user %s", user_id)
        return jsonify({"error": "Could not load your liked cats right now."}), 503

@app.route("/api/cats/<cat_id>/favorite", methods=["PUT", "DELETE"])
@require_auth
@limiter.limit("60 per minute", key_func=authenticated_user_rate_key)
def set_favorite(cat_id: str) -> Any:
    admin = supabase_admin
    if admin is None:
        return jsonify({"error": "Favorites service is unavailable."}), 503
    user_id = str(getattr(g.user, "id", ""))
    saved = request.method == "PUT"
    try:
        if saved:
            cat = get_db_row(admin.table("cats").select("id").eq("id", cat_id))
            if not cat:
                return jsonify({"error": "Cat not found."}), 404
            admin.table("favorites").upsert(
                {"cat_id": cat_id, "user_id": user_id},
                on_conflict="user_id,cat_id", ignore_duplicates=True,
            ).execute()
        else:
            admin.table("favorites").delete().eq("user_id", user_id).eq("cat_id", cat_id).execute()
        return jsonify({"cat_id": cat_id, "saved": saved}), 200
    except Exception:
        app.logger.exception("Could not update favorite for user %s", user_id)
        return jsonify({"error": "Could not update your favorites. Please try again."}), 503

@app.route("/api/user/favorite-ids", methods=["GET"])
@require_auth
def get_favorite_ids() -> Any:
    admin = supabase_admin
    if admin is None:
        return jsonify({"error": "Favorites service is unavailable."}), 503
    user_id = str(getattr(g.user, "id", ""))
    try:
        rows = fetch_all_rows(lambda: admin.table("favorites").select("cat_id").eq("user_id", user_id).order("cat_id"))
        return jsonify({"favorite_cat_ids": [str(row["cat_id"]) for row in rows]}), 200
    except Exception:
        app.logger.exception("Could not load favorites for user %s", user_id)
        return jsonify({"error": "Could not load your favorites. Please try again."}), 503

@app.route("/api/user/favorites", methods=["GET"])
@require_auth
def get_favorites() -> Any:
    admin = supabase_admin
    if admin is None:
        return jsonify({"error": "Favorites service is unavailable."}), 503
    user_id = str(getattr(g.user, "id", ""))
    page = max(1, min(request.args.get("page", 1, type=int) or 1, 10000))
    page_size = 24
    try:
        result = (admin.table("favorites").select("cat_id,cats!inner(*)")
                  .eq("user_id", user_id).order("created_at", desc=True).order("cat_id")
                  .range((page - 1) * page_size, page * page_size).execute())
        rows = as_row_list(getattr(result, "data", None))
        cats: List[Dict[str, Any]] = []
        for row in rows[:page_size]:
            raw_cat: Any = row.get("cats")
            if isinstance(raw_cat, dict):
                cat = dict(cast(Dict[str, Any], raw_cat))
                cat["user_avatar"] = resolve_user_avatar(cat.get("user_id"), cat.get("user_name"), cat.get("user_avatar"))
                cats.append(cat)
        return jsonify({"cats": cats, "page": page, "has_next": len(rows) > page_size}), 200
    except Exception:
        app.logger.exception("Could not load favorite cats for user %s", user_id)
        return jsonify({"error": "Could not load your favorites. Please try again."}), 503

@app.route("/api/admin/overview", methods=["GET"])
@require_auth
def admin_overview() -> Any:
    try:
        is_admin = is_admin_user(getattr(g, "user", None))
        if not is_admin:
            user_email = str(getattr(getattr(g, "user", None), "email", "") or "").lower()
            return jsonify({"error": f"Admin access restricted. Your account '{user_email}' is not configured as admin."}), 403

        admin = supabase_admin
        if admin is None:
            return jsonify({"error": "Admin service is unavailable."}), 503

        cats: List[Dict[str, Any]] = []
        try:
            cats = fetch_all_rows(lambda: admin.table("cats").select("*").order("created_at", desc=True).order("id"))
        except Exception as ce:
            app.logger.warning("Admin overview cats query failed: %s", ce)
            return jsonify({"error": "Could not load the admin dashboard."}), 503

        if not cats and ENABLE_DEMO_DATA:
            cats = list(MOCK_CATS)

        for c in cats:
            c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))

        users_dict: Dict[str, Dict[str, Any]] = {}

        try:
            raw_users_list: List[Any] = []
            auth_page = 1
            while True:
                auth_users_res = admin.auth.admin.list_users(page=auth_page, per_page=1000)
                batch_value: Any = (
                    getattr(auth_users_res, "users", None)
                    or getattr(auth_users_res, "data", None)
                    or auth_users_res
                )
                if not isinstance(batch_value, list):
                    raise ValueError("Unexpected user response")
                batch = cast(List[Any], batch_value)
                raw_users_list.extend(batch)
                if len(batch) < 1000:
                    break
                auth_page += 1

            for u in raw_users_list:
                uid = str(getattr(u, "id", "") or "")
                if not uid:
                    continue

                u_email = str(getattr(u, "email", "") or "")
                u_meta_value: Any = getattr(u, "user_metadata", {}) or {}
                u_meta = cast(Dict[str, Any], u_meta_value) if isinstance(u_meta_value, dict) else {}
                u_app_meta_value: Any = getattr(u, "app_metadata", {}) or {}
                u_app_meta = cast(Dict[str, Any], u_app_meta_value) if isinstance(u_app_meta_value, dict) else {}

                disp_name = str(u_meta.get("display_name", "")).strip() or u_email.split("@")[0] or "Cat Lover"
                avatar_url = str(u_meta.get("avatar_url", "")).strip() or resolve_user_avatar(uid, disp_name, None)
                phone_val = str(u_meta.get("phone_number", "") or getattr(u, "phone", "") or "").strip()
                role_val = "admin" if (
                    u_email.lower() in [e.strip().lower() for e in ADMIN_EMAIL_CONFIG.split(",") if e.strip()]
                    or str(u_app_meta.get("role", "")).lower() == "admin"
                ) else "user"

                users_dict[uid] = {
                    "user_id": uid,
                    "user_name": disp_name,
                    "display_name": disp_name,
                    "user_avatar": avatar_url,
                    "avatar_url": avatar_url,
                    "email": u_email,
                    "phone": phone_val,
                    "phone_number": phone_val,
                    "role": role_val,
                    "created_at": str(getattr(u, "created_at", "") or ""),
                    "cats_count": 0,
                    "cat_count": 0,
                    "total_likes": 0
                }
        except Exception as ue:
            app.logger.warning("Admin auth list users failed: %s", ue)
            return jsonify({"error": "Could not load registered users."}), 503

        for profile in fetch_all_rows(lambda: admin.table("profiles").select("id,display_name,avatar_url,phone").order("id")):
            entry = users_dict.get(str(profile["id"]))
            if entry:
                name = clean_text(profile.get("display_name"), max_length=40, fallback="Cat Lover")
                avatar = sanitize_image_url(profile.get("avatar_url"), fallback_name=name)
                entry.update(user_name=name, display_name=name, user_avatar=avatar, avatar_url=avatar,
                             phone=profile.get("phone") or "", phone_number=profile.get("phone") or "")

        for c in cats:
            uid = str(c.get("user_id", ""))
            uname = str(c.get("user_name", "Cat Lover"))
            uavatar = str(c.get("user_avatar", "")) or generate_default_avatar(uname)
            if uid:
                if uid not in users_dict:
                    users_dict[uid] = {
                        "user_id": uid,
                        "user_name": uname,
                        "display_name": uname,
                        "user_avatar": uavatar,
                        "avatar_url": uavatar,
                        "email": "",
                        "phone": "—",
                        "role": "user",
                        "cats_count": 0,
                        "cat_count": 0,
                        "total_likes": 0
                    }
                users_dict[uid]["cats_count"] += 1
                users_dict[uid]["cat_count"] += 1
                users_dict[uid]["total_likes"] += int(c.get("likes_count", 0) or 0)

        for mc in (MOCK_CATS if ENABLE_DEMO_DATA else []):
            muid = str(mc.get("user_id"))
            if muid not in users_dict:
                users_dict[muid] = {
                    "user_id": muid,
                    "user_name": str(mc.get("user_name")),
                    "display_name": str(mc.get("user_name")),
                    "user_avatar": str(mc.get("user_avatar")),
                    "avatar_url": str(mc.get("user_avatar")),
                    "email": f"{str(mc.get('user_name')).lower()}@example.com",
                    "phone": "+998 90 123 45 67",
                    "role": "user",
                    "cats_count": 1,
                    "cat_count": 1,
                    "total_likes": int(mc.get("likes_count", 0) or 0)
                }

        user_list = list(users_dict.values())
        user_list.sort(key=lambda u: u.get("total_likes", 0), reverse=True)

        all_comments: List[Dict[str, Any]] = []
        try:
            comments_response = admin.table("comments").select("*").order("created_at", desc=True).limit(200).execute()
            all_comments = as_row_list(getattr(comments_response, "data", None))
        except Exception as ce:
            app.logger.warning("Admin overview comments query failed: %s", ce)

        if not all_comments and ENABLE_DEMO_DATA:
            all_comments = list(MOCK_COMMENTS)

        count_method: Any = "exact"
        count_response = admin.table("comments").select("id", count=count_method, head=True).execute()
        comments_count = int(getattr(count_response, "count", 0) or 0)
        return jsonify({
            "total_cats": len(cats),
            "total_likes": sum(int(c.get("likes_count", 0) or 0) for c in cats),
            "total_users": len(users_dict),
            "total_comments": comments_count,
            "cats": cats,
            "users": user_list,
            "comments": all_comments
        }), 200

    except Exception:
        app.logger.exception("Failed to load admin overview")
        return jsonify({"error": "Failed to load admin overview."}), 500

def new_auth_client() -> Any:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError("Authentication is not configured")
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY, options=ClientOptions(persist_session=False, auto_refresh_token=False))


def request_json() -> Dict[str, Any]:
    value = request.get_json(silent=True)
    return cast(Dict[str, Any], value) if isinstance(value, dict) else {}


def email_rate_key() -> str:
    email = clean_text(request_json().get("email"), max_length=254).lower()
    return "email:" + hashlib.sha256(email.encode()).hexdigest()


@app.route("/auth/callback")
def oauth_callback_page() -> str:
    return render_template("auth_callback.html")


@app.route("/api/auth/options")
@limiter.limit("60 per minute")
def auth_options() -> Any:
    options: Dict[str, bool] = {"google_enabled": GOOGLE_AUTH_ENABLED}
    if PHONE_AUTH_ENABLED:
        options["phone_enabled"] = True
    return jsonify(options)


@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("10 per minute")
@limiter.limit("30 per hour", key_func=email_rate_key)
def password_login() -> Any:
    data = request_json()
    email = clean_text(data.get("email"), max_length=254).lower()
    password = data.get("password")
    if not email or not isinstance(password, str) or not 1 <= len(password) <= 128:
        return jsonify({"error": "Enter your email and password."}), 400
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return jsonify({"error": "Sign-in is unavailable."}), 503
    try:
        result = new_auth_client().auth.sign_in_with_password({"email": email, "password": password})
        session = getattr(result, "session", None)
        if not session:
            return jsonify({"error": "Sign-in failed. Check your details and email confirmation."}), 401
        return jsonify({"access_token": session.access_token, "refresh_token": session.refresh_token})
    except Exception as exc:
        status = getattr(exc, "status", None)
        if str(status) == "429":
            return jsonify({"error": "Too many sign-in attempts. Please try again later."}), 429
        return jsonify({"error": "Sign-in failed. Check your details and email confirmation."}), 401


@app.route("/api/auth/password-reset", methods=["POST"])
@limiter.limit("5 per hour", key_func=email_rate_key)
@limiter.limit("15 per hour")
def request_password_reset() -> Any:
    email = clean_text(request_json().get("email"), max_length=254).lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"error": "Enter a valid email address."}), 400
    try:
        new_auth_client().auth.reset_password_email(email, {"redirect_to": f"{public_site_url()}/reset-password"})
    except Exception as exc:
        # Do not disclose whether a registered address exists.
        app.logger.warning("Password reset delivery failed (%s)", type(exc).__name__)
        return jsonify({"error": "Password reset is temporarily unavailable. Please try again later."}), 503
    return jsonify({"message": "If an account exists for that email, a reset link has been sent."})


@app.route("/api/auth/bootstrap", methods=["POST"])
@require_auth
@limiter.limit("30 per minute", key_func=authenticated_user_rate_key)
def bootstrap_profile() -> Any:
    if not supabase_admin:
        return jsonify({"error": "Profile service is unavailable."}), 503
    user = g.user
    try:
        ensure_auth_profile(user)
        return jsonify({"ready": True, "user_id": str(user.id)})
    except Exception:
        app.logger.exception("Could not initialize profile")
        return jsonify({"error": "Could not initialize your profile. Please retry."}), 503


@app.route("/api/user/security", methods=["PUT"])
@require_auth
@limiter.limit("5 per hour", key_func=authenticated_user_rate_key)
@limiter.limit("15 per hour")
def update_account_security() -> Any:
    data = request_json()
    action = data.get("action")
    password = data.get("current_password")
    if action not in {"email", "password", "unlink_google"} or not isinstance(password, str) or not 1 <= len(password) <= 128:
        return jsonify({"error": "Current password is required."}), 400
    value = data.get("value", "")
    if not isinstance(value, str):
        return jsonify({"error": "Invalid account details."}), 400
    if action == "email":
        value = value.strip().lower()
        if len(value) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            return jsonify({"error": "Enter a valid email address."}), 400
    elif action == "password" and not 8 <= len(value) <= 128:
        return jsonify({"error": "Password must be between 8 and 128 characters."}), 400
    client = None
    verified = False
    try:
        client = new_auth_client()
        result = client.auth.sign_in_with_password({"email": str(g.user.email), "password": password})
        verified = bool(getattr(result, "session", None))
        if not verified or str(getattr(getattr(result, "user", None), "id", "")) != str(g.user.id):
            return jsonify({"error": "Re-authentication failed."}), 401
        verified = True
        if action == "unlink_google":
            identities = client.auth.get_user_identities().identities
            google = next((identity for identity in identities if identity.provider == "google"), None)
            if not google or not any(identity.provider == "email" for identity in identities) or len(identities) < 2:
                return jsonify({"error": "Keep a verified password sign-in before disconnecting Google."}), 409
            client.auth.unlink_identity(google)
            return jsonify({"message": "Google disconnected. You can still sign in with your password."})
        attrs: Any = {str(action): value}
        options: Any = {"email_redirect_to": f"{public_site_url()}/profile?email_confirmed=1"}
        updated = client.auth.update_user(attrs, options) if action == "email" else client.auth.update_user(attrs)
        immediate = action == "email" and str(getattr(updated.user, "email", "")).lower() == value
        message = "Password updated." if action == "password" else "Confirm the change using the links sent to your current and new inboxes."
        if immediate:
            message = "Email changed. Confirmation is disabled in the authentication provider settings."
        return jsonify({"message": message, "requires_confirmation": action == "email" and not immediate})
    except Exception as exc:
        app.logger.warning("Account security update rejected (%s)", type(exc).__name__)
        return jsonify({"error": "Could not update your account. Check your current password and try again."}), 400
    finally:
        if client is not None and verified:
            try:
                client.auth.sign_out({"scope": "local"})
            except Exception:
                pass


def normalize_phone(value: Any) -> Optional[str]:
    if not isinstance(value, str) or len(value) > 40:
        return None
    phone = re.sub(r"[\s()\-]", "", value)
    return phone if re.fullmatch(r"\+[1-9]\d{7,14}", phone) else None


def phone_rate_key() -> str:
    phone = normalize_phone(request_json().get("phone")) or "invalid"
    return "phone:" + hashlib.sha256(phone.encode()).hexdigest()


def ensure_auth_profile(user: Any) -> None:
    if not supabase_admin:
        raise RuntimeError("Profile service unavailable")
    raw = getattr(user, "user_metadata", {})
    meta = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    name = clean_text(meta.get("display_name") or meta.get("full_name") or meta.get("name"), max_length=40, fallback="Cat Lover")
    supabase_admin.table("profiles").upsert({
        "id": str(user.id), "email": str(getattr(user, "email", "") or "") or None,
        "display_name": name, "avatar_url": generate_default_avatar(name), "role": "user",
    }, on_conflict="id", ignore_duplicates=True).execute()
    invalidate_profile_cache(user.id)


@app.route("/api/auth/phone/send", methods=["POST"])
@limiter.limit("1 per minute; 5 per hour", key_func=phone_rate_key)
@limiter.limit("15 per hour")
@limiter.limit("100 per day", key_func=lambda: "phone-sms-global")
def send_phone_code() -> Any:
    if not PHONE_AUTH_ENABLED:
        return jsonify({"error": "Phone sign-in is not available yet."}), 503
    data = request_json()
    phone = normalize_phone(data.get("phone"))
    mode = data.get("mode")
    if not phone or mode not in {"login", "register"}:
        return jsonify({"error": "Enter your phone number with its country code, for example +998901234567."}), 400
    name = clean_text(data.get("display_name"), max_length=40, fallback="Cat Lover")
    options: Dict[str, Any] = {"should_create_user": mode == "register", "channel": "sms"}
    if mode == "register":
        options["data"] = {"display_name": name}
    try:
        new_auth_client().auth.sign_in_with_otp(cast(Any, {"phone": phone, "options": options}))
        return jsonify({"message": "Check your phone for a verification code.", "retry_after": 60})
    except Exception as exc:
        app.logger.warning("Phone OTP request failed (%s)", type(exc).__name__)
        code = str(getattr(exc, "code", ""))
        if code in {"over_sms_send_rate_limit", "over_request_rate_limit"}:
            return jsonify({"error": "Too many code requests. Please try again later."}), 429
        if code in {"provider_disabled", "sms_send_failed", "unexpected_failure"}:
            return jsonify({"error": "SMS sign-in is temporarily unavailable."}), 503
        return jsonify({"error": "Could not send a code. Check the number. New users should choose Create account."}), 400


@app.route("/api/auth/phone/verify", methods=["POST"])
@limiter.limit("5 per 10 minutes", key_func=phone_rate_key)
@limiter.limit("30 per hour")
def verify_phone_code() -> Any:
    if not PHONE_AUTH_ENABLED:
        return jsonify({"error": "Phone sign-in is not available yet."}), 503
    data = request_json()
    phone = normalize_phone(data.get("phone"))
    token = data.get("token")
    if not phone or not isinstance(token, str) or not re.fullmatch(r"\d{6}", token):
        return jsonify({"error": "Enter a valid phone number and the six-digit SMS code."}), 400
    try:
        result = new_auth_client().auth.verify_otp({"phone": phone, "token": token, "type": "sms"})
    except Exception as exc:
        app.logger.info("Phone verification rejected (%s)", type(exc).__name__)
        return jsonify({"error": "This code is invalid or expired. Request a new code and try again."}), 400
    auth_session = getattr(result, "session", None)
    user = getattr(result, "user", None)
    verified_phone = str(getattr(user, "phone", "") or "").lstrip("+")
    if not auth_session or not user or not getattr(user, "phone_confirmed_at", None) or verified_phone != phone.lstrip("+"):
        return jsonify({"error": "Phone verification did not complete."}), 401
    try:
        ensure_auth_profile(user)
    except Exception:
        app.logger.exception("Verified phone profile could not be initialized")
        return jsonify({"error": "Your number was verified, but your profile could not load. Please sign in again."}), 503
    return jsonify({"access_token": auth_session.access_token, "refresh_token": auth_session.refresh_token})


@app.route("/api/user/comment-likes", methods=["GET"])
@require_auth
@limiter.limit("120 per minute", key_func=authenticated_user_rate_key)
def get_comment_likes() -> Any:
    ids = request.args.get("ids", "").split(",")
    if not 1 <= len(ids) <= 100:
        return jsonify({"error": "Request between 1 and 100 comments."}), 400
    try:
        ids = list(dict.fromkeys(str(uuid.UUID(value)) for value in ids))
    except ValueError:
        return jsonify({"error": "Invalid comment IDs."}), 400
    if not supabase_admin:
        return jsonify({"error": "Comment likes are unavailable."}), 503
    try:
        result = supabase_admin.table("comment_likes").select("comment_id").eq("user_id", str(g.user.id)).in_("comment_id", ids).execute()
        return jsonify({"liked_comment_ids": [row["comment_id"] for row in as_row_list(result.data)]})
    except Exception:
        app.logger.exception("Could not load comment like state")
        return jsonify({"error": "Comment likes are unavailable."}), 503


@app.route("/api/comments/<comment_id>/like", methods=["PUT", "DELETE"])
@require_auth
@limiter.limit("120 per minute", key_func=authenticated_user_rate_key)
def set_comment_like(comment_id: str) -> Any:
    if not supabase_admin:
        return jsonify({"error": "Comment likes are unavailable."}), 503
    try:
        comment_id = str(uuid.UUID(comment_id))
    except ValueError:
        return jsonify({"error": "Invalid comment ID."}), 400
    try:
        result = supabase_admin.rpc("set_comment_like", {"p_comment_id": comment_id, "p_user_id": str(g.user.id), "p_liked": request.method == "PUT"}).execute()
        rows = as_row_list(result.data)
        if not rows:
            return jsonify({"error": "Comment not found."}), 404
        row = rows[0]
        invalidate_comments(row.get("cat_id"))
        return jsonify({"liked": bool(row["liked"]), "likes_count": int(row["likes_count"])})
    except Exception:
        app.logger.exception("Could not change comment like")
        return jsonify({"error": "Could not change the comment like. Please retry."}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=env_flag("FLASK_DEBUG", False))
