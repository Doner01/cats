import os
import re
import uuid
import secrets
from collections import OrderedDict
from io import BytesIO
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, cast
from urllib.parse import quote, urlparse

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, g, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from supabase import create_client, Client, ClientOptions
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
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024                                
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["RATELIMIT_HEADERS_ENABLED"] = True

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
RATE_LIMIT_STORAGE_URI: str = (os.getenv("RATE_LIMIT_STORAGE_URI") or "memory://").strip()
try:
    TRUST_PROXY_HOPS: int = max(0, int(os.getenv("TRUST_PROXY_HOPS", "0")))
except ValueError:
    TRUST_PROXY_HOPS = 0
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
)
if IS_PRODUCTION and RATE_LIMIT_STORAGE_URI.startswith("memory://"):
    app.logger.warning("RATE_LIMIT_STORAGE_URI uses memory:// in production; use shared Redis for multi-worker/multi-replica deployments.")

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
if R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY:
    try:
        import boto3
        from botocore.config import Config
        r2_client = boto3.client(
            service_name="s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=Config(signature_version="s3v4")
        )
        app.logger.info("Cloudflare R2 Storage client initialized successfully")
    except Exception as r2_err:
        app.logger.warning("Failed to init Cloudflare R2 client: %s", r2_err)

STORAGE_BUCKET: str = "cat-images"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "jfif", "gif"}
MAX_FILE_SIZE: int = 5 * 1024 * 1024        

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
                                              
    if r2_client and R2_BUCKET_NAME and R2_PUBLIC_DOMAIN:
        try:
            r2_client.put_object(
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

        if r2_client and R2_PUBLIC_DOMAIN:
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

        if not backend and supabase_admin and SUPABASE_URL:
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
            r2_client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
        else:
            supabase_admin.storage.from_(bucket_name).remove([key])
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

    if user_id and str(user_id) in user_avatar_cache:
        key = str(user_id)
        cached = user_avatar_cache[key]
        user_avatar_cache.move_to_end(key)
        return cached

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
    """
    user_id = str(getattr(user, "id", "") or "")
    email = str(getattr(user, "email", "") or "")

    fallback_name = clean_text(email.split("@")[0] if "@" in email else "Cat Lover", max_length=40, fallback="Cat Lover")
    fallback_avatar = generate_default_avatar(fallback_name)

    if supabase_admin and user_id:
        try:
            result = supabase_admin.table("profiles").select("display_name,avatar_url").eq("id", user_id).limit(1).execute()
            rows = getattr(result, "data", []) or []
            if rows:
                row = rows[0]
                name = clean_text(row.get("display_name"), max_length=40, fallback=fallback_name)
                avatar = sanitize_image_url(row.get("avatar_url"), fallback_name=name)
                return user_id, name, avatar
        except Exception as exc:
            app.logger.warning("Could not load canonical profile identity for %s: %s", user_id, exc)

    return user_id, fallback_name, fallback_avatar

def public_site_url() -> str:

    return PUBLIC_SITE_URL or request.url_root.rstrip("/")

def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

def fetch_all_rows(query_factory: Callable[[], Any]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    while True:
        rows = query_factory().range(len(result), len(result) + 499).execute().data or []
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

@app.before_request
def assign_request_id() -> None:
    supplied = (request.headers.get("X-Request-ID") or "").strip()
    g.request_id = supplied if re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", supplied) else str(uuid.uuid4())
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
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' https: data: blob:; "
        "font-src 'self'; connect-src 'self' https: wss:; "
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
        return jsonify({"error": "Upload is too large. Maximum request size is 6MB."}), 413
    return Response("Request is too large.", status=413, mimetype="text/plain")

@app.errorhandler(HTTPException)
def http_error(error: HTTPException) -> Any:
    if request.path.startswith("/api/"):
        response = error.get_response()
        response.data = app.json.dumps({"error": error.name})
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
    return {"supabase_url": SUPABASE_URL, "supabase_anon_key": SUPABASE_ANON_KEY}

@app.route("/livez")
def livez() -> Any:
    return jsonify({"status": "ok"})

@app.route("/healthz")
def healthz() -> Any:
    ready = bool(supabase_auth and supabase_admin)
    if ready:
        try:
            supabase_admin.table("profiles").select("id").limit(1).execute()
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
    top_cat = None
    unavailable = False
    if supabase_admin:
        try:
            query = supabase_admin.table("cats").select("*")
            if query_text:
                query = query.ilike("name", "%" + escape_like(query_text) + "%")
            if sort == "top":
                query = query.order("likes_count", desc=True)
            cats = query.order("created_at", desc=True).order("id").range((page - 1) * page_size, page * page_size).execute().data or []
            top_rows = supabase_admin.table("cats").select("*").order("likes_count", desc=True).order("created_at", desc=True).limit(1).execute().data or []
            top_cat = top_rows[0] if top_rows else None
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
        try:
            raw_res: Any = getattr(supabase_admin.table("cats").select("*").order("likes_count", desc=True).order("created_at", desc=True).limit(50).execute(), "data", [])
            leaderboard = cast(List[Dict[str, Any]], raw_res) if isinstance(raw_res, list) else []
        except Exception:
            app.logger.exception("Could not load leaderboard")
            return render_template("error.html", status=503, message="The rankings are temporarily unavailable. Please try again."), 503
    elif not ENABLE_DEMO_DATA:
        return render_template("error.html", status=503, message="The rankings are temporarily unavailable. Please try again."), 503

    if not leaderboard and ENABLE_DEMO_DATA:
        leaderboard = sorted(list(MOCK_CATS), key=lambda c: int(c.get("likes_count", 0) or 0), reverse=True)

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
@limiter.limit("10 per hour")
@require_auth
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

        return jsonify({
            "message": "Cat uploaded successfully!",
            "cat": cat_record
        }), 201

    except Exception:
        app.logger.exception("Cat upload failed")
        return jsonify({"error": "Upload failed unexpectedly. Please try again."}), 500

@app.route("/api/cats/<cat_id>", methods=["GET"])
def get_cat_details(cat_id: str) -> Any:
    cat_record = None

    if supabase_admin:
        try:
            raw_data = get_db_row(supabase_admin.table("cats").select("*").eq("id", cat_id))
            if raw_data:
                cat_record = raw_data
        except Exception:
            app.logger.exception("Could not load cat %s", cat_id)
            return jsonify({"error": "Cat service is unavailable."}), 503
    elif not ENABLE_DEMO_DATA:
        return jsonify({"error": "Cat service is unavailable."}), 503

    if not cat_record and ENABLE_DEMO_DATA:
        cat_record = next((c for c in MOCK_CATS if str(c.get("id")) == str(cat_id)), None)

    if not cat_record:
        return jsonify({"error": "Cat not found."}), 404

    cat_record["user_avatar"] = resolve_user_avatar(cat_record.get("user_id"), cat_record.get("user_name"), cat_record.get("user_avatar"))
    return jsonify({"cat": cat_record}), 200

@app.route("/api/cats/<cat_id>", methods=["PUT"])
@limiter.limit("30 per hour")
@require_auth
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

        if supabase_admin:
            try:
                cat_row = get_db_row(supabase_admin.table("cats").select("id,user_id").eq("id", cat_id))
            except Exception:
                cat_row = None
            if not cat_row:
                return jsonify({"error": "Cat not found."}), 404
            if str(cat_row.get("user_id")) != user_id and not is_admin:
                return jsonify({"error": "Permission denied. You can only edit your own cats."}), 403
            if safe_db_update("cats", updates, "id", cat_id) is None:
                return jsonify({"error": "Database update failed."}), 503
        elif ENABLE_DEMO_DATA:
            match = next((c for c in MOCK_CATS if str(c.get("id")) == str(cat_id)), None)
            if not match:
                return jsonify({"error": "Cat not found."}), 404
            if str(match.get("user_id")) != user_id and not is_admin:
                return jsonify({"error": "Permission denied. You can only edit your own cats."}), 403
            match.update(updates)
        else:
            return jsonify({"error": "Database service is not configured."}), 503

        return jsonify({"message": "Cat updated successfully."}), 200
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid update values."}), 400
    except Exception:
        app.logger.exception("Failed to edit cat %s", cat_id)
        return jsonify({"error": "Unable to update cat right now."}), 500

@app.route("/api/cats/<cat_id>", methods=["DELETE"])
@limiter.limit("20 per hour")
@require_auth
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
            MOCK_CATS[:] = [c for c in MOCK_CATS if str(c.get("id")) != str(cat_id)]
            MOCK_LIKES[:] = [l for l in MOCK_LIKES if str(l.get("cat_id")) != str(cat_id)]
            MOCK_COMMENTS[:] = [cm for cm in MOCK_COMMENTS if str(cm.get("cat_id")) != str(cat_id)]
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

        return jsonify({"message": "Cat deleted successfully."}), 200
    except Exception:
        app.logger.exception("Failed to delete cat %s", cat_id)
        return jsonify({"error": "Unable to delete cat right now."}), 503

@app.route("/api/admin/cats/<cat_id>/force-delete", methods=["DELETE", "POST"])
@limiter.limit("30 per minute")
@require_auth
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
        return jsonify({"message": "Cat force deleted by admin successfully."}), 200
    except Exception:
        app.logger.exception("Admin force-delete failed for cat %s", cat_id)
        return jsonify({"error": "Unable to delete cat right now."}), 503

@app.route("/api/cats/<cat_id>/like", methods=["POST"])
@limiter.limit("120 per minute")
@require_auth
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
        rpc_rows = getattr(rpc_result, "data", []) or []
        if not isinstance(rpc_rows, list) or not rpc_rows:
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

        return jsonify({"status": status, "likes_count": new_count}), 200
    except Exception:
        app.logger.exception("Failed to toggle like for cat %s", cat_id)
        return jsonify({"error": "Unable to update vote right now."}), 503

@app.route("/api/cats/<cat_id>/comments", methods=["GET"])
def get_comments(cat_id: str) -> Any:
    comments_list: List[Dict[str, Any]] = []

    if supabase_admin:
        try:
            raw_res = getattr(
                supabase_admin.table("comments").select("*").eq("cat_id", cat_id).order("created_at", desc=False).limit(200).execute(),
                "data",
                [],
            )
            comments_list = cast(List[Dict[str, Any]], raw_res) if isinstance(raw_res, list) else []
        except Exception:
            app.logger.exception("Could not load comments for cat %s", cat_id)
            return jsonify({"error": "Comments service is unavailable."}), 503
    elif not ENABLE_DEMO_DATA:
        return jsonify({"error": "Comments service is unavailable."}), 503

    if not comments_list and ENABLE_DEMO_DATA:
        comments_list = [c for c in MOCK_COMMENTS if str(c.get("cat_id")) == str(cat_id)]

    for c in comments_list:
        c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))
        c.pop("user_email", None)

    return jsonify({"comments": comments_list}), 200

@app.route("/api/cats/<cat_id>/comments", methods=["POST"])
@limiter.limit("20 per minute")
@require_auth
def add_comment(cat_id: str) -> Any:
    try:
        user = getattr(g, "user", None)
        user_id, user_name, avatar_url = get_canonical_user_identity(user)
        user_email = clean_text(getattr(user, "email", ""), max_length=254)

        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}
        comment_text = clean_text(data.get("comment"), max_length=300)
        parent_id = sanitize_nullable_str(data.get("parent_id"))
        reply_to_name = sanitize_nullable_str(data.get("reply_to_name"))

        if not comment_text:
            return jsonify({"error": "Comment text cannot be empty."}), 400
        if not supabase_admin and not ENABLE_DEMO_DATA:
            return jsonify({"error": "Comments service is unavailable."}), 503

        if supabase_admin:
            try:
                cat_exists = get_db_row(supabase_admin.table("cats").select("id").eq("id", cat_id))
            except Exception:
                cat_exists = None
            if not cat_exists:
                return jsonify({"error": "Cat not found."}), 404
            if parent_id:
                try:
                    parent_row = get_db_row(supabase_admin.table("comments").select("id,cat_id,user_name").eq("id", parent_id))
                except Exception:
                    parent_row = None
                if not parent_row or str(parent_row.get("cat_id")) != str(cat_id):
                    return jsonify({"error": "Invalid reply target."}), 400
                reply_to_name = clean_text(parent_row.get("user_name"), max_length=40, fallback="Cat Lover")

        comment_id = str(uuid.uuid4())
        comment_payload: Dict[str, Any] = {
            "id": comment_id,
            "cat_id": cat_id,
            "user_id": user_id,
            "user_name": user_name,
            "user_avatar": avatar_url,
            "user_email": user_email,
            "parent_id": parent_id,
            "reply_to_name": reply_to_name,
            "comment": comment_text,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        if supabase_admin:
            if safe_db_insert("comments", comment_payload) is None:
                return jsonify({"error": "Could not save comment."}), 503

            try:
                cat_row = get_db_row(supabase_admin.table("cats").select("*").eq("id", cat_id))
                if cat_row:
                    cat_owner_id = str(cat_row.get("user_id", ""))
                    cat_name = str(cat_row.get("name", "Cat"))
                    cat_image = str(cat_row.get("image_url", ""))

                    if parent_id:
                        parent_row = get_db_row(supabase_admin.table("comments").select("*").eq("id", parent_id))
                        if parent_row:
                            parent_user_id = str(parent_row.get("user_id", ""))
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
                    else:
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

        return jsonify({
            "message": "Comment posted successfully!",
            "comment": {k: v for k, v in comment_payload.items() if k != "user_email"}
        }), 201

    except Exception:
        app.logger.exception("Could not add comment to cat %s", cat_id)
        return jsonify({"error": "Could not post comment right now."}), 500

@app.route("/api/comments/<comment_id>", methods=["DELETE"])
@limiter.limit("30 per minute")
@require_auth
def delete_comment(comment_id: str) -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    is_admin = is_admin_user(getattr(g, "user", None))

    if not supabase_admin:
        return jsonify({"error": "Comments service is unavailable."}), 503

    try:
        comm = get_db_row(supabase_admin.table("comments").select("id,user_id").eq("id", comment_id))
        if not comm:
            return jsonify({"error": "Comment not found."}), 404
        if str(comm.get("user_id")) != user_id and not is_admin:
            return jsonify({"error": "Permission denied. You can only delete your own comments."}), 403

        supabase_admin.table("comments").delete().eq("id", comment_id).execute()
        supabase_admin.table("notifications").delete().eq("comment_id", comment_id).execute()
        return jsonify({"message": "Comment deleted successfully."}), 200
    except Exception:
        app.logger.exception("Failed to delete comment %s", comment_id)
        return jsonify({"error": "Unable to delete comment right now."}), 503

@app.route("/api/admin/comments/<comment_id>", methods=["PUT"])
@limiter.limit("60 per minute")
@require_auth
def admin_edit_comment(comment_id: str) -> Any:
    try:
        if not is_admin_user(getattr(g, "user", None)):
            return jsonify({"error": "Admin access required."}), 403

        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}
        new_text = clean_text(data.get("comment"), max_length=300)

        if not new_text:
            return jsonify({"error": "Comment text cannot be empty."}), 400
        if not supabase_admin:
            return jsonify({"error": "Comments service is unavailable."}), 503
        if safe_db_update("comments", {"comment": new_text}, "id", comment_id) is None:
            return jsonify({"error": "Could not update comment."}), 503

        return jsonify({"message": "Comment updated successfully.", "comment_id": comment_id, "comment": new_text}), 200
    except Exception:
        app.logger.exception("Admin comment update failed for %s", comment_id)
        return jsonify({"error": "Could not update comment right now."}), 500

@app.route("/api/admin/comments/<comment_id>", methods=["DELETE", "POST"])
@limiter.limit("60 per minute")
@require_auth
def admin_delete_comment(comment_id: str) -> Any:
    try:
        if not is_admin_user(getattr(g, "user", None)):
            return jsonify({"error": "Admin access required."}), 403

        if not supabase_admin:
            return jsonify({"error": "Comments service is unavailable."}), 503
        try:
            supabase_admin.table("comments").delete().eq("id", comment_id).execute()
        except Exception:
            app.logger.exception("Admin failed to delete comment %s", comment_id)
            return jsonify({"error": "Could not delete comment."}), 503

        return jsonify({"message": "Comment deleted successfully by admin.", "comment_id": comment_id}), 200
    except Exception:
        app.logger.exception("Admin comment deletion failed for %s", comment_id)
        return jsonify({"error": "Could not delete comment right now."}), 500

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
@limiter.limit("120 per minute")
@require_auth
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
@limiter.limit("60 per minute")
@require_auth
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
@limiter.limit("30 per minute")
@require_auth
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
@limiter.limit("10 per hour")
@require_auth
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

@app.route("/api/auth/register", methods=["POST"])
@limiter.limit("5 per hour")
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
        result: Any = signup_client.auth.sign_up({
            "email": email,
            "password": password,
            "options": options,
        })
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
@limiter.limit("30 per hour")
@require_auth
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
@limiter.limit("30 per minute")
@require_auth
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
                supabase_admin.auth.admin.update_user_by_id(user_id, auth_update)
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
@limiter.limit("10 per hour")
@require_auth
def admin_force_delete_user(user_id: str) -> Any:
    try:
        if not is_admin_user(getattr(g, "user", None)):
            return jsonify({"error": "Admin access required."}), 403
        if not supabase_admin and not ENABLE_DEMO_DATA:
            return jsonify({"error": "Database service is unavailable."}), 503

        if str(getattr(g.user, "id", "")) == user_id:
            return jsonify({"error": "You cannot delete your own administrator account."}), 409
        if supabase_admin:
            try:
                user_cats = fetch_all_rows(lambda: supabase_admin.table("cats").select("image_url").eq("user_id", user_id).order("id"))
                profile_rows = supabase_admin.table("profiles").select("avatar_url").eq("id", user_id).limit(1).execute().data or []
                supabase_admin.auth.admin.delete_user(user_id)
                for cat in user_cats:
                    delete_file_from_storage(str(cat.get("image_url", "")), STORAGE_BUCKET, allowed_prefix=f"{user_id}/")
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

        return jsonify({"message": "User and all associated data deleted successfully.", "user_id": user_id}), 200
    except Exception:
        app.logger.exception("Unexpected force-delete failure for user %s", user_id)
        return jsonify({"error": "Could not delete this account right now."}), 500

@app.route("/api/user/<user_id>/profile", methods=["GET"])
def get_public_profile(user_id: str) -> Any:
    cats: List[Dict[str, Any]] = []
    user_name = ""
    user_avatar = ""
    user_bio = ""
    user_found = False

    if supabase_admin:
        try:

            p_res = supabase_admin.table("profiles").select("id,display_name,bio,avatar_url").eq("id", user_id).limit(1).execute()
            p_data = getattr(p_res, "data", []) or []
            if p_data:
                profile = p_data[0]
                user_found = True
                user_name = clean_text(profile.get("display_name"), max_length=40, fallback="Cat Lover")
                user_avatar = sanitize_image_url(profile.get("avatar_url"), fallback_name=user_name)
                user_bio = clean_text(profile.get("bio"), max_length=150)

            raw_data = fetch_all_rows(lambda: supabase_admin.table("cats").select("*").eq("user_id", user_id).order("created_at", desc=True).order("id"))
            cats = cast(List[Dict[str, Any]], raw_data) if isinstance(raw_data, list) else []
            if cats:
                user_found = True

            if not user_found:
                try:
                    u_obj: Any = supabase_admin.auth.admin.get_user_by_id(user_id)
                    u_data: Any = getattr(u_obj, "user", None) or getattr(u_obj, "data", None)
                    if u_data:
                        user_found = True
                        auth_email = str(getattr(u_data, "email", "") or "")
                        if isinstance(u_data, dict):
                            auth_email = str(u_data.get("email") or auth_email)
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
            cats = mock_cats
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

    return jsonify({
        "user_id": user_id,
        "cats_count": len(cats),
        "user_name": user_name,
        "user_avatar": user_avatar,
        "bio": user_bio,
        "total_likes": sum(int(c.get("likes_count", 0) or 0) for c in cats),
        "cats": cats,
    }), 200

@app.route("/api/user/my-cats", methods=["GET"])
@require_auth
def get_my_cats() -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    if not supabase_admin:
        if ENABLE_DEMO_DATA:
            return jsonify({"cats": [c for c in MOCK_CATS if str(c.get("user_id")) == user_id]}), 200
        return jsonify({"error": "Database service is unavailable."}), 503

    try:
        raw_data = fetch_all_rows(lambda: supabase_admin.table("cats").select("*").eq("user_id", user_id).order("created_at", desc=True).order("id"))
        cats = cast(List[Dict[str, Any]], raw_data) if isinstance(raw_data, list) else []
        return jsonify({"cats": cats}), 200
    except Exception:
        app.logger.exception("Could not load cats for user %s", user_id)
        return jsonify({"error": "Could not load your cats right now."}), 503

@app.route("/api/user/liked-cats", methods=["GET"])
@require_auth
def get_user_liked_cats() -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    if not supabase_admin:
        if ENABLE_DEMO_DATA:
            liked = [str(l.get("cat_id")) for l in MOCK_LIKES if str(l.get("user_id")) == user_id]
            return jsonify({"liked_cat_ids": liked}), 200
        return jsonify({"error": "Database service is unavailable."}), 503

    try:
        raw_data = fetch_all_rows(lambda: supabase_admin.table("likes").select("cat_id").eq("user_id", user_id).order("id"))
        liked_cat_ids = [str(item.get("cat_id")) for item in raw_data if item.get("cat_id")] if isinstance(raw_data, list) else []
        return jsonify({"liked_cat_ids": liked_cat_ids}), 200
    except Exception:
        app.logger.exception("Could not load liked cats for user %s", user_id)
        return jsonify({"error": "Could not load your liked cats right now."}), 503

@app.route("/api/admin/overview", methods=["GET"])
@require_auth
def admin_overview() -> Any:
    try:
        is_admin = is_admin_user(getattr(g, "user", None))
        if not is_admin:
            user_email = str(getattr(getattr(g, "user", None), "email", "") or "").lower()
            return jsonify({"error": f"Admin access restricted. Your account '{user_email}' is not configured as admin."}), 403

        if not supabase_admin:
            return jsonify({"error": "Admin service is unavailable."}), 503
        cats: List[Dict[str, Any]] = []
        if supabase_admin:
            try:
                raw_data: Any = fetch_all_rows(lambda: supabase_admin.table("cats").select("*").order("created_at", desc=True).order("id"))
                cats = cast(List[Dict[str, Any]], raw_data) if isinstance(raw_data, list) else []
            except Exception as ce:
                app.logger.warning("Admin overview cats query failed: %s", ce)
                return jsonify({"error": "Could not load the admin dashboard."}), 503

        if not cats and ENABLE_DEMO_DATA:
            cats = list(MOCK_CATS)

        for c in cats:
            c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))

        users_dict: Dict[str, Dict[str, Any]] = {}

        if supabase_admin:
            try:
                raw_users_list: List[Any] = []
                auth_page = 1
                while True:
                    auth_users_res = supabase_admin.auth.admin.list_users(page=auth_page, per_page=1000)
                    batch = getattr(auth_users_res, "users", None) or getattr(auth_users_res, "data", None) or auth_users_res
                    if not isinstance(batch, list):
                        raise ValueError("Unexpected user response")
                    raw_users_list.extend(batch)
                    if len(batch) < 1000:
                        break
                    auth_page += 1
                if isinstance(raw_users_list, list):
                    for u in raw_users_list:
                        uid = str(getattr(u, "id", "") or "")
                        if uid:
                            u_email = str(getattr(u, "email", "") or "")
                            u_meta = getattr(u, "user_metadata", {}) or {}
                            if not isinstance(u_meta, dict):
                                u_meta = {}
                            u_app_meta = getattr(u, "app_metadata", {}) or {}
                            if not isinstance(u_app_meta, dict):
                                u_app_meta = {}
                            disp_name = str(u_meta.get("display_name", "")).strip() or u_email.split("@")[0] or "Cat Lover"
                            avatar_url = str(u_meta.get("avatar_url", "")).strip() or resolve_user_avatar(uid, disp_name, None)
                            phone_val = str(u_meta.get("phone_number", "") or getattr(u, "phone", "") or "").strip()
                            role_val = "admin" if (u_email.lower() in [e.strip().lower() for e in ADMIN_EMAIL_CONFIG.split(",") if e.strip()] or str(u_app_meta.get("role", "")).lower() == "admin") else "user"

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

        for profile in fetch_all_rows(lambda: supabase_admin.table("profiles").select("id,display_name,avatar_url,phone").order("id")):
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
        if supabase_admin:
            try:
                c_res: Any = getattr(supabase_admin.table("comments").select("*").order("created_at", desc=True).limit(200).execute(), "data", [])
                all_comments = cast(List[Dict[str, Any]], c_res) if isinstance(c_res, list) else []
            except Exception as ce:
                app.logger.warning("Admin overview comments query failed: %s", ce)

        if not all_comments and ENABLE_DEMO_DATA:
            all_comments = list(MOCK_COMMENTS)

        comments_count = supabase_admin.table("comments").select("id", count="exact", head=True).execute().count or 0
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=env_flag("FLASK_DEBUG", False))
