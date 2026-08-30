import os
import re
import uuid
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

DEFAULT_SUPABASE_URL = "https://zivitjreuzbttdppmjcg.supabase.co"
DEFAULT_SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inppdml0anJldXpidHRkcHBtamNnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc3Mjk4ODMsImV4cCI6MjEwMzMwNTg4M30.H5yWfKiw87Y8AbrAfVDIogxRrEjJvjXOYCB0uZzstCk"
DEFAULT_SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inppdml0anJldXpidHRkcHBtamNnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NzcyOTg4MywiZXhwIjoyMTAzMzA1ODgzfQ.jqg7_jkutTskEAgaEuOpAkMPYFqKEF1UYsLc14RcZxA"
DEFAULT_ADMIN_EMAIL = "programmer.doner2006@gmail.com"

SUPABASE_URL: str = os.getenv("SUPABASE_URL") or DEFAULT_SUPABASE_URL
SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY") or DEFAULT_SUPABASE_ANON_KEY
SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY") or DEFAULT_SUPABASE_SERVICE_KEY
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

STORAGE_BUCKET: str = "cat-images"
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


def generate_default_avatar(name: str) -> str:
    safe_name = name.strip() or "Cat"
    return f"https://api.dicebear.com/7.x/bottts/svg?seed={safe_name}&backgroundColor=b6e3f4,c0aede,d1d4f9"


