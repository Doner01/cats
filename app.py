import os
import re
import uuid
import time
from threading import Lock
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, g, Response
from supabase import create_client, Client

BASE_DIR: Path = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

app: Flask = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
    static_url_path="/static"
)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "my-flask-secret-key-0101")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = int(os.getenv("STATIC_CACHE_SECONDS", str(7 * 24 * 60 * 60)))

DEFAULT_SUPABASE_URL = ""
DEFAULT_SUPABASE_ANON_KEY = ""
DEFAULT_SUPABASE_SERVICE_KEY = ""
DEFAULT_ADMIN_EMAIL = ""

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip() or DEFAULT_SUPABASE_URL
SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "").strip() or DEFAULT_SUPABASE_ANON_KEY
SUPABASE_SERVICE_KEY: str = (os.getenv("SUPABASE_SERVICE_KEY", "").strip() or os.getenv("SUPABASE_KEY", "").strip() or DEFAULT_SUPABASE_SERVICE_KEY)
ADMIN_EMAIL_CONFIG: str = os.getenv("ADMIN_EMAILS", os.getenv("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)).strip().lower()

# Initialize Supabase clients safely
supabase_admin: Optional[Client] = None
supabase_auth: Optional[Client] = None

try:
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
except Exception as init_err:
    print(f"Warning: Failed to init supabase_admin: {init_err}")

try:
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        supabase_auth = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
except Exception as init_err:
    print(f"Warning: Failed to init supabase_auth: {init_err}")


# Cloudflare R2 Object Storage Configuration (S3-Compatible)
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
        print("Cloudflare R2 Storage client initialized successfully!")
    except Exception as r2_err:
        print(f"Warning: Failed to init Cloudflare R2 client: {r2_err}")

if not r2_client:
    print("Warning: Cloudflare R2 is not configured. Media uploads will be unavailable.")

STORAGE_BUCKET: str = "cat-images"

# Small in-process cache for public, read-heavy pages. This avoids repeated
# Supabase round trips while keeping content fresh after mutations.
PUBLIC_CACHE_TTL_SECONDS = max(2.0, float(os.getenv("PUBLIC_CACHE_TTL_SECONDS", "8")))
_public_cache_lock = Lock()
_public_cache: Dict[str, Tuple[float, Any]] = {}

def _cache_get(key: str) -> Any:
    now = time.monotonic()
    with _public_cache_lock:
        item = _public_cache.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at <= now:
            _public_cache.pop(key, None)
            return None
        return value

def _cache_set(key: str, value: Any, ttl: Optional[float] = None) -> None:
    with _public_cache_lock:
        _public_cache[key] = (time.monotonic() + (ttl if ttl is not None else PUBLIC_CACHE_TTL_SECONDS), value)

def invalidate_public_cache() -> None:
    with _public_cache_lock:
        for key in ("index", "leaderboard"):
            _public_cache.pop(key, None)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "jfif", "gif"}
MAX_FILE_SIZE: int = 5 * 1024 * 1024  # 5 MB

# In-memory mock store for offline and test resilience
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
user_avatar_cache: Dict[str, str] = {}


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

    # Check binary magic numbers
    is_jpeg = file_bytes[:3] == b"\xff\xd8\xff"
    is_png = file_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    is_webp = file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP"
    is_gif = file_bytes[:6] in (b"GIF87a", b"GIF89a")

    if not (is_jpeg or is_png or is_webp or is_gif):
        return False, "Uploaded file content is not a valid image format."

    return True, ""



def upload_file_to_storage(file_bytes: bytes, unique_path: str, content_type: str, bucket_name: str = STORAGE_BUCKET) -> str:
    """Upload an object to Cloudflare R2 and return its public URL.

    R2 is the single source of truth for uploaded media. Supabase Storage is
    intentionally not used as a fallback so media cannot silently end up in
    two different storage systems.
    """
    if not r2_client:
        raise RuntimeError("Cloudflare R2 is not configured.")

    if not R2_BUCKET_NAME or not R2_PUBLIC_DOMAIN:
        raise RuntimeError("R2_BUCKET_NAME and R2_PUBLIC_DOMAIN must be configured.")

    try:
        r2_client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=unique_path,
            Body=file_bytes,
            ContentType=content_type,
        )
    except Exception as r2_err:
        raise RuntimeError(f"Cloudflare R2 upload failed: {r2_err}") from r2_err

    return f"{R2_PUBLIC_DOMAIN}/{unique_path}"

