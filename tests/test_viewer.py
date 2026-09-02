from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import hashlib
import re
import subprocess

import pytest
import app as mod

ROOT = Path(__file__).resolve().parents[1]


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.nodes = []
        self.ids = {}

    def handle_starttag(self, tag, attributes):
        node = {"tag": tag, "attrs": dict(attributes), "parent": self.stack[-1] if self.stack else None}
        self.nodes.append(node)
        if "id" in node["attrs"]:
            assert node["attrs"]["id"] not in self.ids
            self.ids[node["attrs"]["id"]] = node
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                self.stack = self.stack[:index]
                break


@pytest.fixture
def document(monkeypatch):
    monkeypatch.setattr(mod, "supabase_admin", None)
    monkeypatch.setattr(mod, "ENABLE_DEMO_DATA", True)
    page = mod.app.test_client().get("/")
    assert page.status_code == 200
    doc = Document()
    doc.feed(page.get_data(as_text=True))
    return doc


def test_arrows_are_outside_the_panel(document):
    panel = document.ids["cat-detail-panel"]
    previous = document.ids["modal-prev-cat"]
    following = document.ids["modal-next-cat"]
    assert previous["parent"] is panel["parent"] is following["parent"]
    assert "cat-viewer-stage" in panel["parent"]["attrs"]["class"]
    assert panel["parent"]["parent"] is document.ids["cat-detail-modal"]


def test_header_and_form_are_outside_the_scrolling_content(document):
    panel = document.ids["cat-detail-panel"]
    content = document.ids["cat-detail-scroll"]
    header = next(node for node in document.nodes if node["attrs"].get("class") == "cat-detail-header")
    footer = next(node for node in document.nodes if node["attrs"].get("class") == "cat-detail-footer")
    assert header["parent"] is panel is content["parent"] is footer["parent"]
    assert document.ids["modal-comment-input"]["parent"]["parent"] is footer
    assert document.ids["modal-cat-img"]["parent"]["parent"] is panel
    assert document.ids["modal-cat-bio-box"]["parent"] is content
    assert document.ids["modal-comments-items"]["parent"] is document.ids["modal-comments-list"]
    assert "overflow-y-auto" not in document.ids["modal-comments-list"]["attrs"].get("class", "")


def test_fixed_height_layout_is_scoped_to_cat_viewer():
    css = (ROOT / "static/css/style.css").read_text()
    assert "height: min(780px, calc(100dvh - 32px))" in css
    assert "grid-template-rows: minmax(0, 1fr) 44px" in css
    assert "grid-template-columns: minmax(0, 1.3fr) minmax(320px, 1fr)" in css
    assert ".cat-detail-panel {" in css
    assert "scrollbar-gutter: stable" in css
    assert ".cat-modal-nav-prev { grid-column: 1; }" in css


def test_only_the_comments_list_is_scrollable():
    css = (ROOT / "static/css/style.css").read_text()
    rules = {}
    for selector in (".cat-detail-scroll", ".cat-detail-comments", "#modal-comments-list"):
        match = re.search(re.escape(selector) + r"\s*\{([^}]+)\}", css)
        assert match is not None
        rules[selector] = match.group(1)
    assert "overflow: clip" in rules[".cat-detail-scroll"]
    assert "overflow-y: auto" not in rules[".cat-detail-scroll"]
    assert "display: flex" in rules[".cat-detail-comments"]
    assert "min-height: 0" in rules[".cat-detail-comments"]
    assert "overflow-y: auto" in rules["#modal-comments-list"]
    assert "overscroll-behavior: contain" in rules["#modal-comments-list"]


def test_rendered_assets_exist_and_use_content_fingerprints(document):
    for node in document.nodes:
        url = node["attrs"].get("src") or node["attrs"].get("href") or ""
        parsed = urlparse(url)
        if parsed.path.startswith("/static/"):
            path = ROOT / parsed.path.lstrip("/")
            assert path.is_file()
            assert parse_qs(parsed.query) == {"v": [hashlib.sha256(path.read_bytes()).hexdigest()[:12]]}


@pytest.mark.parametrize('path', ['/', '/profile', '/user/example', '/leaderboard', '/login', '/register'])
def test_rendered_inline_javascript_has_valid_syntax(monkeypatch, path):
    monkeypatch.setattr(mod, 'supabase_admin', None)
    monkeypatch.setattr(mod, 'ENABLE_DEMO_DATA', True)
    html = mod.app.test_client().get(path).get_data(as_text=True)
    for script in re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', html, re.S):
        result = subprocess.run(['node', '--check'], input=script, text=True, capture_output=True)
        assert result.returncode == 0, result.stderr


def test_guest_comment_prompt_and_owner_link_are_present(document):
    assert 'hidden' in document.ids['modal-comment-form']['attrs']['class']
    assert document.ids['modal-login-link']['attrs']['href'] == '/login'
    assert document.ids['modal-owner-link']['tag'] == 'a'
    assert document.ids['modal-save-btn']['attrs']['aria-pressed'] == 'false'


def test_caption_is_compact_and_template_indentation_is_not_rendered(document):
    css = (ROOT / 'static/css/style.css').read_text()
    caption = re.search(r'\.cat-caption\s*\{([^}]+)\}', css).group(1)
    text = re.search(r'#modal-cat-bio-text\s*\{([^}]+)\}', css).group(1)
    assert 'white-space: normal' in caption
    assert 'flex: 0 0 auto' in caption
    assert 'margin: 0' in caption
    assert '-webkit-line-clamp: 2' in text
    assert 'overflow: clip' in text
    assert document.ids['modal-bio-more']['attrs']['aria-controls'] == 'modal-cat-bio-text'
    assert document.ids['modal-bio-more']['attrs']['aria-expanded'] == 'false'
    assert 'cat-bio-modal' not in document.ids


def test_full_bio_expands_in_place_and_leaves_room_for_comments(document):
    css = (ROOT / 'static/css/style.css').read_text()
    box = re.search(r'#modal-cat-bio-box\.is-expanded\s*\{([^}]+)\}', css).group(1)
    text = re.search(r'#modal-cat-bio-box\.is-expanded #modal-cat-bio-text\s*\{([^}]+)\}', css).group(1)
    assert 'max-height: 50%' in box
    assert 'min-height: 0' in box
    assert 'line-clamp: unset' in text
    assert 'white-space: pre-line' in text
    assert 'overflow-y: auto' in text
    assert document.ids['modal-bio-more']['parent'] is document.ids['modal-cat-bio-box']
    assert document.ids['modal-cat-bio-box']['parent'] is document.ids['cat-detail-scroll']


def test_podium_photos_have_no_inner_padding(monkeypatch):
    monkeypatch.setattr(mod, 'supabase_admin', None)
    monkeypatch.setattr(mod, 'ENABLE_DEMO_DATA', True)
    page = mod.app.test_client().get('/leaderboard')
    doc = Document()
    doc.feed(page.get_data(as_text=True))
    photos = [node for node in doc.nodes if 'leaderboard-podium-photo' in node['attrs'].get('class', '')]
    assert len(photos) == 3
    for photo in photos:
        assert photo['tag'] == 'button'
        assert photo['attrs']['aria-label']
        assert 'pt-2' not in photo['attrs']['class'].split()
        assert any(node['tag'] == 'img' and node['parent'] is photo for node in doc.nodes)
    css = (ROOT / 'static/css/style.css').read_text()
    rule = re.search(r'\.leaderboard-podium-photo\s*\{([^}]+)\}', css).group(1)
    assert 'padding: 0' in rule
