import re
with open("app.py", "r") as f:
    content = f.read()

orig_get_db = """def get_db_row(query: Any) -> Optional[Dict[str, Any]]:
    try:
        response = query.limit(1).execute()"""

new_get_db = """def get_db_row(query: Any) -> Optional[Dict[str, Any]]:
    start = time.perf_counter()
    try:
        response = query.limit(1).execute()"""

content = content.replace(orig_get_db, new_get_db)

orig_get_db_end = """        rows = as_row_list(getattr(response, "data", None))
        return rows[0] if rows else None
    except Exception as e:"""

new_get_db_end = """        rows = as_row_list(getattr(response, "data", None))
        g.supabase_time = getattr(g, "supabase_time", 0.0) + (time.perf_counter() - start)
        return rows[0] if rows else None
    except Exception as e:
        g.supabase_time = getattr(g, "supabase_time", 0.0) + (time.perf_counter() - start)"""

content = content.replace(orig_get_db_end, new_get_db_end)

# Also let's instrument R2 upload
orig_r2 = """def upload_file_to_storage(file_bytes: bytes, unique_path: str, content_type: str, bucket_name: str = STORAGE_BUCKET) -> str:
                                              
    if r2_client and R2_BUCKET_NAME and R2_PUBLIC_DOMAIN:
        try:"""

new_r2 = """def upload_file_to_storage(file_bytes: bytes, unique_path: str, content_type: str, bucket_name: str = STORAGE_BUCKET) -> str:
                                              
    if r2_client and R2_BUCKET_NAME and R2_PUBLIC_DOMAIN:
        start = time.perf_counter()
        try:"""

content = content.replace(orig_r2, new_r2)

orig_r2_end = """            return f"{R2_PUBLIC_DOMAIN}/{unique_path}"
        except Exception as r2_e:"""

new_r2_end = """            g.r2_time = getattr(g, "r2_time", 0.0) + (time.perf_counter() - start)
            return f"{R2_PUBLIC_DOMAIN}/{unique_path}"
        except Exception as r2_e:
            g.r2_time = getattr(g, "r2_time", 0.0) + (time.perf_counter() - start)"""

content = content.replace(orig_r2_end, new_r2_end)

with open("app.py", "w") as f:
    f.write(content)
