import re

with open("app.py", "r") as f:
    content = f.read()

old_overview = re.search(r'@app\.route\("/api/admin/overview", methods=\["GET"\]\).*?Failed to load admin overview\."\}\), 500', content, re.DOTALL)

new_overview = """@app.route("/api/admin/overview", methods=["GET"])
@require_auth
@limiter.limit("30 per minute", key_func=authenticated_user_rate_key)
def get_admin_overview() -> Any:
    try:
        if not is_admin_user(getattr(g, "user", None)):
            return jsonify({"error": "Admin access required."}), 403
        admin = supabase_admin
        if admin is None and not ENABLE_DEMO_DATA:
            return jsonify({"error": "Database service is unavailable."}), 503

        total_cats = 0
        total_likes = 0
        total_users = 0
        total_comments = 0

        if admin is not None:
            try:
                cat_count_res = admin.table("cats").select("id,likes_count", count="exact").execute()
                total_cats = int(getattr(cat_count_res, "count", 0) or 0)
                cats_data = as_row_list(getattr(cat_count_res, "data", None))
                total_likes = sum(int(c.get("likes_count", 0) or 0) for c in cats_data)

                user_count_res = admin.table("profiles").select("id", count="exact", head=True).execute()
                total_users = int(getattr(user_count_res, "count", 0) or 0)

                comment_count_res = admin.table("comments").select("id", count="exact", head=True).execute()
                total_comments = int(getattr(comment_count_res, "count", 0) or 0)
            except Exception as e:
                app.logger.warning("Admin overview count failed: %s", e)

        return jsonify({
            "total_cats": total_cats,
            "total_likes": total_likes,
            "total_users": total_users,
            "total_comments": total_comments
        }), 200
    except Exception:
        app.logger.exception("Failed to load admin overview")
        return jsonify({"error": "Failed to load admin overview."}), 500

@app.route("/api/admin/cats", methods=["GET"])
@require_auth
def admin_get_cats() -> Any:
    if not is_admin_user(getattr(g, "user", None)): return jsonify({"error": "Admin access required."}), 403
    if not supabase_admin: return jsonify({"cats": [], "total": 0, "page": 1, "limit": 50})
    
    page = max(1, int(request.args.get("page", 1)))
    limit = min(100, max(1, int(request.args.get("limit", 50))))
    search = request.args.get("search", "").strip()
    
    query = supabase_admin.table("cats").select("*", count="exact")
    if search: query = query.ilike("name", f"%{search}%")
        
    res = query.order("created_at", desc=True).range((page-1)*limit, page*limit - 1).execute()
    cats = as_row_list(getattr(res, "data", None))
    return jsonify({"cats": cats, "total": int(getattr(res, "count", 0) or 0), "page": page, "limit": limit})

@app.route("/api/admin/users", methods=["GET"])
@require_auth
def admin_get_users() -> Any:
    if not is_admin_user(getattr(g, "user", None)): return jsonify({"error": "Admin access required."}), 403
    if not supabase_admin: return jsonify({"users": [], "total": 0, "page": 1, "limit": 50})
    
    page = max(1, int(request.args.get("page", 1)))
    limit = min(100, max(1, int(request.args.get("limit", 50))))
    search = request.args.get("search", "").strip()
    
    query = supabase_admin.table("profiles").select("*", count="exact")
    if search: query = query.or_(f"display_name.ilike.%{search}%,email.ilike.%{search}%,phone.ilike.%{search}%")
        
    res = query.order("id").range((page-1)*limit, page*limit - 1).execute()
    profiles = as_row_list(getattr(res, "data", None))
    
    users = []
    for p in profiles:
        users.append({
            "user_id": str(p.get("id")),
            "user_name": str(p.get("display_name") or "Cat Lover"),
            "display_name": str(p.get("display_name") or "Cat Lover"),
            "user_avatar": str(p.get("avatar_url") or ""),
            "avatar_url": str(p.get("avatar_url") or ""),
            "email": str(p.get("email") or ""),
            "phone": str(p.get("phone") or ""),
            "phone_number": str(p.get("phone") or ""),
            "role": str(p.get("role") or "user"),
            "cats_count": 0,
            "total_likes": 0
        })
    return jsonify({"users": users, "total": int(getattr(res, "count", 0) or 0), "page": page, "limit": limit})

@app.route("/api/admin/comments", methods=["GET"])
@require_auth
def admin_get_comments() -> Any:
    if not is_admin_user(getattr(g, "user", None)): return jsonify({"error": "Admin access required."}), 403
    if not supabase_admin: return jsonify({"comments": [], "total": 0, "page": 1, "limit": 50})
    
    page = max(1, int(request.args.get("page", 1)))
    limit = min(100, max(1, int(request.args.get("limit", 50))))
    search = request.args.get("search", "").strip()
    
    query = supabase_admin.table("comments").select("*", count="exact")
    if search: query = query.ilike("comment", f"%{search}%")
        
    res = query.order("created_at", desc=True).range((page-1)*limit, page*limit - 1).execute()
    comments = as_row_list(getattr(res, "data", None))
    return jsonify({"comments": comments, "total": int(getattr(res, "count", 0) or 0), "page": page, "limit": limit})"""

if old_overview:
    content = content[:old_overview.start()] + new_overview + content[old_overview.end():]
    with open("app.py", "w") as f:
        f.write(content)
    print("Patched app.py")
else:
    print("Could not find overview endpoint")
