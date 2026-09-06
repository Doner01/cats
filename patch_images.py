import re

with open("app.py", "r") as f:
    content = f.read()

# Add generate_cat_derivatives function
new_func = """
def generate_cat_derivatives(file_bytes: bytes) -> dict:
    '''Generates responsive derivatives for cat images. Returns a dict of size_name -> (bytes, ext, content_type, width, height).'''
    with Image.open(BytesIO(file_bytes)) as img:
        is_gif = (img.format or "").upper() == "GIF" and getattr(img, "is_animated", False)
        if is_gif:
            return {"original": (file_bytes, "gif", "image/gif", img.width, img.height)}

        img = ImageOps.exif_transpose(img)
        if img.mode not in {"RGB", "RGBA"}:
            img = img.convert("RGBA" if "transparency" in img.info else "RGB")

        derivatives = {}
        targets = {
            "thumb": 480,
            "feed": 800,
            "modal": 1600,
            "original": 2048
        }
        
        orig_width, orig_height = img.size
        
        for name, max_side in targets.items():
            # don't upscale
            if max(orig_width, orig_height) <= max_side:
                resized = img
            else:
                resized = img.copy()
                resized.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
                
            out = BytesIO()
            resized.save(out, format="WEBP", quality=86, method=4)
            derivatives[name] = (out.getvalue(), "webp", "image/webp", resized.width, resized.height)
            
        return derivatives
"""

if "def generate_cat_derivatives" not in content:
    content = content.replace("def optimize_image_file", new_func + "\ndef optimize_image_file")

# Update upload_cat to use derivatives
upload_cat_orig = """        optimized_bytes, clean_ext, content_type = optimize_image_file(file_bytes, avatar=False)
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
            "image_url": public_url,"""

upload_cat_new = """        derivatives = generate_cat_derivatives(file_bytes)
        base_uuid = str(uuid.uuid4())
        
        urls = {}
        width, height = 0, 0
        
        for size_name, (d_bytes, clean_ext, content_type, w, h) in derivatives.items():
            suffix = f"-{size_name}" if size_name != "original" else ""
            unique_path = f"{user_id}/{base_uuid}{suffix}.{clean_ext}"
            p_url = upload_file_to_storage(d_bytes, unique_path, content_type, STORAGE_BUCKET)
            if not p_url:
                return jsonify({"error": "Image storage is unavailable. Nothing was saved; please try again."}), 503
            urls[size_name] = p_url
            if size_name == "original":
                width, height = w, h

        cat_id = str(uuid.uuid4())
        cat_record: Dict[str, Any] = {
            "id": cat_id,
            "user_id": user_id,
            "user_name": user_name,
            "user_avatar": avatar_url,
            "name": cat_name,
            "bio": cat_bio,
            "image_url": urls.get("original"),
            "image_url_thumb": urls.get("thumb"),
            "image_url_feed": urls.get("feed"),
            "image_url_modal": urls.get("modal"),
            "image_width": width,
            "image_height": height,"""

content = content.replace(upload_cat_orig, upload_cat_new)

with open("app.py", "w") as f:
    f.write(content)