def delete_r2_prefix(prefix: str) -> None:
    """Delete all R2 objects under a prefix. Best-effort cleanup."""
    if not r2_client or not R2_BUCKET_NAME:
        return

    continuation_token = None
    try:
        while True:
            kwargs: Dict[str, Any] = {
                "Bucket": R2_BUCKET_NAME,
                "Prefix": prefix,
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            response = r2_client.list_objects_v2(**kwargs)
            objects = response.get("Contents", []) or []
            if objects:
                r2_client.delete_objects(
                    Bucket=R2_BUCKET_NAME,
                    Delete={"Objects": [{"Key": obj["Key"]} for obj in objects if obj.get("Key")]},
                )

            if not response.get("IsTruncated"):
                break

            continuation_token = response.get("NextContinuationToken")
            if not continuation_token:
                break
    except Exception as r2e:
        print(f"Notice: R2 prefix cleanup failed for '{prefix}': {r2e}")


def generate_default_avatar(name: str) -> str:
    safe_name = name.strip() or "Cat"
    return f"https://api.dicebear.com/7.x/bottts/svg?seed={safe_name}&backgroundColor=b6e3f4,c0aede,d1d4f9"


def resolve_user_avatar(user_id: Optional[str], user_name: Optional[str], existing_avatar: Optional[str] = None) -> str:
    """Resolve an avatar without an Auth API call per row.

    Feed/leaderboard pages can contain dozens of cats, so calling Supabase Auth
    once per card creates a classic N+1 latency problem. Persisted avatars are
    already present on cat/comment/profile rows; when missing, use the deterministic
    local fallback instead of doing another network request.
    """
    avatar = str(existing_avatar or "").strip()
    if avatar and not avatar.startswith("https://api.dicebear.com/"):
        if user_id:
            user_avatar_cache[str(user_id)] = avatar
        return avatar

    if user_id and str(user_id) in user_avatar_cache:
        return user_avatar_cache[str(user_id)]

    fallback = generate_default_avatar(str(user_name or "Cat"))
    if user_id:
        user_avatar_cache[str(user_id)] = fallback
    return fallback


def is_admin_user(user: Any) -> bool:
    """Check admin status from a server-controlled allowlist/database role.

    Client-controlled auth.user_metadata.role is never trusted for authorization.
    """
    if not user:
        return False

    user_email = str(getattr(user, "email", "") or "").strip().lower()

    if user_email and ADMIN_EMAIL_CONFIG:
        admin_emails = [e.strip().lower() for e in ADMIN_EMAIL_CONFIG.split(",") if e.strip()]
        if user_email in admin_emails:
            return True

    user_id = str(getattr(user, "id", "") or "")
    if user_id and supabase_admin:
        try:
            row = getattr(
                supabase_admin.table("profiles").select("role").eq("id", user_id).single().execute(),
                "data",
                None,
            )
            return bool(row and str(row.get("role", "")).strip().lower() == "admin")
        except Exception:
            pass

    return False

def sanitize_nullable_str(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in ("none", "null", "undefined", ""):
        return None
    return s


def safe_db_insert(table_name: str, payload: Dict[str, Any]) -> Any:
    if not supabase_admin:
        return None
    try:
        return supabase_admin.table(table_name).insert(payload).execute()
    except Exception as e:
        print(f"Notice: safe_db_insert on '{table_name}' failed: {e}")
        return None


def safe_db_update(table_name: str, payload: Dict[str, Any], id_column: str, id_value: Any) -> Any:
    if not supabase_admin:
        return None
    try:
        return supabase_admin.table(table_name).update(payload).eq(id_column, id_value).execute()
    except Exception as e:
        print(f"Notice: safe_db_update on '{table_name}' failed: {e}")
        return None


def push_notification(user_id: str, actor_id: str, actor_name: str, actor_avatar: str, notif_type: str, cat_id: str, message: str, cat_name: Optional[str] = None, cat_image: Optional[str] = None, comment_id: Optional[str] = None) -> None:
    if not user_id or str(user_id) == str(actor_id):
        return

    clean_actor_avatar = resolve_user_avatar(actor_id, actor_name, actor_avatar)
    notif_data: Dict[str, Any] = {
        "id": f"notif-{uuid.uuid4()}",
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

    MOCK_NOTIFICATIONS.insert(0, notif_data)


def require_auth(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not str(auth_header).startswith("Bearer "):
            return jsonify({"error": "Unauthorized. Please sign in."}), 401

        parts = str(auth_header).split(" ")
        if len(parts) != 2:
            return jsonify({"error": "Malformed authorization token."}), 401

        token = str(parts[1]).strip()
        auth_user = None

        if supabase_auth:
            try:
                user_res: Any = supabase_auth.auth.get_user(token)
                auth_user = getattr(user_res, "user", None) or getattr(user_res, "data", None)
            except Exception:
                pass

        if not auth_user and supabase_admin:
            try:
                user_res2: Any = supabase_admin.auth.get_user(token)
                auth_user = getattr(user_res2, "user", None) or getattr(user_res2, "data", None)
            except Exception:
                pass

        # Invalid/expired tokens must never become an authenticated mock user.
        if not auth_user:
            return jsonify({"error": "Unauthorized. Invalid or expired session."}), 401

        g.user = auth_user
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# PAGE ROUTES
# ==========================================

@app.route("/favicon.ico")
def favicon() -> Response:
    return Response(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">🐱</text></svg>',
        mimetype="image/svg+xml"
    )


@app.route("/")
def index() -> str:
    cached = _cache_get("index")
    if cached is not None:
        return render_template(
            "index.html",
            cats=cached["cats"],
            top_cat=cached["top_cat"],
            supabase_url=SUPABASE_URL,
            supabase_anon_key=SUPABASE_ANON_KEY
        )

    cats: List[Dict[str, Any]] = []
    top_cat: Optional[Dict[str, Any]] = None

    feed_fields = "id,user_id,user_name,user_avatar,name,bio,description,image_url,likes_count,created_at"
    if supabase_admin:
        try:
            raw_res: Any = getattr(
                supabase_admin.table("cats").select(feed_fields).order("created_at", desc=True).limit(60).execute(),
                "data", []
            )
            cats = cast(List[Dict[str, Any]], raw_res) if isinstance(raw_res, list) else []

            top_raw: Any = getattr(
                supabase_admin.table("cats").select(feed_fields).order("likes_count", desc=True).order("created_at", desc=True).limit(1).execute(),
                "data", []
            )
            if isinstance(top_raw, list) and top_raw:
                top_cat = dict(top_raw[0])
        except Exception as e:
            print(f"Notice: Supabase index fetch error: {e}")

    if not cats:
        cats = list(MOCK_CATS)
        if cats:
            top_cat = max(cats, key=lambda c: int(c.get("likes_count", 0) or 0))

    for c in cats:
        c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))
    if top_cat:
        top_cat["user_avatar"] = resolve_user_avatar(top_cat.get("user_id"), top_cat.get("user_name"), top_cat.get("user_avatar"))

    _cache_set("index", {"cats": cats, "top_cat": top_cat})
    return render_template(
        "index.html",
        cats=cats,
        top_cat=top_cat,
        supabase_url=SUPABASE_URL,
        supabase_anon_key=SUPABASE_ANON_KEY
    )


@app.route("/leaderboard")
def leaderboard_page() -> str:
    cached = _cache_get("leaderboard")
    if cached is not None:
        return render_template(
            "leaderboard.html",
            leaderboard=cached,
            supabase_url=SUPABASE_URL,
            supabase_anon_key=SUPABASE_ANON_KEY
        )

    leaderboard: List[Dict[str, Any]] = []
    fields = "id,user_id,user_name,user_avatar,name,bio,description,image_url,likes_count,created_at"
    if supabase_admin:
        try:
            raw_res: Any = getattr(
                supabase_admin.table("cats").select(fields).order("likes_count", desc=True).order("created_at", desc=True).limit(50).execute(),
                "data", []
            )
            leaderboard = cast(List[Dict[str, Any]], raw_res) if isinstance(raw_res, list) else []
        except Exception as e:
            print(f"Notice: Supabase leaderboard fetch error: {e}")

    if not leaderboard:
        leaderboard = sorted(
            MOCK_CATS,
            key=lambda c: (int(c.get("likes_count", 0) or 0), str(c.get("created_at", ""))),
            reverse=True
        )[:50]

    for c in leaderboard:
        c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))

    _cache_set("leaderboard", leaderboard)
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


# ==========================================
# CAT CRUD API ENDPOINTS
# ==========================================

