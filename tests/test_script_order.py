import unittest
from app import app
from html.parser import HTMLParser

class ScriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.in_script = False
        self.current_attrs = {}
        self.current_data = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.in_script = True
            self.current_attrs = dict(attrs)
            self.current_data = []

    def handle_endtag(self, tag):
        if tag == 'script':
            self.in_script = False
            self.scripts.append({
                'attrs': self.current_attrs,
                'data': ''.join(self.current_data)
            })

    def handle_data(self, data):
        if self.in_script:
            self.current_data.append(data)

class TestScriptOrder(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TRUSTED_HOSTS'] = ['localhost']
        self.client = self.app.test_client()

    def test_script_order_no_defer_on_critical_scripts(self):
        resp = self.client.get('/', environ_base={'HTTP_HOST': 'localhost'})
        html = resp.get_data(as_text=True)
        
        parser = ScriptParser()
        parser.feed(html)
        
        supabase_js_idx = -1
        auth_js_idx = -1
        inline_init_idx = -1
        
        for i, script in enumerate(parser.scripts):
            src = script['attrs'].get('src', '')
            has_defer = 'defer' in script['attrs']
            data = script['data']
            
            if 'vendor/supabase.js' in src:
                supabase_js_idx = i
                self.assertFalse(has_defer, "supabase.js should NOT have defer to preserve order")
            elif 'js/auth.js' in src:
                auth_js_idx = i
                self.assertFalse(has_defer, "auth.js should NOT have defer to preserve order")
            elif not src and 'let supabaseClient' in data:
                inline_init_idx = i
                
        self.assertTrue(supabase_js_idx != -1, "supabase.js must be present")
        self.assertTrue(inline_init_idx != -1, "inline initialization must be present")
        self.assertTrue(auth_js_idx != -1, "auth.js must be present")
        
        self.assertTrue(supabase_js_idx < inline_init_idx, "supabase.js must appear before inline initialization")
        self.assertTrue(inline_init_idx < auth_js_idx, "inline initialization must appear before auth.js")

if __name__ == '__main__':
    unittest.main()
