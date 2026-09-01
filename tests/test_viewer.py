from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import re

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
    assert document.ids["modal-cat-img"]["parent"]["parent"] is content
    assert "overflow-y-auto" not in document.ids["modal-comments-list"]["attrs"]["class"]


def test_fixed_height_layout_is_scoped_to_cat_viewer():
    css = (ROOT / "static/css/style.css").read_text()
    assert "height: min(860px, calc(100dvh - 32px))" in css
    assert "grid-template-rows: minmax(0, 1fr) 48px" in css
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


def test_rendered_assets_exist_and_use_new_versions(document):
    changed = {"css/style.css": "v=5", "js/main.js": "v=5", "js/ui.js": "v=4", "css/tailwind.css": "v=4"}
    for node in document.nodes:
        url = node["attrs"].get("src") or node["attrs"].get("href") or ""
        parsed = urlparse(url)
        if parsed.path.startswith("/static/"):
            assert (ROOT / parsed.path.lstrip("/")).is_file()
            if parsed.path.removeprefix("/static/") in changed:
                assert parsed.query == changed[parsed.path.removeprefix("/static/")]
