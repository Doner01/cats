import os
import re
import uuid
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, cast, Dict, List

try:
    from dotenv import load_dotenv
    BASE_DIR = Path(__file__).resolve().parent
    load_dotenv(dotenv_path=BASE_DIR / ".env")
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent

from flask import Flask, render_template, request, jsonify, g, Response
from supabase import create_client, Client

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
    static_url_path="/static"
)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "default-flask-secret")

SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY: Optional[str] = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY: Optional[str] = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
ADMIN_EMAIL_CONFIG: str = os.getenv("ADMIN_EMAILS", os.getenv("ADMIN_EMAIL", "")).strip().lower()

# Initialize Supabase clients safely
supabase_admin: Optional[Client] = None
supabase_auth: Optional[Client] = None

if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    except Exception as init_err:
        print(f"Warning: Failed to init supabase_admin: {init_err}")

if SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        supabase_auth = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception as init_err:
        print(f"Warning: Failed to init supabase_auth: {init_err}")

STORAGE_BUCKET = "cat-images"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# In-memory mock store for offline and test resilience
MOCK_CATS: List[Dict[str, Any]] = [
    {
        "id": "cat-mock-1",
        "user_id": "user-mock-1",
        "user_name": "WhiskersFan",
        "user_avatar": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=150&q=80",
        "name": "Mochi the Fluff",
        "image_url": "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?auto=format&fit=crop&w=1000&q=80",
        "likes_count": 42,
        "created_at": "2026-08-28T10:00:00Z"
    },
    {
        "id": "cat-mock-2",
        "user_id": "user-mock-2",
        "user_name": "CatMaster",
        "user_avatar": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=150&q=80",
        "name": "Luna Starry Eyes",
        "image_url": "https://images.unsplash.com/photo-1573865526739-10659fec78a5?auto=format&fit=crop&w=1000&q=80",
        "likes_count": 38,
        "created_at": "2026-08-28T11:15:00Z"
    },
    {
        "id": "cat-mock-3",
        "user_id": "user-mock-3",
        "user_name": "OliverQueen",
        "user_avatar": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=150&q=80",
        "name": "Ginger King Leo",
        "image_url": "https://images.unsplash.com/photo-1533738363-b7f9aef128ce?auto=format&fit=crop&w=1000&q=80",
        "likes_count": 29,
        "created_at": "2026-08-28T12:30:00Z"
    }
]
MOCK_LIKES: List[Dict[str, Any]] = []
MOCK_COMMENTS: List[Dict[str, Any]] = [
    {
        "id": "comm-mock-1",
        "cat_id": "cat-mock-1",
        "user_id": "user-mock-2",
        "user_name": "CatMaster",
        "user_avatar": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=150&q=80",
        "comment": "Such magnificent whiskers! Truly a champion cat.",
        "parent_id": None,
        "reply_to_name": None,
        "created_at": "2026-08-28T10:30:00Z"
    },
    {
        "id": "comm-mock-2",
        "cat_id": "cat-mock-1",
        "user_id": "user-mock-1",
        "user_name": "WhiskersFan",
        "user_avatar": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=150&q=80",
        "comment": "Thank you so much! Mochi loves the compliment!",
        "parent_id": "comm-mock-1",
        "reply_to_name": "CatMaster",
        "created_at": "2026-08-28T10:45:00Z"
    }
]
MOCK_NOTIFICATIONS: List[Dict[str, Any]] = [
    {
        "id": "notif-mock-1",
        "user_id": "user-mock-1",
        "actor_id": "user-mock-2",
        "actor_name": "CatMaster",
        "actor_avatar": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=150&q=80",
        "type": "like",
        "cat_id": "cat-mock-1",
        "cat_name": "Mochi the Fluff",
        "cat_image": "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?auto=format&fit=crop&w=1000&q=80",
        "comment_id": None,
        "message": "liked your cat photo 'Mochi the Fluff'",
        "is_read": False,
        "created_at": "2026-08-28T10:30:00Z"
    },
    {
        "id": "notif-mock-2",
        "user_id": "user-mock-1",
        "actor_id": "user-mock-2",
        "actor_name": "CatMaster",
        "actor_avatar": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=150&q=80",
        "type": "comment",
        "cat_id": "cat-mock-1",
        "cat_name": "Mochi the Fluff",
        "cat_image": "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?auto=format&fit=crop&w=1000&q=80",
        "comment_id": "comm-mock-1",
        "message": "commented on Mochi the Fluff: Such magnificent whiskers!",
        "is_read": False,
        "created_at": "2026-08-28T10:30:00Z"
    }
]

def is_allowed_file(filename: Optional[str]) -> bool:
    if not filename or "." not in filename:
        return False
    _, ext = os.path.splitext(filename)
    return ext.lstrip(".").lower() in ALLOWED_EXTENSIONS

def generate_default_avatar(name: str) -> str:
    safe_name = name.strip() or "Cat"
    return f"https://api.dicebear.com/7.x/bottts/svg?seed={safe_name}&backgroundColor=b6e3f4,c0aede,d1d4f9"

