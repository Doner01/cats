import re

with open("app.py", "r") as f:
    content = f.read()

# Add to before_request
orig_before = """@app.before_request
def assign_request_id() -> None:"""

new_before = """import time
@app.before_request
def assign_request_id() -> None:
    g.start_time = time.perf_counter()
    g.supabase_time = 0.0
    g.r2_time = 0.0"""

if "g.start_time =" not in content:
    content = content.replace(orig_before, new_before)

# Add to after_request
orig_after = """    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000\""""

new_after = """    if hasattr(g, 'start_time'):
        app_time = (time.perf_counter() - g.start_time) * 1000
        supa_time = getattr(g, 'supabase_time', 0.0) * 1000
        r2_time = getattr(g, 'r2_time', 0.0) * 1000
        parts = [f"app;dur={app_time:.1f}"]
        if supa_time > 0: parts.append(f"db;dur={supa_time:.1f}")
        if r2_time > 0: parts.append(f"r2;dur={r2_time:.1f}")
        response.headers["Server-Timing"] = ", ".join(parts)
        
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000\""""

if "Server-Timing" not in content:
    content = content.replace(orig_after, new_after)

# Now we need to inject timing into fetch_all_rows and get_db_row
orig_fetch = """def fetch_all_rows(query_factory: Callable[[], Any], *, max_rows: int = 10000) -> List[Dict[str, Any]]:"""
new_fetch = """def fetch_all_rows(query_factory: Callable[[], Any], *, max_rows: int = 10000) -> List[Dict[str, Any]]:
    start = time.perf_counter()
    try:"""

orig_fetch_end = """        return all_rows
    except Exception as e:"""
new_fetch_end = """        g.supabase_time = getattr(g, 'supabase_time', 0.0) + (time.perf_counter() - start)
        return all_rows
    except Exception as e:
        g.supabase_time = getattr(g, 'supabase_time', 0.0) + (time.perf_counter() - start)"""

if "start = time.perf_counter()" not in content:
    # Not trivial to just string replace because of indentation. Let's do it carefully.
    content = re.sub(r'def fetch_all_rows([^:]*):\s*all_rows = \[\]', r'def fetch_all_rows\1:\n    start = time.perf_counter()\n    all_rows = []', content)
    content = re.sub(r'return all_rows\n    except', r'g.supabase_time = getattr(g, "supabase_time", 0.0) + (time.perf_counter() - start)\n        return all_rows\n    except', content)
    content = re.sub(r'raise RuntimeError\("Database query failed"\)\n', r'g.supabase_time = getattr(g, "supabase_time", 0.0) + (time.perf_counter() - start)\n        raise RuntimeError("Database query failed")\n', content)

with open("app.py", "w") as f:
    f.write(content)
