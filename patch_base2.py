import re

with open("templates/base.html", "r") as f:
    content = f.read()

content = content.replace('<script\\n        src="', '<script defer\\n        src="')
content = content.replace('<script\\n    src="', '<script defer\\n    src="')
content = content.replace('<script\\n\\t\\tsrc="', '<script defer\\n\\t\\tsrc="')

# We can also just regex substitute <script \s* src=
content = re.sub(r'<script(\s+)src=', r'<script defer\1src=', content)

with open("templates/base.html", "w") as f:
    f.write(content)