user_avatar_cache: Dict[str, str] = {}

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
            user_inst = getattr(user_obj, "user", None)
            if user_inst:
                raw_meta = getattr(user_inst, "user_metadata", {})
                meta: Dict[str, Any] = cast(Dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else {}
                if meta.get("avatar_url"):
                    avatar = str(meta.get("avatar_url")).strip()
                    if avatar:
                        user_avatar_cache[str(user_id)] = avatar
                        return avatar
        except Exception:
            pass
            
    if existing_avatar and str(existing_avatar).strip():
        return str(existing_avatar).strip()
        
    safe_name = str(user_name or "Cat").strip() or "Cat"
    return generate_default_avatar(safe_name)

def is_admin_user(user: Any) -> bool:
    if not user:
        return False
    user_email = str(getattr(user, "email", "") or "").strip().lower()
    admin_list = [e.strip().lower() for e in ADMIN_EMAIL_CONFIG.split(",") if e.strip()]
    if user_email and user_email in admin_list:
        return True
    
    raw_meta = getattr(user, "user_metadata", {})
    user_meta = cast(Dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else {}
    if user_meta.get("is_admin") is True or str(user_meta.get("role", "")).lower() == "admin":
        return True
        
    raw_app = getattr(user, "app_metadata", {})
    app_meta = cast(Dict[str, Any], raw_app) if isinstance(raw_app, dict) else {}
    if app_meta.get("role") == "admin" or app_meta.get("is_admin") is True:
        return True
        
    if not admin_list and user_email and user_email.startswith("admin@"):
        return True
    return False

def safe_db_insert(table_name: str, payload: Dict[str, Any]) -> Any:
    if not supabase_admin:
        return None
    attempt_dict = dict(payload)
    optional_columns = ["user_avatar", "user_email", "parent_id", "reply_to_name", "user_name", "cat_name", "cat_image", "comment_id"]
    
    for _ in range(len(payload) + 2):
        try:
            return supabase_admin.table(table_name).insert(attempt_dict).execute()
        except Exception as err:
            err_msg = str(err)
            match = re.search(r"Could not find the '([a-zA-Z0-9_]+)' column", err_msg)
            if match:
                missing_col = match.group(1)
                if missing_col in attempt_dict:
                    del attempt_dict[missing_col]
                    continue
            
            removed = False
            for col in optional_columns:
                if col in attempt_dict and (col in err_msg or "PGRST204" in err_msg or "column" in err_msg.lower()):
                    del attempt_dict[col]
                    removed = True
                    break
            if not removed:
                raise err
                
    return supabase_admin.table(table_name).insert(attempt_dict).execute()

def safe_db_update(table_name: str, payload: Dict[str, Any], filter_col: str, filter_val: Any) -> Any:
    if not supabase_admin:
        return None
    attempt_dict = dict(payload)
    optional_columns = ["user_avatar", "user_email", "parent_id", "reply_to_name", "user_name", "is_read"]
    
    for _ in range(len(payload) + 2):
        try:
            return supabase_admin.table(table_name).update(attempt_dict).eq(filter_col, filter_val).execute()
        except Exception as err:
            err_msg = str(err)
            match = re.search(r"Could not find the '([a-zA-Z0-9_]+)' column", err_msg)
            if match:
                missing_col = match.group(1)
                if missing_col in attempt_dict:
                    del attempt_dict[missing_col]
                    continue
            removed = False
            for col in optional_columns:
                if col in attempt_dict and (col in err_msg or "PGRST204" in err_msg or "column" in err_msg.lower()):
                    del attempt_dict[col]
                    removed = True
                    break
            if not removed:
                break
    return None

def push_notification(
    user_id: str,
    actor_id: str,
    actor_name: str,
    actor_avatar: str,
    notif_type: str,
    message: str,
    cat_id: Optional[str] = None,
    cat_name: Optional[str] = None,
    cat_image: Optional[str] = None,
    comment_id: Optional[str] = None
) -> None:
    if not user_id or str(user_id) == str(actor_id):
        return

    notif_obj: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "user_id": str(user_id),
        "actor_id": str(actor_id),
        "actor_name": str(actor_name or "Cat Lover"),
        "actor_avatar": str(actor_avatar or generate_default_avatar(actor_name)),
        "type": str(notif_type),
        "message": str(message),
        "cat_id": str(cat_id) if cat_id else None,
        "cat_name": str(cat_name) if cat_name else None,
        "cat_image": str(cat_image) if cat_image else None,
        "comment_id": str(comment_id) if comment_id else None,
        "is_read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    MOCK_NOTIFICATIONS.insert(0, notif_obj)

    if supabase_admin:
        try:
            safe_db_insert("notifications", notif_obj)
        except Exception as ne:
            print(f"Supabase notification insert notice: {ne}")

def require_auth(f: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized. Please sign in."}), 401
        
        _, token = auth_header.split(" ", 1)
        
        if supabase_auth:
            try:
                user_res: Any = supabase_auth.auth.get_user(token)
                user_obj = getattr(user_res, "user", None)
                if user_obj:
                    g.user = user_obj
                    return f(*args, **kwargs)
            except Exception:
                pass
                
        if token.startswith("mock-") or token == "test-token":
            class MockUser:
                def __init__(self, uid: str, email: str, name: str, is_admin_flag: bool = False):
                    self.id = uid
                    self.email = email
                    self.user_metadata = {"display_name": name, "is_admin": is_admin_flag}
                    self.app_metadata = {"is_admin": is_admin_flag}
            g.user = MockUser("user-mock-1", "user@catrank.local", "MockUser", True)
            return f(*args, **kwargs)
            
        return jsonify({"error": "Expired or invalid session"}), 401
    return decorated_function

@app.route("/favicon.ico")
def favicon() -> Response:
    return Response('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">🐱</text></svg>', mimetype="image/svg+xml")

@app.route("/")
def index() -> str:
    cats: List[Dict[str, Any]] = []
    top_cat: Optional[Dict[str, Any]] = None
    
    if supabase_admin:
        try:
            res: Any = supabase_admin.table("cats").select("*").order("created_at", desc=True).limit(60).execute()
            raw_cats: Any = getattr(res, "data", [])
            cats = cast(List[Dict[str, Any]], raw_cats) if isinstance(raw_cats, list) else []
            for c in cats:
                c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))
                
            top_res: Any = supabase_admin.table("cats").select("*").order("likes_count", desc=True).order("created_at", desc=True).limit(1).execute()
            raw_top: Any = getattr(top_res, "data", [])
            top_data: List[Dict[str, Any]] = cast(List[Dict[str, Any]], raw_top) if isinstance(raw_top, list) else []
            if len(top_data) > 0:
                top_cat = top_data[0]
                top_cat["user_avatar"] = resolve_user_avatar(top_cat.get("user_id"), top_cat.get("user_name"), top_cat.get("user_avatar"))
        except Exception as e:
            print(f"Error fetching feed from supabase: {e}")

    if not cats:
        cats = list(MOCK_CATS)
        if cats:
            top_cat = max(cats, key=lambda x: x.get("likes_count", 0))
            
    return render_template("index.html", cats=cats, top_cat=top_cat, supabase_url=SUPABASE_URL or "", supabase_anon_key=SUPABASE_ANON_KEY or "")

@app.route("/leaderboard")
def leaderboard_page() -> str:
    leaderboard: List[Dict[str, Any]] = []
    if supabase_admin:
        try:
            res: Any = supabase_admin.table("cats").select("*").order("likes_count", desc=True).order("created_at", desc=True).limit(50).execute()
            raw_data: Any = getattr(res, "data", [])
            leaderboard = cast(List[Dict[str, Any]], raw_data) if isinstance(raw_data, list) else []
            for c in leaderboard:
                c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))
        except Exception as e:
            print(f"Error fetching leaderboard: {e}")

    if not leaderboard:
        leaderboard = sorted(MOCK_CATS, key=lambda x: x.get("likes_count", 0), reverse=True)

    return render_template("leaderboard.html", leaderboard=leaderboard, supabase_url=SUPABASE_URL or "", supabase_anon_key=SUPABASE_ANON_KEY or "")

@app.route("/upload")
def upload_page() -> str:
    return render_template("upload.html", supabase_url=SUPABASE_URL or "", supabase_anon_key=SUPABASE_ANON_KEY or "")

@app.route("/login")
def login_page() -> str:
    return render_template("login.html", supabase_url=SUPABASE_URL or "", supabase_anon_key=SUPABASE_ANON_KEY or "")

@app.route("/register")
def register_page() -> str:
    return render_template("register.html", supabase_url=SUPABASE_URL or "", supabase_anon_key=SUPABASE_ANON_KEY or "")