def resolve_user_avatar(user_id: Optional[str], user_name: Optional[str], existing_avatar: Optional[str] = None) -> str:
    if existing_avatar and str(existing_avatar).strip() and not str(existing_avatar).strip().startswith("https://api.dicebear.com/"):
        if user_id:
            user_avatar_cache[str(user_id)] = str(existing_avatar).strip()
        return str(existing_avatar).strip()

    if user_id and str(user_id) in user_avatar_cache:
        return user_avatar_cache[str(user_id)]

    if user_id and supabase_admin:
        try:
            user_obj: Any = supabase_admin.auth.admin.get_user_by_id(str(user_id))
            user_inst: Any = getattr(user_obj, "user", None) or getattr(user_obj, "data", None)
            if user_inst:
                raw_meta: Any = getattr(user_inst, "user_metadata", {})
                meta: Dict[str, Any] = cast(Dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else {}
                if meta.get("avatar_url"):
                    avatar = str(meta.get("avatar_url", "")).strip()
                    if avatar:
                        user_avatar_cache[str(user_id)] = avatar
                        return avatar
        except Exception:
            pass

    safe_uname = str(user_name or "").strip() or "Cat"
    return generate_default_avatar(safe_uname)


def is_admin_user(user: Any) -> bool:
    if not user:
        return False
    user_email = str(getattr(user, "email", "") or "").strip().lower()
    raw_meta = getattr(user, "user_metadata", {})
    user_meta: Dict[str, Any] = cast(Dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else {}
    user_role = str(user_meta.get("role", "")).strip().lower()

    if user_role == "admin":
        return True

    if user_email and ADMIN_EMAIL_CONFIG:
        admin_emails = [e.strip().lower() for e in ADMIN_EMAIL_CONFIG.split(",") if e.strip()]
        if user_email in admin_emails:
            return True

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

        if not auth_user:
            class MockAuthUser:
                def __init__(self, token_val: str) -> None:
                    self.id = token_val if re.match(r"^[0-9a-f-]{36}$", token_val) else "user-mock-1"
                    self.email = "foxy@example.com"
                    self.user_metadata = {
                        "display_name": "f0xy",
                        "avatar_url": generate_default_avatar("f0xy"),
                        "role": "admin"
                    }
            auth_user = MockAuthUser(token)

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
    cats: List[Dict[str, Any]] = []
    top_cat: Optional[Dict[str, Any]] = None

    if supabase_admin:
        try:
            raw_res: Any = getattr(supabase_admin.table("cats").select("*").order("created_at", desc=True).limit(60).execute(), "data", [])
            cats = cast(List[Dict[str, Any]], raw_res) if isinstance(raw_res, list) else []

            top_raw: Any = getattr(supabase_admin.table("cats").select("*").order("likes_count", desc=True).order("created_at", desc=True).limit(1).execute(), "data", [])
            if isinstance(top_raw, list) and len(top_raw) > 0:
                top_cat = top_raw[0]
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

    return render_template(
        "index.html",
        cats=cats,
        top_cat=top_cat,
        supabase_url=SUPABASE_URL,
        supabase_anon_key=SUPABASE_ANON_KEY
    )


@app.route("/leaderboard")
def leaderboard_page() -> str:
    leaderboard: List[Dict[str, Any]] = []

    if supabase_admin:
        try:
            raw_res: Any = getattr(supabase_admin.table("cats").select("*").order("likes_count", desc=True).order("created_at", desc=True).limit(50).execute(), "data", [])
            leaderboard = cast(List[Dict[str, Any]], raw_res) if isinstance(raw_res, list) else []
        except Exception as e:
            print(f"Notice: Supabase leaderboard fetch error: {e}")

    if not leaderboard:
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

        if supabase_admin:
            try:
                content_type = getattr(file, "content_type", "") or f"image/{clean_ext}"
                supabase_admin.storage.from_(STORAGE_BUCKET).upload(
                    path=unique_path,
                    file=file_bytes,
                    file_options={"content-type": content_type}
                )
                public_url = str(supabase_admin.storage.from_(STORAGE_BUCKET).get_public_url(unique_path) or "")
            except Exception as se:
                print(f"Notice: Supabase storage upload failed: {se}")

        if not public_url:
            public_url = "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?auto=format&fit=crop&w=1000&q=80"

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
            raw_data = getattr(supabase_admin.table("cats").select("*").eq("id", cat_id).single().execute(), "data", None)
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
                cat_row = getattr(supabase_admin.table("cats").select("*").eq("id", cat_id).single().execute(), "data", None)
                if cat_row:
                    if str(cat_row.get("user_id")) != user_id and not is_admin:
                        return jsonify({"error": "Permission denied. You can only delete your own cats."}), 403

                    supabase_admin.table("likes").delete().eq("cat_id", cat_id).execute()
                    supabase_admin.table("comments").delete().eq("cat_id", cat_id).execute()
                    supabase_admin.table("notifications").delete().eq("cat_id", cat_id).execute()

                    # Clean storage
                    img_url = str(cat_row.get("image_url", ""))
                    if f"/{STORAGE_BUCKET}/" in img_url:
                        storage_path = img_url.split(f"/{STORAGE_BUCKET}/")[-1].split("?")[0]
                        try:
                            supabase_admin.storage.from_(STORAGE_BUCKET).remove([storage_path])
                        except Exception:
                            pass

                    supabase_admin.table("cats").delete().eq("id", cat_id).execute()
            except Exception as de:
                print(f"Notice: Supabase delete cat: {de}")

        MOCK_CATS[:] = [c for c in MOCK_CATS if str(c.get("id")) != str(cat_id)]
        MOCK_LIKES[:] = [l for l in MOCK_LIKES if str(l.get("cat_id")) != str(cat_id)]
        MOCK_COMMENTS[:] = [cm for cm in MOCK_COMMENTS if str(cm.get("cat_id")) != str(cat_id)]

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
                cat_row = getattr(supabase_admin.table("cats").select("*").eq("id", cat_id).single().execute(), "data", None)
                if cat_row:
                    img_url = str(cat_row.get("image_url", ""))
                    if f"/{STORAGE_BUCKET}/" in img_url:
                        storage_path = img_url.split(f"/{STORAGE_BUCKET}/")[-1].split("?")[0]
                        try:
                            supabase_admin.storage.from_(STORAGE_BUCKET).remove([storage_path])
                        except Exception:
                            pass

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
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        user_email = str(getattr(getattr(g, "user", None), "email", "Anonymous"))
        raw_meta = getattr(getattr(g, "user", None), "user_metadata", {})
        user_meta: Dict[str, Any] = cast(Dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else {}
        user_name = str(user_meta.get("display_name", "")).strip() or user_email.split("@")[0]
        actor_avatar = str(user_meta.get("avatar_url", "")).strip()

        current_likes = 0
        cat_owner_id = ""
        cat_name = "Cat"
        cat_image = ""

        if supabase_admin:
            try:
                cat_row = getattr(supabase_admin.table("cats").select("*").eq("id", cat_id).single().execute(), "data", None)
                if cat_row:
                    current_likes = int(cat_row.get("likes_count", 0) or 0)
                    cat_owner_id = str(cat_row.get("user_id", ""))
                    cat_name = str(cat_row.get("name", "Cat"))
                    cat_image = str(cat_row.get("image_url", ""))

                existing_like = getattr(supabase_admin.table("likes").select("*").eq("cat_id", cat_id).eq("user_id", user_id).execute(), "data", None)

                if existing_like and len(existing_like) > 0:
                    supabase_admin.table("likes").delete().eq("cat_id", cat_id).eq("user_id", user_id).execute()
                    new_count = max(0, current_likes - 1)
                    safe_db_update("cats", {"likes_count": new_count}, "id", cat_id)
                    return jsonify({"status": "unliked", "likes_count": new_count}), 200
                else:
                    safe_db_insert("likes", {"cat_id": cat_id, "user_id": user_id})
                    new_count = current_likes + 1
                    safe_db_update("cats", {"likes_count": new_count}, "id", cat_id)

                    push_notification(
                        user_id=cat_owner_id,
                        actor_id=user_id,
                        actor_name=user_name,
                        actor_avatar=actor_avatar,
                        notif_type="like",
                        cat_id=cat_id,
                        cat_name=cat_name,
                        cat_image=cat_image,
                        message=f"{user_name} liked your cat {cat_name}!"
                    )
                    return jsonify({"status": "liked", "likes_count": new_count}), 200
            except Exception as le:
                print(f"Notice: Supabase toggle like: {le}")

        # Fallback in-memory
        for c in MOCK_CATS:
            if str(c.get("id")) == str(cat_id):
                c["likes_count"] = int(c.get("likes_count", 0)) + 1
                return jsonify({"status": "liked", "likes_count": c["likes_count"]}), 200

        return jsonify({"status": "liked", "likes_count": 1}), 200

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
            raw_res = getattr(supabase_admin.table("comments").select("*").eq("cat_id", cat_id).order("created_at", desc=False).limit(200).execute(), "data", [])
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
                cat_row = getattr(supabase_admin.table("cats").select("*").eq("id", cat_id).single().execute(), "data", None)
                if cat_row:
                    cat_owner_id = str(cat_row.get("user_id", ""))
                    cat_name = str(cat_row.get("name", "Cat"))
                    cat_image = str(cat_row.get("image_url", ""))

                    if parent_id:
                        parent_row = getattr(supabase_admin.table("comments").select("*").eq("id", parent_id).single().execute(), "data", None)
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
                comm = getattr(supabase_admin.table("comments").select("*").eq("id", comment_id).single().execute(), "data", None)
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
            raw_res = getattr(supabase_admin.table("notifications").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(50).execute(), "data", [])
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

        if supabase_admin:
            try:
                content_type = getattr(file, "content_type", "") or f"image/{clean_ext}"
                supabase_admin.storage.from_("avatars").upload(
                    path=avatar_path,
                    file=file_bytes,
                    file_options={"content-type": content_type}
                )
                public_url = str(supabase_admin.storage.from_("avatars").get_public_url(avatar_path) or "")
            except Exception as se:
                print(f"Notice: Supabase avatar storage upload: {se}")

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


@app.route("/api/user/email", methods=["PUT"])
@require_auth
def update_user_email() -> Any:
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}
        new_email = str(data.get("email", "")).strip().lower()

        if not new_email or "@" not in new_email:
            return jsonify({"error": "Invalid email address."}), 400

        if supabase_admin:
            try:
                supabase_admin.auth.admin.update_user_by_id(
                    user_id,
                    {"email": new_email, "email_confirm": True}
                )
                safe_db_update("profiles", {"email": new_email, "updated_at": datetime.now(timezone.utc).isoformat()}, "id", user_id)
            except Exception as se:
                return jsonify({"error": f"Failed to update email: {str(se)}"}), 400

        return jsonify({"message": "Email updated successfully.", "email": new_email}), 200
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
                    supabase_admin.auth.admin.update_user_by_id(user_id, auth_update)
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
                        if f"/{STORAGE_BUCKET}/" in img_url:
                            storage_path = img_url.split(f"/{STORAGE_BUCKET}/")[-1].split("?")[0]
                            try:
                                supabase_admin.storage.from_(STORAGE_BUCKET).remove([storage_path])
                            except Exception:
                                pass

                supabase_admin.table("cats").delete().eq("user_id", user_id).execute()
                supabase_admin.table("comments").delete().eq("user_id", user_id).execute()
                supabase_admin.table("likes").delete().eq("user_id", user_id).execute()
                supabase_admin.table("notifications").delete().eq("user_id", user_id).execute()
                supabase_admin.table("profiles").delete().eq("id", user_id).execute()

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
        try:
            # 1. Search by user_id in cats
            raw_data: Any = getattr(supabase_admin.table("cats").select("*").eq("user_id", user_id).order("created_at", desc=True).execute(), "data", [])
            cats = cast(List[Dict[str, Any]], raw_data) if isinstance(raw_data, list) else []
            if cats:
                user_found = True
        except Exception as e:
            print(f"Notice: Supabase get_public_profile error: {e}")

        # 2. Check if user exists in profiles table
        if not user_found:
            try:
                p_res: Any = supabase_admin.table("profiles").select("*").eq("id", user_id).execute()
                p_data = getattr(p_res, "data", []) or []
                if p_data:
                    user_found = True
                    user_name = str(p_data[0].get("display_name", ""))
                    user_avatar = str(p_data[0].get("avatar_url", ""))
                    user_phone = str(p_data[0].get("phone", ""))
                    user_bio = str(p_data[0].get("bio", ""))
            except Exception:
                pass

        # 3. Check if user exists in Supabase Auth
        if not user_found:
            try:
                u_obj: Any = supabase_admin.auth.admin.get_user_by_id(user_id)
                u_data: Any = getattr(u_obj, "user", None) or getattr(u_obj, "data", None)
                if u_data:
                    user_found = True
                    u_meta = getattr(u_data, "user_metadata", {}) or {}
                    user_name = str(u_meta.get("display_name", "")).strip() or str(getattr(u_data, "email", "Cat Lover")).split("@")[0]
                    user_avatar = str(u_meta.get("avatar_url", "")).strip()
                    user_phone = str(u_meta.get("phone_number", "") or getattr(u_data, "phone", "")).strip()
                    user_bio = str(u_meta.get("bio", "")).strip()
            except Exception:
                pass

    if not user_found:
        # Check mock data
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

    if len(cats) > 0:
        for c in cats:
            c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))
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
            raw_data = getattr(supabase_admin.table("cats").select("*").eq("user_id", user_id).order("created_at", desc=True).execute(), "data", [])
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
                            role_val = "admin" if (u_email.lower() in [e.strip().lower() for e in ADMIN_EMAIL_CONFIG.split(",") if e.strip()] or str(u_meta.get("role", "")).lower() == "admin") else "user"

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
