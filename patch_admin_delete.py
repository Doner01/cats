import re

with open("app.py", "r") as f:
    content = f.read()

orig = """                user_cats = fetch_all_rows(lambda: admin.table("cats").select("id,image_url").eq("user_id", user_id).order("id"))
                profile_response = admin.table("profiles").select("avatar_url").eq("id", user_id).limit(1).execute()
                profile_rows = as_row_list(getattr(profile_response, "data", None))
                admin.auth.admin.delete_user(user_id)
                for cat in user_cats:
                    delete_file_from_storage(str(cat.get("image_url", "")), STORAGE_BUCKET, allowed_prefix=f"{user_id}/")
                    cache_delete(make_cache_key("cat", cat.get("id", "")))"""

new_ = """                user_cats = fetch_all_rows(lambda: admin.table("cats").select("id,image_url,image_url_thumb,image_url_feed,image_url_modal").eq("user_id", user_id).order("id"))
                profile_response = admin.table("profiles").select("avatar_url").eq("id", user_id).limit(1).execute()
                profile_rows = as_row_list(getattr(profile_response, "data", None))
                admin.auth.admin.delete_user(user_id)
                for cat in user_cats:
                    for key in ["image_url", "image_url_thumb", "image_url_feed", "image_url_modal"]:
                        url = str(cat.get(key) or "")
                        if url:
                            delete_file_from_storage(url, STORAGE_BUCKET, allowed_prefix=f"{user_id}/")
                    cache_delete(make_cache_key("cat", cat.get("id", "")))"""

content = content.replace(orig, new_)

with open("app.py", "w") as f:
    f.write(content)
