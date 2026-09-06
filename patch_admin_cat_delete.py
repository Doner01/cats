import re
with open("app.py", "r") as f:
    content = f.read()

orig = """        img_url = str(cat_row.get("image_url", ""))
        supabase_admin.table("cats").delete().eq("id", cat_id).execute()
        try:
            delete_file_from_storage(img_url, STORAGE_BUCKET, allowed_prefix=f"{str(cat_row.get('user_id') or '')}/")
        except Exception:
            app.logger.warning("Admin deleted cat %s but storage cleanup failed", cat_id)"""

new_ = """        supabase_admin.table("cats").delete().eq("id", cat_id).execute()
        for key in ["image_url", "image_url_thumb", "image_url_feed", "image_url_modal"]:
            url = str(cat_row.get(key) or "")
            if url:
                try:
                    delete_file_from_storage(url, STORAGE_BUCKET, allowed_prefix=f"{str(cat_row.get('user_id') or '')}/")
                except Exception:
                    app.logger.warning("Admin deleted cat %s but storage cleanup failed for %s", cat_id, key)"""
content = content.replace(orig, new_)
with open("app.py", "w") as f:
    f.write(content)