@app.route("/api/cats/upload", methods=["POST"])
@require_auth
def upload_cat() -> Any:
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        user_email = str(getattr(getattr(g, "user", None), "email", "Anonymous"))
        raw_meta = getattr(getattr(g, "user", None), "user_metadata", {})
        user_meta: Dict[str, Any] = cast(Dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else {}
        user_name = str(user_meta.get("display_name", "")).strip() or user_email.split("@")[0]
        avatar_url = str(user_meta.get("avatar_url", "")).strip() or generate_default_avatar(user_name)

        file = request.files.get("file")
        if not file or not getattr(file, "filename", None):
            return jsonify({"error": "No image file provided."}), 400

        cat_name = str(request.form.get("name") or "Whiskers").strip() or "Whiskers"
        cat_bio = str(request.form.get("bio") or request.form.get("description") or "").strip()
        filename_str: str = str(getattr(file, "filename", "") or "")

        file_bytes: bytes = file.read()
        is_valid_img, img_err = validate_image_file(file_bytes, filename_str)
        if not is_valid_img:
            return jsonify({"error": img_err}), 400

        clean_ext: str = str(filename_str.rsplit(".", 1)[-1]).lower() if "." in filename_str else "jpg"
        unique_path = f"{user_id}/{uuid.uuid4()}.{clean_ext}"
        public_url = ""

        content_type = getattr(file, "content_type", "") or f"image/{clean_ext}"
        try:
            public_url = upload_file_to_storage(file_bytes, unique_path, content_type, STORAGE_BUCKET)
        except Exception as storage_err:
            return jsonify({"error": str(storage_err)}), 503

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
            safe_db_insert("cats", cat_record)

        MOCK_CATS.insert(0, cat_record)

        invalidate_public_cache()
        return jsonify({
            "message": "Cat uploaded successfully!",
            "cat": cat_record
        }), 201

    except Exception as e:
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500


@app.route("/api/cats/<cat_id>", methods=["GET"])
def get_cat_details(cat_id: str) -> Any:
    cat_record = None

    if supabase_admin:
        try:
            raw_data = getattr(supabase_admin.table("cats").select("id,user_id,user_name,user_avatar,name,bio,description,image_url,likes_count,created_at").eq("id", cat_id).single().execute(), "data", None)
            if raw_data:
                cat_record = raw_data
        except Exception:
            pass

    if not cat_record:
        for c in MOCK_CATS:
            if str(c.get("id")) == str(cat_id):
                cat_record = c
                break

    if not cat_record:
        return jsonify({"error": "Cat not found."}), 404

    cat_record["user_avatar"] = resolve_user_avatar(cat_record.get("user_id"), cat_record.get("user_name"), cat_record.get("user_avatar"))

    return jsonify({"cat": cat_record}), 200


@app.route("/api/cats/<cat_id>", methods=["PUT"])
@require_auth
def edit_cat(cat_id: str) -> Any:
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        is_admin = is_admin_user(getattr(g, "user", None))

        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}
        new_name = str(data.get("name", "")).strip()
        new_bio = str(data.get("bio") or data.get("description") or "").strip()

        updates: Dict[str, Any] = {}
        if new_name:
            updates["name"] = new_name
        if "bio" in data or "description" in data:
            updates["bio"] = new_bio
            updates["description"] = new_bio
        if is_admin and "likes_count" in data:
            updates["likes_count"] = int(data.get("likes_count", 0))

        if not updates:
            return jsonify({"error": "No updates provided."}), 400

        if supabase_admin:
            safe_db_update("cats", updates, "id", cat_id)

        for c in MOCK_CATS:
            if str(c.get("id")) == str(cat_id):
                if new_name: c["name"] = new_name
                if "bio" in data or "description" in data:
                    c["bio"] = new_bio
                    c["description"] = new_bio
                if is_admin and "likes_count" in data:
                    c["likes_count"] = int(data.get("likes_count", 0))

        invalidate_public_cache()
        return jsonify({"message": "Cat updated successfully."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cats/<cat_id>", methods=["DELETE"])
@require_auth
def delete_cat(cat_id: str) -> Any:
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        is_admin = is_admin_user(getattr(g, "user", None))

        if supabase_admin:
            try:
                cat_row = getattr(supabase_admin.table("cats").select("id,user_id,user_name,user_avatar,name,bio,description,image_url,likes_count,created_at").eq("id", cat_id).single().execute(), "data", None)
                if cat_row:
                    if str(cat_row.get("user_id")) != user_id and not is_admin:
                        return jsonify({"error": "Permission denied. You can only delete your own cats."}), 403

                    supabase_admin.table("likes").delete().eq("cat_id", cat_id).execute()
                    supabase_admin.table("comments").delete().eq("cat_id", cat_id).execute()
                    supabase_admin.table("notifications").delete().eq("cat_id", cat_id).execute()

                    # Clean the corresponding R2 object
                    img_url = str(cat_row.get("image_url", ""))
                    if r2_client and R2_PUBLIC_DOMAIN and img_url.startswith(R2_PUBLIC_DOMAIN + "/"):
                        object_key = img_url[len(R2_PUBLIC_DOMAIN) + 1:].split("?")[0]
                        try:
                            r2_client.delete_object(Bucket=R2_BUCKET_NAME, Key=object_key)
                        except Exception as r2e:
                            print(f"Notice: R2 delete cat image: {r2e}")

                    supabase_admin.table("cats").delete().eq("id", cat_id).execute()
            except Exception as de:
                print(f"Notice: Supabase delete cat: {de}")

        MOCK_CATS[:] = [c for c in MOCK_CATS if str(c.get("id")) != str(cat_id)]
        MOCK_LIKES[:] = [l for l in MOCK_LIKES if str(l.get("cat_id")) != str(cat_id)]
        MOCK_COMMENTS[:] = [cm for cm in MOCK_COMMENTS if str(cm.get("cat_id")) != str(cat_id)]

        invalidate_public_cache()
        return jsonify({"message": "Cat deleted successfully."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/cats/<cat_id>/force-delete", methods=["DELETE", "POST"])
@require_auth
def admin_force_delete(cat_id: str) -> Any:
    try:
        if not is_admin_user(getattr(g, "user", None)):
            return jsonify({"error": "Admin access required."}), 403

        if supabase_admin:
            try:
                cat_row = getattr(supabase_admin.table("cats").select("id,user_id,user_name,user_avatar,name,bio,description,image_url,likes_count,created_at").eq("id", cat_id).single().execute(), "data", None)
                if cat_row:
                    img_url = str(cat_row.get("image_url", ""))
                    if r2_client and R2_PUBLIC_DOMAIN and img_url.startswith(R2_PUBLIC_DOMAIN + "/"):
                        object_key = img_url[len(R2_PUBLIC_DOMAIN) + 1:].split("?")[0]
                        try:
                            r2_client.delete_object(Bucket=R2_BUCKET_NAME, Key=object_key)
                        except Exception as r2e:
                            print(f"Notice: R2 delete cat image: {r2e}")

                supabase_admin.table("likes").delete().eq("cat_id", cat_id).execute()
                supabase_admin.table("comments").delete().eq("cat_id", cat_id).execute()
                supabase_admin.table("notifications").delete().eq("cat_id", cat_id).execute()
                supabase_admin.table("cats").delete().eq("id", cat_id).execute()
            except Exception as ce:
                print(f"Notice: Supabase admin force delete cat: {ce}")

        MOCK_CATS[:] = [c for c in MOCK_CATS if str(c.get("id")) != str(cat_id)]
        MOCK_LIKES[:] = [l for l in MOCK_LIKES if str(l.get("cat_id")) != str(cat_id)]
        MOCK_COMMENTS[:] = [cm for cm in MOCK_COMMENTS if str(cm.get("cat_id")) != str(cat_id)]

        return jsonify({"message": "Cat force deleted by admin successfully."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================
# LIKES & VOTING API
# ==========================================

@app.route("/api/cats/<cat_id>/like", methods=["POST"])
@require_auth
def toggle_like(cat_id: str) -> Any:
    try:
        user = getattr(g, "user", None)
        user_id = str(getattr(user, "id", ""))
        user_email = str(getattr(user, "email", "Anonymous"))
        raw_meta = getattr(user, "user_metadata", {})
        user_meta: Dict[str, Any] = cast(Dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else {}
        user_name = str(user_meta.get("display_name", "")).strip() or user_email.split("@")[0]
        actor_avatar = str(user_meta.get("avatar_url", "")).strip()

        if supabase_admin:
            # Fast path: one database round-trip for the like toggle, count update,
            # and the cat metadata needed for the notification.
            try:
                rpc_res: Any = supabase_admin.rpc(
                    "toggle_cat_like",
                    {"p_cat_id": cat_id, "p_user_id": user_id}
                ).execute()
                rpc_data: Any = getattr(rpc_res, "data", None)
                if isinstance(rpc_data, list) and rpc_data:
                    rpc_data = rpc_data[0]
                if isinstance(rpc_data, dict) and rpc_data.get("status") in {"liked", "unliked"}:
                    status = str(rpc_data.get("status"))
                    likes_count = int(rpc_data.get("likes_count", 0) or 0)
                    if status == "liked":
                        push_notification(
                            user_id=str(rpc_data.get("cat_owner_id", "")),
                            actor_id=user_id,
                            actor_name=user_name,
                            actor_avatar=actor_avatar,
                            notif_type="like",
                            cat_id=cat_id,
                            cat_name=str(rpc_data.get("cat_name", "Cat")),
                            cat_image=str(rpc_data.get("cat_image", "")),
                            message=f"{user_name} liked your cat {str(rpc_data.get('cat_name', 'Cat'))}!"
                        )
                    invalidate_public_cache()
                    return jsonify({"status": status, "likes_count": likes_count}), 200
            except Exception as rpc_err:
                print(f"Notice: fast like RPC unavailable, using fallback: {rpc_err}")

            # Compatibility fallback for deployments where the migration has not
            # yet created the RPC function.
            try:
                cat_row = getattr(
                    supabase_admin.table("cats")
                    .select("id,user_id,name,image_url,likes_count")
                    .eq("id", cat_id).single().execute(),
                    "data", None
                )
                if cat_row:
                    current_likes = int(cat_row.get("likes_count", 0) or 0)
                    existing_like = getattr(
                        supabase_admin.table("likes")
                        .select("id")
                        .eq("cat_id", cat_id).eq("user_id", user_id).limit(1).execute(),
                        "data", []
                    ) or []
                    if existing_like:
                        supabase_admin.table("likes").delete().eq("cat_id", cat_id).eq("user_id", user_id).execute()
                        new_count = max(0, current_likes - 1)
                        safe_db_update("cats", {"likes_count": new_count}, "id", cat_id)
                        invalidate_public_cache()
                        return jsonify({"status": "unliked", "likes_count": new_count}), 200

                    safe_db_insert("likes", {"cat_id": cat_id, "user_id": user_id})
                    new_count = current_likes + 1
                    safe_db_update("cats", {"likes_count": new_count}, "id", cat_id)
                    push_notification(
                        user_id=str(cat_row.get("user_id", "")),
                        actor_id=user_id,
                        actor_name=user_name,
                        actor_avatar=actor_avatar,
                        notif_type="like",
                        cat_id=cat_id,
                        cat_name=str(cat_row.get("name", "Cat")),
                        cat_image=str(cat_row.get("image_url", "")),
                        message=f"{user_name} liked your cat {str(cat_row.get('name', 'Cat'))}!"
                    )
                    invalidate_public_cache()
                    return jsonify({"status": "liked", "likes_count": new_count}), 200
            except Exception as le:
                print(f"Notice: Supabase toggle like fallback: {le}")

        # Offline/test fallback.
        for c in MOCK_CATS:
            if str(c.get("id")) == str(cat_id):
                c["likes_count"] = int(c.get("likes_count", 0) or 0) + 1
                invalidate_public_cache()
                return jsonify({"status": "liked", "likes_count": c["likes_count"]}), 200

        return jsonify({"error": "Cat not found."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================
# COMMENTS API (WITH THREADED REPLIES)
# ==========================================

@app.route("/api/cats/<cat_id>/comments", methods=["GET"])
def get_comments(cat_id: str) -> Any:
    comments_list: List[Dict[str, Any]] = []

    if supabase_admin:
        try:
            raw_res = getattr(supabase_admin.table("comments").select("id,cat_id,user_id,user_name,user_avatar,parent_id,reply_to_name,comment,created_at").eq("cat_id", cat_id).order("created_at", desc=False).limit(200).execute(), "data", [])
            comments_list = cast(List[Dict[str, Any]], raw_res) if isinstance(raw_res, list) else []
        except Exception as ce:
            print(f"Notice: Supabase get comments: {ce}")

    if not comments_list:
        comments_list = [c for c in MOCK_COMMENTS if str(c.get("cat_id")) == str(cat_id)]

    for c in comments_list:
        c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))

    return jsonify({"comments": comments_list}), 200


@app.route("/api/cats/<cat_id>/comments", methods=["POST"])
@require_auth
def add_comment(cat_id: str) -> Any:
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        user_email = str(getattr(getattr(g, "user", None), "email", "Anonymous"))
        raw_meta = getattr(getattr(g, "user", None), "user_metadata", {})
        user_meta: Dict[str, Any] = cast(Dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else {}
        user_name = str(user_meta.get("display_name", "")).strip() or user_email.split("@")[0]
        avatar_url = str(user_meta.get("avatar_url", "")).strip() or generate_default_avatar(user_name)

        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}
        comment_text = str(data.get("comment", "")).strip()
        parent_id = sanitize_nullable_str(data.get("parent_id"))
        reply_to_name = sanitize_nullable_str(data.get("reply_to_name"))

        if not comment_text:
            return jsonify({"error": "Comment text cannot be empty."}), 400

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
            safe_db_insert("comments", comment_payload)

            # Notifications
            try:
                cat_row = getattr(supabase_admin.table("cats").select("id,user_id,user_name,user_avatar,name,bio,description,image_url,likes_count,created_at").eq("id", cat_id).single().execute(), "data", None)
                if cat_row:
                    cat_owner_id = str(cat_row.get("user_id", ""))
                    cat_name = str(cat_row.get("name", "Cat"))
                    cat_image = str(cat_row.get("image_url", ""))

                    if parent_id:
                        parent_row = getattr(supabase_admin.table("comments").select("id,user_id").eq("id", parent_id).single().execute(), "data", None)
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
                print(f"Notice: Supabase comment notification: {ne}")

        if not supabase_admin:
            MOCK_COMMENTS.append(comment_payload)

        return jsonify({
            "message": "Comment posted successfully!",
            "comment": comment_payload
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/comments/<comment_id>", methods=["DELETE"])
@require_auth
def delete_comment(comment_id: str) -> Any:
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        is_admin = is_admin_user(getattr(g, "user", None))

        if supabase_admin:
            try:
                comm = getattr(supabase_admin.table("comments").select("id,user_id,cat_id").eq("id", comment_id).single().execute(), "data", None)
                if comm:
                    if str(comm.get("user_id")) != user_id and not is_admin:
                        return jsonify({"error": "Permission denied. You can only delete your own comments."}), 403

                    supabase_admin.table("comments").delete().eq("id", comment_id).execute()
                    supabase_admin.table("comments").delete().eq("parent_id", comment_id).execute()
                    supabase_admin.table("notifications").delete().eq("comment_id", comment_id).execute()
            except Exception as cde:
                print(f"Notice: Supabase delete comment: {cde}")

        MOCK_COMMENTS[:] = [c for c in MOCK_COMMENTS if str(c.get("id")) != str(comment_id) and str(c.get("parent_id")) != str(comment_id)]

        return jsonify({"message": "Comment deleted successfully."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/comments/<comment_id>", methods=["PUT"])
@require_auth
def admin_edit_comment(comment_id: str) -> Any:
    try:
        if not is_admin_user(getattr(g, "user", None)):
            return jsonify({"error": "Admin access required."}), 403

        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}
        new_text = str(data.get("comment", "")).strip()

        if not new_text:
            return jsonify({"error": "Comment text cannot be empty."}), 400

        if supabase_admin:
            safe_db_update("comments", {"comment": new_text}, "id", comment_id)

        for comm in MOCK_COMMENTS:
            if str(comm.get("id")) == str(comment_id):
                comm["comment"] = new_text

        return jsonify({"message": "Comment updated successfully.", "comment_id": comment_id, "comment": new_text}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/comments/<comment_id>", methods=["DELETE", "POST"])
@require_auth
def admin_delete_comment(comment_id: str) -> Any:
    try:
        if not is_admin_user(getattr(g, "user", None)):
            return jsonify({"error": "Admin access required."}), 403

        if supabase_admin:
            try:
                supabase_admin.table("comments").delete().eq("id", comment_id).execute()
            except Exception as ce:
                print(f"Notice: Supabase admin delete comment: {ce}")

        MOCK_COMMENTS[:] = [comm for comm in MOCK_COMMENTS if str(comm.get("id")) != str(comment_id)]

        return jsonify({"message": "Comment deleted successfully by admin.", "comment_id": comment_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================
# NOTIFICATIONS API
# ==========================================

@app.route("/api/notifications", methods=["GET"])
@require_auth
def get_notifications() -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    notifications: List[Dict[str, Any]] = []

    if supabase_admin:
        try:
            raw_res = getattr(supabase_admin.table("notifications").select("id,user_id,actor_id,actor_name,actor_avatar,type,cat_id,cat_name,cat_image,comment_id,message,is_read,created_at").eq("user_id", user_id).order("created_at", desc=True).limit(50).execute(), "data", [])
            notifications = cast(List[Dict[str, Any]], raw_res) if isinstance(raw_res, list) else []
        except Exception as ne:
            print(f"Notice: Supabase get notifications: {ne}")

    if not notifications:
        notifications = [n for n in MOCK_NOTIFICATIONS if str(n.get("user_id")) == str(user_id)]

    unread_count = sum(1 for n in notifications if not n.get("is_read", False))

    return jsonify({
        "notifications": notifications,
        "unread_count": unread_count
    }), 200


@app.route("/api/notifications/<notif_id>/read", methods=["POST"])
@require_auth
def mark_notification_read(notif_id: str) -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    if supabase_admin:
        safe_db_update("notifications", {"is_read": True}, "id", notif_id)

    for n in MOCK_NOTIFICATIONS:
        if str(n.get("id")) == str(notif_id) and str(n.get("user_id")) == user_id:
            n["is_read"] = True

    return jsonify({"message": "Marked as read."}), 200


@app.route("/api/notifications/read-all", methods=["POST"])
@require_auth
def mark_all_notifications_read() -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    if supabase_admin:
        safe_db_update("notifications", {"is_read": True}, "user_id", user_id)

    for n in MOCK_NOTIFICATIONS:
        if str(n.get("user_id")) == user_id:
            n["is_read"] = True

    return jsonify({"message": "All marked as read."}), 200


@app.route("/api/notifications/clear-all", methods=["DELETE", "POST"])
@require_auth
def clear_all_notifications() -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    if supabase_admin:
        try:
            supabase_admin.table("notifications").delete().eq("user_id", user_id).execute()
        except Exception:
            pass

    MOCK_NOTIFICATIONS[:] = [n for n in MOCK_NOTIFICATIONS if str(n.get("user_id")) != user_id]

    return jsonify({"message": "Notifications cleared."}), 200


# ==========================================
# USER PROFILE & AVATAR API
# ==========================================

@app.route("/api/user/avatar", methods=["POST"])
@require_auth
def upload_user_avatar() -> Any:
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        file = request.files.get("avatar") or request.files.get("file")
        if not file or not getattr(file, "filename", None):
            return jsonify({"error": "No avatar image provided."}), 400

        filename_str = str(getattr(file, "filename", "") or "")
        file_bytes: bytes = file.read()
        is_valid_img, img_err = validate_image_file(file_bytes, filename_str)
        if not is_valid_img:
            return jsonify({"error": img_err}), 400

        clean_ext = str(filename_str.rsplit(".", 1)[-1]).lower() if "." in filename_str else "jpg"
        avatar_path = f"avatars/{user_id}/{uuid.uuid4()}.{clean_ext}"
        public_url = ""

        content_type = getattr(file, "content_type", "") or f"image/{clean_ext}"
        public_url = upload_file_to_storage(file_bytes, avatar_path, content_type, "avatars")

        if not public_url:
            public_url = generate_default_avatar(user_id)

        user_avatar_cache[user_id] = public_url

        if supabase_admin:
            safe_db_update("cats", {"user_avatar": public_url}, "user_id", user_id)
            safe_db_update("comments", {"user_avatar": public_url}, "user_id", user_id)
            safe_db_update("profiles", {"avatar_url": public_url, "updated_at": datetime.now(timezone.utc).isoformat()}, "id", user_id)
            try:
                supabase_admin.auth.admin.update_user_by_id(user_id, {"user_metadata": {"avatar_url": public_url}})
            except Exception:
                pass

        return jsonify({"message": "Avatar uploaded successfully.", "avatar_url": public_url}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/user/profile/ensure", methods=["POST"])
@require_auth
def ensure_user_profile() -> Any:
    """Make sure every authenticated user has a profile row before editing account data."""
    try:
        user = getattr(g, "user", None)
        user_id = str(getattr(user, "id", "") or "").strip()
        if not user_id:
            return jsonify({"error": "Authenticated user ID is missing."}), 401

        if not supabase_admin:
            return jsonify({"message": "Profile is ready.", "profile_created": False}), 200

        existing = None
        try:
            existing_res = supabase_admin.table("profiles").select("id").eq("id", user_id).limit(1).execute()
            existing_rows = getattr(existing_res, "data", None) or []
            existing = existing_rows[0] if isinstance(existing_rows, list) and existing_rows else None
        except Exception as lookup_err:
            print(f"Notice: profile existence check failed: {lookup_err}")

        if existing:
            return jsonify({"message": "Profile is ready.", "profile_created": False}), 200

        raw_meta: Any = getattr(user, "user_metadata", {}) or {}
        meta: Dict[str, Any] = cast(Dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else {}
        email = str(getattr(user, "email", "") or "").strip().lower()
        display_name = str(meta.get("display_name", "") or "").strip() or (email.split("@", 1)[0] if email else "Cat Lover")
        phone = str(meta.get("phone_number", "") or meta.get("phone", "") or "").strip() or None
        bio = str(meta.get("bio", "") or "").strip() or None
        avatar_url = str(meta.get("avatar_url", "") or "").strip() or None

        payload: Dict[str, Any] = {
            "id": user_id,
            "email": email or None,
            "display_name": display_name,
            "phone": phone,
            "bio": bio,
            "avatar_url": avatar_url,
            "role": "user",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            insert_res = supabase_admin.table("profiles").insert(payload).execute()
            inserted = getattr(insert_res, "data", None) or []
            if not inserted:
                return jsonify({"error": "Could not create the profile row."}), 500
            return jsonify({"message": "Profile created.", "profile_created": True}), 201
        except Exception as insert_err:
            # A concurrent trigger may have created the row between the SELECT and INSERT.
            try:
                verify_res = supabase_admin.table("profiles").select("id").eq("id", user_id).limit(1).execute()
                verify_rows = getattr(verify_res, "data", None) or []
                if isinstance(verify_rows, list) and verify_rows:
                    return jsonify({"message": "Profile is ready.", "profile_created": False}), 200
            except Exception:
                pass
            return jsonify({"error": f"Could not ensure profile: {insert_err}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Email changes must go through Supabase Auth's confirmation flow on the client.
# The server never changes a user's Auth email directly for self-service profile edits.

@app.route("/api/user/profile/sync-email", methods=["POST"])
@require_auth
def sync_confirmed_email() -> Any:
    try:
        user = getattr(g, "user", None)
        user_id = str(getattr(user, "id", ""))
        confirmed_email = str(getattr(user, "email", "") or "").strip().lower()
        if not user_id or not confirmed_email:
            return jsonify({"error": "Authenticated user email is unavailable."}), 401

        if not supabase_admin:
            return jsonify({"error": "Supabase admin client is not configured."}), 500

        # This endpoint is called only after Supabase Auth has completed the
        # email confirmation redirect, so it is safe to synchronize the public
        # profile with the Auth user's now-active email.
        safe_db_update(
            "profiles",
            {"email": confirmed_email, "updated_at": datetime.now(timezone.utc).isoformat()},
            "id",
            user_id,
        )
        return jsonify({"message": "Confirmed email synchronized.", "email": confirmed_email}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user/profile", methods=["PUT"])
@require_auth
def sync_user_profile() -> Any:
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}

        new_name = str(data.get("display_name", "")).strip()
        new_avatar = str(data.get("avatar_url", "")).strip()
        new_phone = str(data.get("phone", "") or data.get("phone_number", "")).strip()
        new_bio = str(data.get("bio", "")).strip()

        cat_updates: Dict[str, Any] = {}
        comment_updates: Dict[str, Any] = {}

        if new_name:
            cat_updates["user_name"] = new_name
            comment_updates["user_name"] = new_name
        if new_avatar:
            cat_updates["user_avatar"] = new_avatar
            comment_updates["user_avatar"] = new_avatar
            user_avatar_cache[user_id] = new_avatar

        if supabase_admin:
            if cat_updates:
                safe_db_update("cats", cat_updates, "user_id", user_id)
            if comment_updates:
                safe_db_update("comments", comment_updates, "user_id", user_id)

            # Update profiles table
            profile_data: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
            if new_name: profile_data["display_name"] = new_name
            if new_avatar: profile_data["avatar_url"] = new_avatar
            if new_phone: profile_data["phone"] = new_phone
            if new_bio: profile_data["bio"] = new_bio
            safe_db_update("profiles", profile_data, "id", user_id)

            try:
                auth_meta: Dict[str, Any] = {}
                if new_name: auth_meta["display_name"] = new_name
                if new_avatar: auth_meta["avatar_url"] = new_avatar
                if new_phone: auth_meta["phone_number"] = new_phone
                if new_bio: auth_meta["bio"] = new_bio
                if auth_meta:
                    supabase_admin.auth.admin.update_user_by_id(user_id, {"user_metadata": auth_meta})
            except Exception as ae:
                print(f"Notice: Supabase auth metadata update: {ae}")

        for c in MOCK_CATS:
            if str(c.get("user_id")) == str(user_id):
                if new_name: c["user_name"] = new_name
                if new_avatar: c["user_avatar"] = new_avatar

        return jsonify({
            "message": "User profile synchronized successfully.",
            "display_name": new_name,
            "avatar_url": new_avatar,
            "phone": new_phone,
            "bio": new_bio
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/users/<user_id>/profile", methods=["PUT"])
@require_auth
def admin_edit_user_profile(user_id: str) -> Any:
    try:
        if not is_admin_user(getattr(g, "user", None)):
            return jsonify({"error": "Admin access required."}), 403

        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}

        new_name = str(data.get("display_name", "")).strip()
        new_avatar = str(data.get("avatar_url", "")).strip()
        new_email = str(data.get("email", "")).strip()
        new_phone = str(data.get("phone", "") or data.get("phone_number", "")).strip()
        new_bio = str(data.get("bio", "")).strip()
        new_role = str(data.get("role", "")).strip().lower()

        cat_updates: Dict[str, Any] = {}
        comment_updates: Dict[str, Any] = {}
        if new_name:
            cat_updates["user_name"] = new_name
            comment_updates["user_name"] = new_name
        if new_avatar:
            cat_updates["user_avatar"] = new_avatar
            comment_updates["user_avatar"] = new_avatar
            user_avatar_cache[user_id] = new_avatar

        if supabase_admin:
            if cat_updates:
                safe_db_update("cats", cat_updates, "user_id", user_id)
            if comment_updates:
                safe_db_update("comments", comment_updates, "user_id", user_id)

            # Update profiles table
            profile_data: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
            if new_name: profile_data["display_name"] = new_name
            if new_avatar: profile_data["avatar_url"] = new_avatar
            if new_email: profile_data["email"] = new_email
            if new_phone: profile_data["phone"] = new_phone
            if new_bio: profile_data["bio"] = new_bio
            if new_role: profile_data["role"] = new_role
            safe_db_update("profiles", profile_data, "id", user_id)

            try:
                auth_update: Dict[str, Any] = {}
                meta_update: Dict[str, Any] = {}
                if new_name: meta_update["display_name"] = new_name
                if new_avatar: meta_update["avatar_url"] = new_avatar
                if new_phone: meta_update["phone_number"] = new_phone
                if new_bio: meta_update["bio"] = new_bio
                if new_role: meta_update["role"] = new_role
                if meta_update: auth_update["user_metadata"] = meta_update
                if new_email: auth_update["email"] = new_email
                if auth_update:
                    supabase_admin.auth.admin.update_user_by_id(
                        user_id,
                        cast(Any, auth_update)
                    )
            except Exception as ae:
                print(f"Notice: Admin auth update user: {ae}")

        for c in MOCK_CATS:
            if str(c.get("user_id")) == str(user_id):
                if new_name: c["user_name"] = new_name
                if new_avatar: c["user_avatar"] = new_avatar

        return jsonify({
            "message": "User profile updated by admin successfully.",
            "user_id": user_id,
            "display_name": new_name,
            "email": new_email,
            "phone": new_phone,
            "role": new_role
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/users/<user_id>/force-delete", methods=["DELETE", "POST"])
@require_auth
def admin_force_delete_user(user_id: str) -> Any:
    try:
        if not is_admin_user(getattr(g, "user", None)):
            return jsonify({"error": "Admin access required."}), 403

        if supabase_admin:
            try:
                user_cats = getattr(supabase_admin.table("cats").select("id, image_url").eq("user_id", user_id).execute(), "data", [])
                if isinstance(user_cats, list):
                    for uc in user_cats:
                        cid = str(uc.get("id"))
                        supabase_admin.table("likes").delete().eq("cat_id", cid).execute()
                        supabase_admin.table("comments").delete().eq("cat_id", cid).execute()
                        supabase_admin.table("notifications").delete().eq("cat_id", cid).execute()

                        img_url = str(uc.get("image_url", ""))
                        if r2_client and R2_PUBLIC_DOMAIN and img_url.startswith(R2_PUBLIC_DOMAIN + "/"):
                            object_key = img_url[len(R2_PUBLIC_DOMAIN) + 1:].split("?")[0]
                            try:
                                r2_client.delete_object(Bucket=R2_BUCKET_NAME, Key=object_key)
                            except Exception as r2e:
                                print(f"Notice: R2 delete user cat image: {r2e}")

                supabase_admin.table("cats").delete().eq("user_id", user_id).execute()
                supabase_admin.table("comments").delete().eq("user_id", user_id).execute()
                supabase_admin.table("likes").delete().eq("user_id", user_id).execute()
                supabase_admin.table("notifications").delete().eq("user_id", user_id).execute()
                supabase_admin.table("profiles").delete().eq("id", user_id).execute()

                # Remove all R2 media owned by this user.
                delete_r2_prefix(f"{user_id}/")
                delete_r2_prefix(f"avatars/{user_id}/")

                try:
                    supabase_admin.auth.admin.delete_user(user_id)
                except Exception:
                    pass
            except Exception as de:
                print(f"Notice: Supabase admin delete user: {de}")

        user_cat_ids = {str(c.get("id")) for c in MOCK_CATS if str(c.get("user_id")) == str(user_id)}
        MOCK_CATS[:] = [c for c in MOCK_CATS if str(c.get("user_id")) != str(user_id)]
        MOCK_COMMENTS[:] = [cm for cm in MOCK_COMMENTS if str(cm.get("user_id")) != str(user_id) and str(cm.get("cat_id")) not in user_cat_ids]
        MOCK_LIKES[:] = [l for l in MOCK_LIKES if str(l.get("user_id")) != str(user_id) and str(l.get("cat_id")) not in user_cat_ids]
        MOCK_NOTIFICATIONS[:] = [n for n in MOCK_NOTIFICATIONS if str(n.get("user_id")) != str(user_id) and str(n.get("actor_id")) != str(user_id) and str(n.get("cat_id")) not in user_cat_ids]

        if user_id in user_avatar_cache:
            del user_avatar_cache[user_id]

        return jsonify({"message": "User and all associated data force deleted successfully.", "user_id": user_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/user/<user_id>/profile", methods=["GET"])
def get_public_profile(user_id: str) -> Any:
    cats: List[Dict[str, Any]] = []
    user_name = ""
    user_avatar = ""
    user_phone = ""
    user_bio = ""
    user_found = False

    if supabase_admin:
        # Profile row is the canonical lightweight user record. Read it first so
        # we normally avoid the slower Auth Admin lookup entirely.
        try:
            p_res: Any = supabase_admin.table("profiles").select("id,display_name,avatar_url,phone,bio,email").eq("id", user_id).limit(1).execute()
            p_data: Any = getattr(p_res, "data", None) or []
            if isinstance(p_data, list) and p_data:
                row = p_data[0]
                user_found = True
                user_name = str(row.get("display_name", "") or "")
                user_avatar = str(row.get("avatar_url", "") or "")
                user_phone = str(row.get("phone", "") or "")
                user_bio = str(row.get("bio", "") or "")
        except Exception as e:
            print(f"Notice: Supabase profile lookup error: {e}")

        # Cat list is the second and final normal query.
        try:
            raw_data: Any = getattr(
                supabase_admin.table("cats")
                .select("id,user_id,user_name,user_avatar,name,bio,description,image_url,likes_count,created_at")
                .eq("user_id", user_id).order("created_at", desc=True).execute(),
                "data", []
            )
            cats = cast(List[Dict[str, Any]], raw_data) if isinstance(raw_data, list) else []
            if cats:
                user_found = True
        except Exception as e:
            print(f"Notice: Supabase get_public_profile cats error: {e}")

        # Compatibility for legacy accounts created before profiles were added.
        if not user_found:
            try:
                u_obj: Any = supabase_admin.auth.admin.get_user_by_id(user_id)
                u_data: Any = getattr(u_obj, "user", None) or getattr(u_obj, "data", None)
                if u_data:
                    user_found = True
                    u_meta = getattr(u_data, "user_metadata", {}) or {}
                    if not isinstance(u_meta, dict):
                        u_meta = {}
                    user_name = str(u_meta.get("display_name", "")).strip() or str(getattr(u_data, "email", "Cat Lover")).split("@")[0]
                    user_avatar = str(u_meta.get("avatar_url", "")).strip()
                    user_phone = str(u_meta.get("phone_number", "") or getattr(u_data, "phone", "")).strip()
                    user_bio = str(u_meta.get("bio", "")).strip()
            except Exception:
                pass

    if not user_found:
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

    if not user_found:
        return jsonify({"error": "User not found"}), 404

    for c in cats:
        c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))

    if cats:
        if not user_name:
            user_name = str(cats[0].get("user_name", "Cat Lover"))
        if not user_avatar:
            user_avatar = str(cats[0].get("user_avatar", ""))

    if not user_avatar:
        user_avatar = resolve_user_avatar(user_id, user_name or "Cat Lover", None)
    if not user_name:
        user_name = "Cat Lover"

    return jsonify({
        "user_id": user_id,
        "cats_count": len(cats),
        "user_name": user_name,
        "user_avatar": user_avatar,
        "phone": user_phone,
        "bio": user_bio,
        "total_likes": sum(int(c.get("likes_count", 0) or 0) for c in cats),
        "cats": cats
    }), 200


@app.route("/api/user/my-cats", methods=["GET"])
@require_auth
def get_my_cats() -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    cats: List[Dict[str, Any]] = []

    if supabase_admin:
        try:
            raw_data = getattr(supabase_admin.table("cats").select("id,user_id,user_name,user_avatar,name,bio,description,image_url,likes_count,created_at").eq("user_id", user_id).order("created_at", desc=True).execute(), "data", [])
            cats = cast(List[Dict[str, Any]], raw_data) if isinstance(raw_data, list) else []
        except Exception:
            pass

    if not cats:
        cats = [c for c in MOCK_CATS if str(c.get("user_id")) == user_id]

    return jsonify({"cats": cats}), 200


@app.route("/api/user/liked-cats", methods=["GET"])
@require_auth
def get_user_liked_cats() -> Any:
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    liked_cat_ids: List[str] = []

    if supabase_admin:
        try:
            raw_data = getattr(supabase_admin.table("likes").select("cat_id").eq("user_id", user_id).execute(), "data", [])
            if isinstance(raw_data, list):
                liked_cat_ids = [str(item.get("cat_id")) for item in raw_data if item.get("cat_id")]
        except Exception:
            pass

    if not liked_cat_ids:
        liked_cat_ids = [str(l.get("cat_id")) for l in MOCK_LIKES if str(l.get("user_id")) == user_id]

    return jsonify({"liked_cat_ids": liked_cat_ids}), 200


@app.route("/api/admin/overview", methods=["GET"])
@require_auth
def admin_overview() -> Any:
    try:
        is_admin = is_admin_user(getattr(g, "user", None))
        if not is_admin:
            user_email = str(getattr(getattr(g, "user", None), "email", "") or "").lower()
            return jsonify({"error": f"Admin access restricted. Your account '{user_email}' is not configured as admin."}), 403

        cats: List[Dict[str, Any]] = []
        if supabase_admin:
            try:
                raw_data: Any = getattr(supabase_admin.table("cats").select("*").order("created_at", desc=True).execute(), "data", [])
                cats = cast(List[Dict[str, Any]], raw_data) if isinstance(raw_data, list) else []
            except Exception as ce:
                print(f"Admin overview cats notice: {ce}")

        if not cats:
            cats = list(MOCK_CATS)

        for c in cats:
            c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))

        users_dict: Dict[str, Dict[str, Any]] = {}

        # 1. Populate all registered users from Supabase Auth if available
        if supabase_admin:
            try:
                auth_users_res: Any = supabase_admin.auth.admin.list_users()
                raw_users_list: Any = getattr(auth_users_res, "users", None) or getattr(auth_users_res, "data", None) or auth_users_res
                if isinstance(raw_users_list, list):
                    admin_email_set = {e.strip().lower() for e in ADMIN_EMAIL_CONFIG.split(",") if e.strip()}
                    profile_roles: Dict[str, str] = {}
                    try:
                        all_uids = [str(getattr(u, "id", "") or "") for u in raw_users_list if str(getattr(u, "id", "") or "")]
                        if all_uids:
                            role_rows = getattr(supabase_admin.table("profiles").select("id,role").in_("id", all_uids).execute(), "data", []) or []
                            if isinstance(role_rows, list):
                                profile_roles = {str(r.get("id")): str(r.get("role", "")).lower() for r in role_rows if r.get("id")}
                    except Exception:
                        profile_roles = {}

                    for u in raw_users_list:
                        uid = str(getattr(u, "id", "") or "")
                        if uid:
                            u_email = str(getattr(u, "email", "") or "")
                            u_meta = getattr(u, "user_metadata", {}) or {}
                            if not isinstance(u_meta, dict):
                                u_meta = {}
                            disp_name = str(u_meta.get("display_name", "")).strip() or u_email.split("@")[0] or "Cat Lover"
                            avatar_url = str(u_meta.get("avatar_url", "")).strip() or resolve_user_avatar(uid, disp_name, None)
                            phone_val = str(u_meta.get("phone_number", "") or getattr(u, "phone", "") or "").strip()
                            role_val = "admin" if u_email.lower() in admin_email_set or profile_roles.get(uid) == "admin" else "user"

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
                print(f"Notice: Admin auth list users: {ue}")

        # 2. Enrich/aggregate stats from uploaded cats
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
                        "email": f"{uname.lower().replace(' ', '')}@example.com",
                        "phone": "—",
                        "role": "user",
                        "cats_count": 0,
                        "cat_count": 0,
                        "total_likes": 0
                    }
                users_dict[uid]["cats_count"] += 1
                users_dict[uid]["cat_count"] += 1
                users_dict[uid]["total_likes"] += int(c.get("likes_count", 0) or 0)

        # 3. Add mock users if in-memory fallback is active
        for mc in MOCK_CATS:
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
                print(f"Notice: Admin overview comments fetch: {ce}")

        if not all_comments:
            all_comments = list(MOCK_COMMENTS)

        return jsonify({
            "total_cats": len(cats),
            "total_likes": sum(int(c.get("likes_count", 0) or 0) for c in cats),
            "total_users": len(users_dict),
            "total_comments": len(all_comments),
            "cats": cats,
            "users": user_list,
            "comments": all_comments
        }), 200

    except Exception as e:
        return jsonify({"error": f"Failed to load admin overview: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
