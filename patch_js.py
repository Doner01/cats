with open("static/js/profile-cats.js", "r") as f:
    content = f.read()

orig = "const image = escapeHtml(safeImageUrl(cat.image_url, cat.name || 'Cat'));"
new = """
        const image = escapeHtml(safeImageUrl(cat.image_url_feed || cat.image_url, cat.name || 'Cat'));
        const imageThumb = escapeHtml(safeImageUrl(cat.image_url_thumb || cat.image_url, cat.name || 'Cat'));
        const srcset = cat.image_url_feed ? `srcset="${imageThumb} 480w, ${image} 800w" sizes="(max-width: 600px) 480px, 800px"` : '';
        const width = cat.image_width || 640;
        const height = cat.image_height || 480;
"""
content = content.replace(orig, new)

orig_img_tag = '`<img src="${image}" alt="${name}" loading="lazy" decoding="async" width="640" height="480">`'
new_img_tag = '`<img src="${image}" ${srcset} alt="${name}" loading="lazy" decoding="async" width="${width}" height="${height}" style="aspect-ratio: ${width} / ${height}">`'
content = content.replace(orig_img_tag, new_img_tag)

with open("static/js/profile-cats.js", "w") as f:
    f.write(content)

with open("static/js/main.js", "r") as f:
    main_js = f.read()

# Modal image setting
orig_modal = 'if (modalImgElem) setModalCatImage(cat.image_url || "", cat.name || "Cat");'
new_modal = 'if (modalImgElem) setModalCatImage(cat.image_url_modal || cat.image_url || "", cat.name || "Cat");'
main_js = main_js.replace(orig_modal, new_modal)

with open("static/js/main.js", "w") as f:
    f.write(main_js)

