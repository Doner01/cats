import unittest
from app import app
from bs4 import BeautifulSoup

class TestScriptOrder(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TRUSTED_HOSTS'] = ['localhost']
        self.client = self.app.test_client()

    def test_script_order_no_defer_on_critical_scripts(self):
        resp = self.client.get('/', environ_base={'HTTP_HOST': 'localhost'})
        html = resp.get_data(as_text=True)
        soup = BeautifulSoup(html, 'html.parser')
        
        scripts = soup.find_all('script')
        
        supabase_js_idx = -1
        auth_js_idx = -1
        inline_init_idx = -1
        
        for i, script in enumerate(scripts):
            src = script.get('src', '')
            
            if 'vendor/supabase.js' in src:
                supabase_js_idx = i
                self.assertFalse(script.has_attr('defer'), "supabase.js should NOT have defer to preserve order")
            elif 'js/auth.js' in src:
                auth_js_idx = i
                self.assertFalse(script.has_attr('defer'), "auth.js should NOT have defer to preserve order")
            elif not src and script.string and 'let supabaseClient' in script.string:
                inline_init_idx = i
                
        if supabase_js_idx == -1:
            print("HTML RETRIEVED:", html[:200])

        self.assertTrue(supabase_js_idx != -1, "supabase.js must be present")
        self.assertTrue(inline_init_idx != -1, "inline initialization must be present")
        self.assertTrue(auth_js_idx != -1, "auth.js must be present")
        
        self.assertTrue(supabase_js_idx < inline_init_idx, "supabase.js must appear before inline initialization")
        self.assertTrue(inline_init_idx < auth_js_idx, "inline initialization must appear before auth.js")

if __name__ == '__main__':
    unittest.main()
