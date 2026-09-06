import re

with open("app.py", "r") as f:
    content = f.read()

# Replace select("id,user_id,image_url") with select("id,user_id,image_url,image_url_thumb,image_url_feed,image_url_modal")
content = content.replace('select("id,user_id,image_url")', 'select("id,user_id,image_url,image_url_thumb,image_url_feed,image_url_modal")')

# Replace delete_file_from_storage block for delete_cat and admin_force_delete
delete_block_orig = """        img_url = str(cat_row.get("image_url", ""))
        supabase_admin.table("cats").delete().eq("id", cat_id).execute()                         

        try:
            delete_file_from_storage(img_url, STORAGE_BUCKET, allowed_prefix=f"{str(cat_row.get('user_id') or '')}/")
        except Exception:
            app.logger.warning("Cat row deleted but image cleanup failed for %s", cat_id)"""

delete_block_new = """        supabase_admin.table("cats").delete().eq("id", cat_id).execute()                         

        for key in ["image_url", "image_url_thumb", "image_url_feed", "image_url_modal"]:
            url = str(cat_row.get(key) or "")
            if url:
                try:
                    delete_file_from_storage(url, STORAGE_BUCKET, allowed_prefix=f"{str(cat_row.get('user_id') or '')}/")
                except Exception:
                    app.logger.warning(f"Cat row deleted but image cleanup failed for {key}: %s", cat_id)"""

content = content.replace(delete_block_orig, delete_block_new)

# Similarly for admin_force_delete_user
# find: img_url = str(c.get("image_url", "")) ... delete_file_from_storage(img_url
# wait, let's see how admin_force_delete_user is implemented.

with open("app.py", "w") as f:
    f.write(content)