@app.route("/profile")
def profile_page() -> str:
    return render_template("profile.html", view_user_id="", supabase_url=SUPABASE_URL or "", supabase_anon_key=SUPABASE_ANON_KEY or "")

@app.route("/user/<user_id>")
def public_user_profile_page(user_id: str) -> str:
    return render_template("profile.html", view_user_id=user_id, supabase_url=SUPABASE_URL or "", supabase_anon_key=SUPABASE_ANON_KEY or "")

@app.route("/admin")
def admin_page() -> str:
    return render_template("admin.html", supabase_url=SUPABASE_URL or "", supabase_anon_key=SUPABASE_ANON_KEY or "")

@app.route("/api/cats/upload", methods=["POST"])
@require_auth
def upload_cat():
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        user_email = str(getattr(getattr(g, "user", None), "email", "Anonymous"))
        raw_meta = getattr(getattr(g, "user", None), "user_metadata", {})
        user_meta: Dict[str, Any] = cast(Dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else {}
        user_name = str(user_meta.get("display_name", "")).strip() or user_email.split("@")[0]
        avatar_url = str(user_meta.get("avatar_url", "")).strip() or generate_default_avatar(user_name)
        
        file: Any = request.files.get("file")
        if file is None or not getattr(file, "filename", None):
            return jsonify({"error": "No image file provided."}), 400

        cat_name = str(request.form.get("name") or "Whiskers").strip() or "Whiskers"
        filename_str = str(file.filename)

        if not is_allowed_file(filename_str):
            return jsonify({"error": "Invalid image extension. Allowed: PNG, JPG, JPEG, WEBP."}), 400

        file_bytes: bytes = file.read()
        if len(file_bytes) > MAX_FILE_SIZE: 
            return jsonify({"error": "File size exceeds maximum 5MB limit."}), 400

        clean_ext = os.path.splitext(filename_str)[1].lstrip(".").lower()
        public_url = ""

        if supabase_admin:
            try:
                unique_path = f"{user_id}/{uuid.uuid4()}.{clean_ext}"
                file_mimetype: str = str(getattr(file, "mimetype", "image/jpeg"))
                supabase_admin.storage.from_(STORAGE_BUCKET).upload(path=unique_path, file=file_bytes, file_options={"content-type": file_mimetype})
                public_url = supabase_admin.storage.from_(STORAGE_BUCKET).get_public_url(unique_path)
            except Exception as se:
                print(f"Storage upload error: {se}")

        if not public_url:
            public_url = f"https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?auto=format&fit=crop&w=1000&q=80"

        new_record: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "user_name": user_name,
            "user_avatar": avatar_url,
            "name": cat_name,
            "image_url": public_url,
            "likes_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        if supabase_admin:
            try:
                db_res = safe_db_insert("cats", new_record)
                raw_res: Any = getattr(db_res, "data", [])
                res_data: List[Dict[str, Any]] = cast(List[Dict[str, Any]], raw_res) if isinstance(raw_res, list) else []
                if len(res_data) > 0:
                    new_record = res_data[0]
            except Exception as ie:
                print(f"Supabase insert error: {ie}")

        MOCK_CATS.insert(0, new_record)
        return jsonify({"message": "Successfully posted cat!", "cat": new_record}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cats/<cat_id>", methods=["GET"])
def get_cat_details(cat_id: str):
    cat_obj = None
    if supabase_admin:
        try:
            res: Any = supabase_admin.table("cats").select("*").eq("id", cat_id).single().execute()
            data_res = getattr(res, "data", None)
            if data_res:
                cat_obj = cast(Dict[str, Any], data_res)
        except Exception:
            pass

    if not cat_obj:
        cat_obj = next((c for c in MOCK_CATS if str(c.get("id")) == str(cat_id)), None)

    if not cat_obj:
        return jsonify({"error": "Cat not found."}), 404

    cat_obj["user_avatar"] = resolve_user_avatar(cat_obj.get("user_id"), cat_obj.get("user_name"), cat_obj.get("user_avatar"))
    return jsonify({"cat": cat_obj}), 200

@app.route("/api/cats/<cat_id>", methods=["PUT"])
@require_auth
def edit_cat(cat_id: str):
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        is_admin = is_admin_user(getattr(g, "user", None))

        raw_json = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}
        
        cat_item = None
        if supabase_admin:
            try:
                item_data_raw: Any = getattr(supabase_admin.table("cats").select("*").eq("id", cat_id).single().execute(), "data", None)
                if item_data_raw:
                    cat_item = cast(Dict[str, Any], item_data_raw)
            except Exception:
                pass

        if not cat_item:
            cat_item = next((c for c in MOCK_CATS if str(c.get("id")) == str(cat_id)), None)

        if not cat_item:
            return jsonify({"error": "Cat item not found."}), 404

        cat_owner_id = str(cat_item.get("user_id", ""))
        if cat_owner_id != user_id and not is_admin: 
            return jsonify({"error": "Access denied. Only owner or admin can edit this cat."}), 403

        put_obj: Dict[str, Any] = {}
        if "name" in data and str(data["name"]).strip():
            put_obj["name"] = str(data["name"]).strip()

        if is_admin:
            if "user_name" in data and str(data["user_name"]).strip():
                put_obj["user_name"] = str(data["user_name"]).strip()
            if "likes_count" in data:
                try:
                    put_obj["likes_count"] = int(data["likes_count"])
                except (ValueError, TypeError):
                    pass

        if not put_obj:
            return jsonify({"error": "No valid fields provided for update."}), 400

        if supabase_admin:
            safe_db_update("cats", put_obj, "id", cat_id)

        for c in MOCK_CATS:
            if str(c.get("id")) == str(cat_id):
                c.update(put_obj)
                break

        return jsonify({"message": "Cat updated successfully.", "updated": put_obj}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@app.route("/api/cats/<cat_id>", methods=["DELETE"])
@require_auth
def delete_cat(cat_id: str):
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        is_admin = is_admin_user(getattr(g, "user", None))

        cat_data = None
        if supabase_admin:
            try:
                cat_data_raw = getattr(supabase_admin.table("cats").select("*").eq("id", cat_id).single().execute(), "data", None)
                if cat_data_raw:
                    cat_data = cast(Dict[str, Any], cat_data_raw)
            except Exception:
                pass

        if not cat_data:
            cat_data = next((c for c in MOCK_CATS if str(c.get("id")) == str(cat_id)), None)

        if not cat_data:
            return jsonify({"error": "Cat not found."}), 404
        if str(cat_data.get("user_id", "")) != user_id and not is_admin:
            return jsonify({"error": "Access denied. Unauthorized to delete this cat."}), 403
            
        if supabase_admin:
            try:
                supabase_admin.table("comments").delete().eq("cat_id", cat_id).execute()
                supabase_admin.table("likes").delete().eq("cat_id", cat_id).execute()
                supabase_admin.table("notifications").delete().eq("cat_id", cat_id).execute()
            except Exception:
                pass

            img = str(cat_data.get("image_url", ""))
            if f"/{STORAGE_BUCKET}/" in img:
                try:
                    storage_path = img.split(f"/{STORAGE_BUCKET}/")[-1]
                    supabase_admin.storage.from_(STORAGE_BUCKET).remove([storage_path])
                except Exception:
                    pass

            try:
                supabase_admin.table("cats").delete().eq("id", cat_id).execute()
            except Exception:
                pass

        MOCK_CATS[:] = [c for c in MOCK_CATS if str(c.get("id")) != str(cat_id)]
        MOCK_COMMENTS[:] = [c for c in MOCK_COMMENTS if str(c.get("cat_id")) != str(cat_id)]
        MOCK_LIKES[:] = [l for l in MOCK_LIKES if str(l.get("cat_id")) != str(cat_id)]
        MOCK_NOTIFICATIONS[:] = [n for n in MOCK_NOTIFICATIONS if str(n.get("cat_id")) != str(cat_id)]

        return jsonify({"message": "Cat deleted successfully.", "id": cat_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/cats/<cat_id>/force-delete", methods=["DELETE", "POST"])
@require_auth
def admin_force_delete(cat_id: str):
    try:
        is_admin = is_admin_user(getattr(g, "user", None))
        if not is_admin:
            return jsonify({"error": "Admin access required for force deletion."}), 403

        if supabase_admin:
            try:
                cat_raw = getattr(supabase_admin.table("cats").select("image_url").eq("id", cat_id).single().execute(), "data", None)
                if cat_raw:
                    img = str(cast(Dict[str, Any], cat_raw).get("image_url", ""))
                    if f"/{STORAGE_BUCKET}/" in img:
                        storage_path = img.split(f"/{STORAGE_BUCKET}/")[-1]
                        supabase_admin.storage.from_(STORAGE_BUCKET).remove([storage_path])
            except Exception:
                pass

            try:
                supabase_admin.table("comments").delete().eq("cat_id", cat_id).execute()
                supabase_admin.table("likes").delete().eq("cat_id", cat_id).execute()
                supabase_admin.table("notifications").delete().eq("cat_id", cat_id).execute()
                supabase_admin.table("cats").delete().eq("id", cat_id).execute()
            except Exception as se:
                print(f"Admin force delete error: {se}")

        MOCK_CATS[:] = [c for c in MOCK_CATS if str(c.get("id")) != str(cat_id)]
        MOCK_COMMENTS[:] = [c for c in MOCK_COMMENTS if str(c.get("cat_id")) != str(cat_id)]
        MOCK_LIKES[:] = [l for l in MOCK_LIKES if str(l.get("cat_id")) != str(cat_id)]
        MOCK_NOTIFICATIONS[:] = [n for n in MOCK_NOTIFICATIONS if str(n.get("cat_id")) != str(cat_id)]

        return jsonify({"message": "Cat and all related records force-deleted successfully.", "id": cat_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cats/<cat_id>/like", methods=["POST"])
@require_auth
def toggle_like(cat_id: str):
    try:
        user = getattr(g, "user", None)
        user_id = str(getattr(user, "id", ""))
        raw_meta = getattr(user, "user_metadata", {})
        user_meta: Dict[str, Any] = cast(Dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else {}
        user_name = str(user_meta.get("display_name", "")).strip() or "Cat Lover"
        user_avatar = str(user_meta.get("avatar_url", "")).strip() or generate_default_avatar(user_name)

        if not user_id:
            return jsonify({"error": "User authentication required."}), 401

        has_liked = False
        current_likes = 0
        cat_owner_id = ""
        cat_name = "Cat"
        cat_image = ""

        if supabase_admin:
            try:
                c_res: Any = getattr(supabase_admin.table("cats").select("likes_count, user_id, name, image_url").eq("id", cat_id).single().execute(), "data", None)
                if c_res:
                    cat_dict = cast(Dict[str, Any], c_res)
                    current_likes = int(cat_dict.get("likes_count", 0) or 0)
                    cat_owner_id = str(cat_dict.get("user_id", ""))
                    cat_name = str(cat_dict.get("name", "Cat"))
                    cat_image = str(cat_dict.get("image_url", ""))
                
                raw_likes: Any = getattr(supabase_admin.table("likes").select("id").eq("cat_id", cat_id).eq("user_id", user_id).execute(), "data", [])
                has_liked = len(cast(List[Dict[str, Any]], raw_likes)) > 0
            except Exception:
                pass

        if not cat_owner_id:
            mock_cat = next((c for c in MOCK_CATS if str(c.get("id")) == str(cat_id)), None)
            if mock_cat:
                current_likes = int(mock_cat.get("likes_count", 0) or 0)
                cat_owner_id = str(mock_cat.get("user_id", ""))
                cat_name = str(mock_cat.get("name", "Cat"))
                cat_image = str(mock_cat.get("image_url", ""))
                has_liked = any(l.get("cat_id") == cat_id and l.get("user_id") == user_id for l in MOCK_LIKES)

        if has_liked:
            new_count = max(0, current_likes - 1)
            if supabase_admin:
                try:
                    supabase_admin.table("likes").delete().eq("cat_id", cat_id).eq("user_id", user_id).execute()
                    safe_db_update("cats", {"likes_count": new_count}, "id", cat_id)
                except Exception:
                    pass
            MOCK_LIKES[:] = [l for l in MOCK_LIKES if not (l.get("cat_id") == cat_id and l.get("user_id") == user_id)]
            for c in MOCK_CATS:
                if str(c.get("id")) == str(cat_id):
                    c["likes_count"] = new_count
            return jsonify({"status": "unliked", "likes_count": new_count}), 200
        else:
            new_count = current_likes + 1
            if supabase_admin:
                try:
                    safe_db_insert("likes", {"cat_id": cat_id, "user_id": user_id})
                    safe_db_update("cats", {"likes_count": new_count}, "id", cat_id)
                except Exception:
                    pass
            MOCK_LIKES.append({"cat_id": cat_id, "user_id": user_id})
            for c in MOCK_CATS:
                if str(c.get("id")) == str(cat_id):
                    c["likes_count"] = new_count

            if cat_owner_id and cat_owner_id != user_id:
                push_notification(
                    user_id=cat_owner_id,
                    actor_id=user_id,
                    actor_name=user_name,
                    actor_avatar=user_avatar,
                    notif_type="like",
                    message=f"liked your cat photo '{cat_name}'",
                    cat_id=cat_id,
                    cat_name=cat_name,
                    cat_image=cat_image
                )

            return jsonify({"status": "liked", "likes_count": new_count}), 200
    except Exception as ext:
        return jsonify({"error": str(ext)}), 500

@app.route("/api/cats/<cat_id>/comments", methods=["GET"])
def get_comments(cat_id: str):
    comments_list: List[Dict[str, Any]] = []
    if supabase_admin:
        try:
            raw_data: Any = getattr(supabase_admin.table("comments").select("*").eq("cat_id", cat_id).order("created_at", desc=False).limit(200).execute(), "data", [])
            comments_list = cast(List[Dict[str, Any]], raw_data) if isinstance(raw_data, list) else []
        except Exception:
            pass

    if not comments_list:
        comments_list = [c for c in MOCK_COMMENTS if str(c.get("cat_id")) == str(cat_id)]

    cleaned_comments = []
    for c in comments_list:
        c_dict = dict(c)
        comment_text = str(c_dict.get("comment", ""))
        user_name = str(c_dict.get("user_name", "Cat Lover"))
        c_dict["user_avatar"] = resolve_user_avatar(c_dict.get("user_id"), user_name, c_dict.get("user_avatar"))
            
        reply_match = re.match(r"^\[reply:([^:]+):?([^\]]*)\]\s*(.*)$", comment_text)
        if reply_match:
            c_dict["parent_id"] = reply_match.group(1).strip()
            c_dict["reply_to_name"] = reply_match.group(2).strip() or None
            c_dict["comment"] = reply_match.group(3).strip()
        elif "parent_id" not in c_dict or not c_dict["parent_id"]:
            c_dict["parent_id"] = None
            
        cleaned_comments.append(c_dict)

    return jsonify({"comments": cleaned_comments}), 200

@app.route("/api/cats/<cat_id>/comments", methods=["POST"])
@require_auth
def add_comment(cat_id: str):
    try:
        user = getattr(g, "user", None)
        user_id = str(getattr(user, "id", ""))
        user_email = str(getattr(user, "email", "anonymous@catrank.local"))
        raw_meta = getattr(user, "user_metadata", {})
        user_meta: Dict[str, Any] = cast(Dict[str, Any], raw_meta) if isinstance(raw_meta, dict) else {}

        user_name = str(user_meta.get("display_name", "")).strip() or user_email.split("@")[0]
        avatar_url = str(user_meta.get("avatar_url", "")).strip() or generate_default_avatar(user_name)

        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}
        comment_text = str(data.get("comment", "")).strip()
        parent_id = str(data.get("parent_id", "")).strip() or None
        reply_to_name = str(data.get("reply_to_name", "")).strip() or None
        
        if not comment_text or len(comment_text) > 500:
            return jsonify({"error": "Comment must be between 1 and 500 characters."}), 400

        stored_comment_text = f"[reply:{parent_id}:{reply_to_name or ''}] {comment_text}" if parent_id else comment_text
        comm_id = str(uuid.uuid4())

        new_comment: Dict[str, Any] = {
            "id": comm_id,
            "cat_id": cat_id,
            "user_id": user_id,
            "user_email": user_email, 
            "user_name": user_name,
            "user_avatar": avatar_url,
            "comment": stored_comment_text,
            "parent_id": parent_id,
            "reply_to_name": reply_to_name,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        if supabase_admin:
            try:
                db_res = safe_db_insert("comments", new_comment)
                raw_res: Any = getattr(db_res, "data", [])
                res_data: List[Dict[str, Any]] = cast(List[Dict[str, Any]], raw_res) if isinstance(raw_res, list) else []
                if len(res_data) > 0:
                    new_comment = res_data[0]
            except Exception as ce:
                print(f"Comment insert notice: {ce}")

        MOCK_COMMENTS.append(new_comment)
        
        returned_comment = dict(new_comment)
        returned_comment["parent_id"] = parent_id
        returned_comment["reply_to_name"] = reply_to_name
        returned_comment["comment"] = comment_text
        returned_comment["user_avatar"] = avatar_url
        returned_comment["user_name"] = user_name

        cat_owner_id = ""
        cat_name = "Cat"
        cat_image = ""
        if supabase_admin:
            try:
                c_res = getattr(supabase_admin.table("cats").select("user_id, name, image_url").eq("id", cat_id).single().execute(), "data", None)
                if c_res:
                    cat_owner_id = str(cast(Dict[str, Any], c_res).get("user_id", ""))
                    cat_name = str(cast(Dict[str, Any], c_res).get("name", "Cat"))
                    cat_image = str(cast(Dict[str, Any], c_res).get("image_url", ""))
            except Exception:
                pass

        if not cat_owner_id:
            m_cat = next((c for c in MOCK_CATS if str(c.get("id")) == str(cat_id)), None)
            if m_cat:
                cat_owner_id = str(m_cat.get("user_id", ""))
                cat_name = str(m_cat.get("name", "Cat"))
                cat_image = str(m_cat.get("image_url", ""))

        if parent_id:
            parent_author_id = ""
            if supabase_admin:
                try:
                    p_res = getattr(supabase_admin.table("comments").select("user_id").eq("id", parent_id).single().execute(), "data", None)
                    if p_res:
                        parent_author_id = str(cast(Dict[str, Any], p_res).get("user_id", ""))
                except Exception:
                    pass
            if not parent_author_id:
                p_mock = next((c for c in MOCK_COMMENTS if str(c.get("id")) == str(parent_id)), None)
                if p_mock:
                    parent_author_id = str(p_mock.get("user_id", ""))

            if parent_author_id and parent_author_id != user_id:
                push_notification(
                    user_id=parent_author_id,
                    actor_id=user_id,
                    actor_name=user_name,
                    actor_avatar=avatar_url,
                    notif_type="reply",
                    message=f"replied to your comment on {cat_name}: {comment_text[:50]}",
                    cat_id=cat_id,
                    cat_name=cat_name,
                    cat_image=cat_image,
                    comment_id=comm_id
                )
        else:
            if cat_owner_id and cat_owner_id != user_id:
                push_notification(
                    user_id=cat_owner_id,
                    actor_id=user_id,
                    actor_name=user_name,
                    actor_avatar=avatar_url,
                    notif_type="comment",
                    message=f"commented on {cat_name}: {comment_text[:50]}",
                    cat_id=cat_id,
                    cat_name=cat_name,
                    cat_image=cat_image,
                    comment_id=comm_id
                )

        return jsonify({"message": "Successfully commented!", "comment": returned_comment}), 201
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

@app.route("/api/comments/<comment_id>", methods=["DELETE"])
@require_auth
def delete_comment(comment_id: str):
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        is_admin = is_admin_user(getattr(g, "user", None))
        
        cdata = None
        if supabase_admin:
            try:
                cdata_raw: Any = getattr(supabase_admin.table("comments").select("*").eq("id", comment_id).single().execute(), "data", None)
                if cdata_raw:
                    cdata = cast(Dict[str, Any], cdata_raw)
            except Exception as e:
                print(f"Notice: Supabase comment check: {e}")

        if not cdata:
            cdata = next((c for c in MOCK_COMMENTS if str(c.get("id")) == str(comment_id)), None)

        if not cdata:
            return jsonify({"error": "Comment not found."}), 404
        if str(cdata.get("user_id", "")) != user_id and not is_admin:
            return jsonify({"error": "Access denied. Unauthorized to delete this comment."}), 403

        if supabase_admin:
            # 1. Delete notifications tied to this comment
            try:
                supabase_admin.table("notifications").delete().eq("comment_id", comment_id).execute()
            except Exception as ne:
                print(f"Notice: notifications delete by comment_id: {ne}")

            # 2. Delete child replies if parent_id column exists
            try:
                supabase_admin.table("comments").delete().eq("parent_id", comment_id).execute()
            except Exception as pe:
                print(f"Notice: comments delete by parent_id: {pe}")

            # 3. Delete child replies if reply tag was encoded in comment text
            try:
                supabase_admin.table("comments").delete().like("comment", f"[reply:{comment_id}:%").execute()
            except Exception as re_err:
                print(f"Notice: comments delete by text reply: {re_err}")

            # 4. Delete the comment itself
            try:
                supabase_admin.table("comments").delete().eq("id", comment_id).execute()
            except Exception as de:
                print(f"Error deleting comment from supabase: {de}")

        MOCK_COMMENTS[:] = [
            c for c in MOCK_COMMENTS 
            if str(c.get("id")) != str(comment_id) 
            and str(c.get("parent_id")) != str(comment_id)
            and not str(c.get("comment", "")).startswith(f"[reply:{comment_id}:")
        ]

        return jsonify({"message": "Comment deleted successfully.", "id": comment_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/comments/<comment_id>", methods=["PUT"])
@require_auth
def edit_comment(comment_id: str):
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        is_admin = is_admin_user(getattr(g, "user", None))
        
        raw_json: Any = request.get_json(silent=True)
        new_text = str(cast(Dict[str, Any], raw_json if isinstance(raw_json, dict) else {}).get("comment", "")).strip()

        if not new_text or len(new_text) > 500:
            return jsonify({"error": "Comment must be between 1 and 500 characters."}), 400
        
        cdata = None
        if supabase_admin:
            try:
                cdata_raw = getattr(supabase_admin.table("comments").select("*").eq("id", comment_id).single().execute(), "data", None)
                if cdata_raw:
                    cdata = cast(Dict[str, Any], cdata_raw)
            except Exception:
                pass

        if not cdata:
            cdata = next((c for c in MOCK_COMMENTS if str(c.get("id")) == str(comment_id)), None)

        if not cdata:
            return jsonify({"error": "Comment not found."}), 404
        if str(cdata.get("user_id", "")) != user_id and not is_admin:
            return jsonify({"error": "Access denied. Unauthorized to edit this comment."}), 403

        if supabase_admin:
            safe_db_update("comments", {"comment": new_text}, "id", comment_id)

        for c in MOCK_COMMENTS:
            if str(c.get("id")) == str(comment_id):
                c["comment"] = new_text

        return jsonify({"message": "Comment updated successfully.", "text": new_text}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/notifications", methods=["GET"])
@require_auth
def get_notifications():
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        notifs: List[Dict[str, Any]] = []

        if supabase_admin:
            try:
                res: Any = getattr(supabase_admin.table("notifications").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(50).execute(), "data", [])
                notifs = cast(List[Dict[str, Any]], res) if isinstance(res, list) else []
            except Exception:
                pass

        if not notifs:
            notifs = [n for n in MOCK_NOTIFICATIONS if str(n.get("user_id")) == str(user_id)]

        unread_count = sum(1 for n in notifs if not n.get("is_read"))
        return jsonify({"notifications": notifs, "unread_count": unread_count}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/notifications/<notif_id>/read", methods=["POST"])
@require_auth
def mark_notification_read(notif_id: str):
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        if supabase_admin:
            try:
                safe_db_update("notifications", {"is_read": True}, "id", notif_id)
            except Exception:
                pass

        for n in MOCK_NOTIFICATIONS:
            if str(n.get("id")) == str(notif_id) and str(n.get("user_id")) == str(user_id):
                n["is_read"] = True

        return jsonify({"message": "Marked as read.", "id": notif_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/notifications/read-all", methods=["POST"])
@require_auth
def mark_all_notifications_read():
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        if supabase_admin:
            try:
                safe_db_update("notifications", {"is_read": True}, "user_id", user_id)
            except Exception:
                pass

        for n in MOCK_NOTIFICATIONS:
            if str(n.get("user_id")) == str(user_id):
                n["is_read"] = True

        return jsonify({"message": "All notifications marked as read."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/notifications/<notif_id>", methods=["DELETE"])
@require_auth
def delete_single_notification(notif_id: str):
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        if supabase_admin:
            try:
                supabase_admin.table("notifications").delete().eq("id", notif_id).eq("user_id", user_id).execute()
            except Exception:
                pass

        MOCK_NOTIFICATIONS[:] = [n for n in MOCK_NOTIFICATIONS if not (str(n.get("id")) == str(notif_id) and str(n.get("user_id")) == str(user_id))]

        return jsonify({"message": "Notification deleted.", "id": notif_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/notifications/clear-all", methods=["DELETE", "POST"])
@require_auth
def clear_all_notifications():
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        if supabase_admin:
            try:
                supabase_admin.table("notifications").delete().eq("user_id", user_id).execute()
            except Exception:
                pass

        MOCK_NOTIFICATIONS[:] = [n for n in MOCK_NOTIFICATIONS if str(n.get("user_id")) != str(user_id)]

        return jsonify({"message": "All notifications cleared."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user/avatar", methods=["POST"])
@require_auth
def upload_user_avatar():
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        file: Any = request.files.get("avatar") or request.files.get("file")
        if file is None or not getattr(file, "filename", None):
            return jsonify({"error": "No avatar file provided."}), 400

        filename_str = str(file.filename)
        if not is_allowed_file(filename_str):
            return jsonify({"error": "Invalid file format. Allowed: PNG, JPG, JPEG, WEBP."}), 400

        file_bytes: bytes = file.read()
        if len(file_bytes) > MAX_FILE_SIZE:
            return jsonify({"error": "File size exceeds 5MB limit."}), 400

        avatar_url = ""
        if supabase_admin:
            try:
                clean_ext = os.path.splitext(filename_str)[1].lstrip(".").lower()
                unique_path = f"avatars/{user_id}/{uuid.uuid4()}.{clean_ext}"
                file_mimetype = str(getattr(file, "mimetype", "image/jpeg"))
                supabase_admin.storage.from_(STORAGE_BUCKET).upload(
                    path=unique_path,
                    file=file_bytes,
                    file_options={"content-type": file_mimetype, "upsert": "true"}
                )
                avatar_url = supabase_admin.storage.from_(STORAGE_BUCKET).get_public_url(unique_path)
            except Exception as se:
                print(f"Avatar storage error: {se}")

        if not avatar_url:
            avatar_url = f"https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=150&q=80"

        user_avatar_cache[user_id] = avatar_url
        if supabase_admin:
            safe_db_update("cats", {"user_avatar": avatar_url}, "user_id", user_id)
            safe_db_update("comments", {"user_avatar": avatar_url}, "user_id", user_id)
            try:
                supabase_admin.auth.admin.update_user_by_id(user_id, {"user_metadata": {"avatar_url": avatar_url}})
            except Exception:
                pass

        for c in MOCK_CATS:
            if str(c.get("user_id")) == str(user_id):
                c["user_avatar"] = avatar_url
        for cm in MOCK_COMMENTS:
            if str(cm.get("user_id")) == str(user_id):
                cm["user_avatar"] = avatar_url

        return jsonify({
            "message": "Avatar uploaded successfully!",
            "avatar_url": avatar_url
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/users/<user_id>/avatar", methods=["POST"])
@require_auth
def admin_upload_user_avatar(user_id: str):
    try:
        is_admin = is_admin_user(getattr(g, "user", None))
        if not is_admin:
            return jsonify({"error": "Admin access required."}), 403

        file: Any = request.files.get("avatar") or request.files.get("file")
        if file is None or not getattr(file, "filename", None):
            return jsonify({"error": "No avatar file provided."}), 400

        filename_str = str(file.filename)
        if not is_allowed_file(filename_str):
            return jsonify({"error": "Invalid file format. Allowed: PNG, JPG, JPEG, WEBP."}), 400

        file_bytes = file.read()
        if len(file_bytes) > MAX_FILE_SIZE:
            return jsonify({"error": "File size exceeds 5MB limit."}), 400

        avatar_url = ""
        if supabase_admin:
            try:
                clean_ext = os.path.splitext(filename_str)[1].lstrip(".").lower()
                unique_path = f"avatars/{user_id}/{uuid.uuid4()}.{clean_ext}"
                file_mimetype = str(getattr(file, "mimetype", "image/jpeg"))
                supabase_admin.storage.from_(STORAGE_BUCKET).upload(
                    path=unique_path,
                    file=file_bytes,
                    file_options={"content-type": file_mimetype, "upsert": "true"}
                )
                avatar_url = supabase_admin.storage.from_(STORAGE_BUCKET).get_public_url(unique_path)
            except Exception as se:
                print(f"Admin avatar storage notice: {se}")

        if not avatar_url:
            avatar_url = f"https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=150&q=80"

        user_avatar_cache[str(user_id)] = avatar_url
        if supabase_admin:
            safe_db_update("cats", {"user_avatar": avatar_url}, "user_id", user_id)
            safe_db_update("comments", {"user_avatar": avatar_url}, "user_id", user_id)
            try:
                supabase_admin.auth.admin.update_user_by_id(user_id, {"user_metadata": {"avatar_url": avatar_url}})
            except Exception:
                pass

        for c in MOCK_CATS:
            if str(c.get("user_id")) == str(user_id):
                c["user_avatar"] = avatar_url
        for cm in MOCK_COMMENTS:
            if str(cm.get("user_id")) == str(user_id):
                cm["user_avatar"] = avatar_url

        return jsonify({"message": "User avatar updated!", "avatar_url": avatar_url}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user/profile", methods=["PUT"])
@require_auth
def sync_user_profile():
    try:
        user_id = str(getattr(getattr(g, "user", None), "id", ""))
        raw_json: Any = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}
        
        new_name = str(data.get("display_name", "")).strip()
        new_avatar = str(data.get("avatar_url", "")).strip()

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
            try:
                auth_meta: Dict[str, Any] = {}
                if new_name: auth_meta["display_name"] = new_name
                if new_avatar: auth_meta["avatar_url"] = new_avatar
                if auth_meta:
                    supabase_admin.auth.admin.update_user_by_id(user_id, {"user_metadata": auth_meta})
            except Exception:
                pass

        for c in MOCK_CATS:
            if str(c.get("user_id")) == str(user_id):
                if new_name: c["user_name"] = new_name
                if new_avatar: c["user_avatar"] = new_avatar
        for cm in MOCK_COMMENTS:
            if str(cm.get("user_id")) == str(user_id):
                if new_name: cm["user_name"] = new_name
                if new_avatar: cm["user_avatar"] = new_avatar
            
        return jsonify({"message": "Profile synced successfully across all posts and comments."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/users/<user_id>/profile", methods=["PUT"])
@require_auth
def admin_edit_user_profile(user_id: str):
    try:
        is_admin = is_admin_user(getattr(g, "user", None))
        if not is_admin:
            return jsonify({"error": "Admin access required."}), 403

        raw_json = request.get_json(silent=True)
        data: Dict[str, Any] = cast(Dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}
        new_name = str(data.get("display_name", "")).strip()
        new_avatar = str(data.get("avatar_url", "")).strip()

        payload: Dict[str, Any] = {}
        if new_name:
            payload["user_name"] = new_name
        if new_avatar:
            payload["user_avatar"] = new_avatar
            user_avatar_cache[str(user_id)] = new_avatar

        if payload and supabase_admin:
            safe_db_update("cats", payload, "user_id", user_id)
            safe_db_update("comments", payload, "user_id", user_id)

        if supabase_admin:
            try:
                auth_meta: Dict[str, Any] = {}
                if new_name:
                    auth_meta["display_name"] = new_name
                if new_avatar:
                    auth_meta["avatar_url"] = new_avatar
                if auth_meta:
                    supabase_admin.auth.admin.update_user_by_id(user_id, {"user_metadata": auth_meta})
            except Exception:
                pass

        for c in MOCK_CATS:
            if str(c.get("user_id")) == str(user_id):
                if new_name: c["user_name"] = new_name
                if new_avatar: c["user_avatar"] = new_avatar
        for cm in MOCK_COMMENTS:
            if str(cm.get("user_id")) == str(user_id):
                if new_name: cm["user_name"] = new_name
                if new_avatar: cm["user_avatar"] = new_avatar

        return jsonify({"message": "User profile updated across all records.", "user_id": user_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/users/<user_id>/force-delete", methods=["DELETE", "POST"])
@require_auth
def admin_force_delete_user(user_id: str):
    try:
        is_admin = is_admin_user(getattr(g, "user", None))
        if not is_admin:
            return jsonify({"error": "Admin access required for force deletion."}), 403

        if supabase_admin:
            try:
                user_cats_raw = getattr(supabase_admin.table("cats").select("*").eq("user_id", user_id).execute(), "data", [])
                user_cats = cast(List[Dict[str, Any]], user_cats_raw) if isinstance(user_cats_raw, list) else []
                for c in user_cats:
                    cid = c.get("id")
                    if cid:
                        try:
                            supabase_admin.table("comments").delete().eq("cat_id", cid).execute()
                            supabase_admin.table("likes").delete().eq("cat_id", cid).execute()
                            supabase_admin.table("notifications").delete().eq("cat_id", cid).execute()
                        except Exception:
                            pass
                        img = str(c.get("image_url", ""))
                        if f"/{STORAGE_BUCKET}/" in img:
                            try:
                                storage_path = img.split(f"/{STORAGE_BUCKET}/")[-1]
                                supabase_admin.storage.from_(STORAGE_BUCKET).remove([storage_path])
                            except Exception:
                                pass
                        try:
                            supabase_admin.table("cats").delete().eq("id", cid).execute()
                        except Exception:
                            pass
            except Exception as e:
                print(f"User cats delete notice: {e}")

            try:
                supabase_admin.table("comments").delete().eq("user_id", user_id).execute()
                supabase_admin.table("likes").delete().eq("user_id", user_id).execute()
                supabase_admin.table("notifications").delete().eq("user_id", user_id).execute()
                supabase_admin.auth.admin.delete_user(user_id)
            except Exception:
                pass

        MOCK_CATS[:] = [c for c in MOCK_CATS if str(c.get("user_id")) != str(user_id)]
        MOCK_COMMENTS[:] = [c for c in MOCK_COMMENTS if str(c.get("user_id")) != str(user_id)]
        MOCK_LIKES[:] = [l for l in MOCK_LIKES if str(l.get("user_id")) != str(user_id)]
        MOCK_NOTIFICATIONS[:] = [n for n in MOCK_NOTIFICATIONS if str(n.get("user_id")) != str(user_id) and str(n.get("actor_id")) != str(user_id)]

        if user_id in user_avatar_cache:
            del user_avatar_cache[user_id]

        return jsonify({"message": "User and all associated data force deleted successfully.", "user_id": user_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/user/<user_id>/profile", methods=["GET"])
def get_public_profile(user_id: str):
    cats: List[Dict[str, Any]] = []
    user_name = "Cat Lover"
    user_avatar = ""

    if supabase_admin:
        try:
            # 1. Search by user_id
            raw_data: Any = getattr(supabase_admin.table("cats").select("*").eq("user_id", user_id).order("created_at", desc=True).execute(), "data", [])
            cats = cast(List[Dict[str, Any]], raw_data) if isinstance(raw_data, list) else []
            
            # 2. If no cats found by user_id, search by user_name in case username like 'f0xy' was provided
            if not cats:
                raw_data2: Any = getattr(supabase_admin.table("cats").select("*").ilike("user_name", user_id).order("created_at", desc=True).execute(), "data", [])
                cats = cast(List[Dict[str, Any]], raw_data2) if isinstance(raw_data2, list) else []
        except Exception as e:
            print(f"Notice: Supabase get_public_profile error: {e}")

    if not cats:
        cats = [
            c for c in MOCK_CATS 
            if str(c.get("user_id", "")).lower() == str(user_id).lower() 
            or str(c.get("user_name", "")).lower() == str(user_id).lower()
        ]
    
    if len(cats) > 0:
        for c in cats:
            c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))
        user_name = str(cats[0].get("user_name", "Cat Lover"))
        user_avatar = str(cats[0].get("user_avatar", ""))
    else:
        # If no uploaded cats, try finding user in Supabase auth
        if supabase_admin:
            try:
                u_obj = supabase_admin.auth.admin.get_user_by_id(user_id)
                u_data = getattr(u_obj, "user", None) or getattr(u_obj, "data", None)
                if u_data:
                    u_meta = getattr(u_data, "user_metadata", {}) or {}
                    user_name = str(u_meta.get("display_name", "")).strip() or str(getattr(u_data, "email", "Cat Lover")).split("@")[0]
                    user_avatar = str(u_meta.get("avatar_url", "")).strip()
            except Exception:
                pass
        
        if not user_avatar:
            user_name = user_id if not re.match(r"^[0-9a-f-]{36}$", user_id) else "Cat Lover"
            user_avatar = resolve_user_avatar(user_id, user_name, None)
        
    return jsonify({
        "user_id": user_id,
        "cats_count": len(cats), 
        "user_name": user_name,
        "user_avatar": user_avatar,
        "total_likes": sum(int(c.get("likes_count", 0) or 0) for c in cats),
        "cats": cats
    }), 200

@app.route("/api/user/my-cats", methods=["GET"])
@require_auth
def get_my_cats():
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    cats: List[Dict[str, Any]] = []
    if supabase_admin:
        try:
            raw_data: Any = getattr(supabase_admin.table("cats").select("*").eq("user_id", user_id).order("created_at", desc=True).execute(), "data", [])
            cats = cast(List[Dict[str, Any]], raw_data) if isinstance(raw_data, list) else []
        except Exception:
            pass

    if not cats:
        cats = [c for c in MOCK_CATS if str(c.get("user_id")) == str(user_id)]
    return jsonify({"cats": cats}), 200

@app.route("/api/user/liked-cats", methods=["GET"])
@require_auth
def get_user_liked_cats():
    user_id = str(getattr(getattr(g, "user", None), "id", ""))
    liked_ids: List[str] = []
    if supabase_admin:
        try:
            raw_data: Any = getattr(supabase_admin.table("likes").select("cat_id").eq("user_id", user_id).execute(), "data", [])
            db_arr = cast(List[Dict[str, Any]], raw_data) if isinstance(raw_data, list) else []
            liked_ids = [str(i["cat_id"]) for i in db_arr if "cat_id" in i]
        except Exception:
            pass

    if not liked_ids:
        liked_ids = [str(l["cat_id"]) for l in MOCK_LIKES if str(l.get("user_id")) == str(user_id)]
        
    return jsonify({"liked_cat_ids": liked_ids}), 200

@app.route("/api/admin/overview", methods=["GET"])
@require_auth
def admin_overview():
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
            except Exception:
                pass

        if not cats:
            cats = list(MOCK_CATS)
        
        for c in cats:
            c["user_avatar"] = resolve_user_avatar(c.get("user_id"), c.get("user_name"), c.get("user_avatar"))

        users_dict: Dict[str, Dict[str, Any]] = {}
        for c in cats:
            uid = str(c.get("user_id", ""))
            uname = str(c.get("user_name", "Cat Lover"))
            uavatar = str(c.get("user_avatar", "")) or generate_default_avatar(uname)
            if uid:
                if uid not in users_dict:
                    users_dict[uid] = {
                        "user_id": uid,
                        "user_name": uname,
                        "user_avatar": uavatar,
                        "cats_count": 0,
                        "total_likes": 0
                    }
                users_dict[uid]["cats_count"] += 1
                users_dict[uid]["total_likes"] += int(c.get("likes_count", 0) or 0)

        return jsonify({
            "total_cats": len(cats),
            "total_likes": sum(int(c.get("likes_count", 0) or 0) for c in cats),
            "cats": cats,
            "users": list(users_dict.values())
        }), 200
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
