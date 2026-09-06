import os
import re

def update_file(path, orig, new):
    with open(path, "r") as f:
        content = f.read()
    if orig in content:
        content = content.replace(orig, new)
        with open(path, "w") as f:
            f.write(content)

# index.html
update_file("templates/index.html",
    '<img src="{{ top_cat.image_url }}" alt="{{ top_cat.name }}" fetchpriority="high" width="600" height="600" decoding="async">',
    '''<img src="{{ top_cat.image_url_feed or top_cat.image_url }}" 
             {% if top_cat.image_url_feed %}srcset="{{ top_cat.image_url_thumb or top_cat.image_url }} 480w, {{ top_cat.image_url_feed }} 800w" sizes="(max-width: 600px) 480px, 800px"{% endif %}
             alt="{{ top_cat.name }}" fetchpriority="high" width="{{ top_cat.image_width or 600 }}" height="{{ top_cat.image_height or 600 }}" decoding="async" style="aspect-ratio: {{ top_cat.image_width or 1 }} / {{ top_cat.image_height or 1 }}">''')

update_file("templates/index.html",
    '<img src="{{ cat.image_url }}" alt="{{ cat.name }}" loading="lazy" decoding="async" width="640" height="480">',
    '''<img src="{{ cat.image_url_feed or cat.image_url }}" 
             {% if cat.image_url_feed %}srcset="{{ cat.image_url_thumb or cat.image_url }} 480w, {{ cat.image_url_feed }} 800w" sizes="(max-width: 600px) 480px, 800px"{% endif %}
             alt="{{ cat.name }}" loading="lazy" decoding="async" width="{{ cat.image_width or 640 }}" height="{{ cat.image_height or 480 }}" style="aspect-ratio: {{ cat.image_width or 4 }} / {{ cat.image_height or 3 }}">''')

# leaderboard.html
for num, top in [(0, "0"), (1, "1"), (2, "2")]:
    orig = f'<img src="{{{{ leaderboard[{top}].image_url }}}}" alt="{{{{ leaderboard[{top}].name }}}}" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" loading="lazy" decoding="async">'
    new = f'''<img src="{{{{ leaderboard[{top}].image_url_feed or leaderboard[{top}].image_url }}}}" 
                   {{% if leaderboard[{top}].image_url_feed %}}srcset="{{{{ leaderboard[{top}].image_url_thumb or leaderboard[{top}].image_url }}}} 480w, {{{{ leaderboard[{top}].image_url_feed }}}} 800w" sizes="(max-width: 600px) 480px, 800px"{{% endif %}}
                   alt="{{{{ leaderboard[{top}].name }}}}" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" loading="lazy" decoding="async" width="{{{{ leaderboard[{top}].image_width or 640 }}}}" height="{{{{ leaderboard[{top}].image_height or 480 }}}}">'''
    update_file("templates/leaderboard.html", orig, new)

update_file("templates/leaderboard.html",
    '<img src="{{ cat.image_url }}" alt="{{ cat.name }}" class="w-10 h-10 rounded-xl object-cover border border-slate-200 bg-slate-900">',
    '<img src="{{ cat.image_url_thumb or cat.image_url }}" alt="{{ cat.name }}" class="w-10 h-10 rounded-xl object-cover border border-slate-200 bg-slate-900" loading="lazy" decoding="async">')

