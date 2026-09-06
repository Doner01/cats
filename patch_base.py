import re

with open("templates/base.html", "r") as f:
    content = f.read()

# Add preconnects
orig_preconnect_target = '    <meta name="theme-color" content="#faf9f6">'
new_preconnect = '''    <meta name="theme-color" content="#faf9f6">
    {% if supabase_url %}<link rel="preconnect" href="{{ supabase_url }}" crossorigin>{% endif %}
    {% if r2_domain %}<link rel="preconnect" href="{{ r2_domain }}" crossorigin>{% endif %}'''
content = content.replace(orig_preconnect_target, new_preconnect)

# Add preload for css/style.css
orig_preload_target = '    <!-- Static CSS -->'
new_preload = '''    <!-- Static CSS -->
    <link rel="preload" href="{{ url_for('static', filename='css/style.css') }}?v={{ asset_fingerprint('css/style.css') }}" as="style">'''
content = content.replace(orig_preload_target, new_preload)

# Add defer to first party scripts. We need to be careful with script order.
# toast, auth, main, favorites, ui, account, comment-likes
# Since they are all injected just before </body>, defer is safe and won't break order if all have defer.
# However, `supabase.js` and `translations.js` are also loaded. 
# Let's replace <script src=".../js/..." ...> with <script defer src="..."> 

# Find scripts
scripts_to_defer = [
    'vendor/supabase.js',
    'js/translations.js',
    'js/toast.js',
    'js/auth.js',
    'js/main.js',
    'js/favorites.js',
    'js/ui.js',
    'js/account.js',
    'js/comment-likes.js'
]

for script in scripts_to_defer:
    content = re.sub(
        r'<script(\s*)src="([^"]*' + re.escape(script) + r'[^"]*)"([^>]*)></script>',
        r'<script defer\1src="\2"\3></script>',
        content
    )

with open("templates/base.html", "w") as f:
    f.write(content)
