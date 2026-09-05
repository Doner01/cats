import unittest
import io
import os
from unittest.mock import patch
from PIL import Image

# Setup realistic environment variables for testing
os.environ["CAT_DETECTOR_ENABLED"] = "true"
os.environ["CAT_DETECTOR_CONFIDENCE"] = "0.50"
os.environ["CAT_DETECTOR_MODEL"] = "models/yolov8n.pt"

import app as app_module

class CatDetectorIntegrationTest(unittest.TestCase):
    def setUp(self):
        app_module.app.config['TESTING'] = True
        app_module.app.config['CAT_DETECTOR_ENABLED'] = True
        app_module.app.config['CAT_DETECTOR_CONFIDENCE'] = 0.50
        app_module.app.config['CAT_DETECTOR_MODEL'] = "models/yolov8n.pt"
        app_module.app.config['TRUSTED_HOSTS'] = ["localhost"]
        self.client = app_module.app.test_client()

        cat_img = Image.new('RGB', (100, 100), color='white')
        self.cat_bytes = io.BytesIO()
        cat_img.save(self.cat_bytes, format='JPEG')
        
        # Strip require_auth for test
        self.original_upload = app_module.app.view_functions['upload_cat']
        if hasattr(self.original_upload, "__wrapped__"):
            app_module.app.view_functions['upload_cat'] = self.original_upload.__wrapped__

    def tearDown(self):
        app_module.app.view_functions['upload_cat'] = self.original_upload

    def _post_image(self, img_bytes, filename="test.jpg"):
        data = {
            "name": "Test Cat",
            "file": (io.BytesIO(img_bytes), filename)
        }
        return self.client.post("/api/cats/upload", data=data, content_type="multipart/form-data")

    @patch('app.validate_image_file', return_value=(True, ""))
    @patch('app.optimize_image_file', return_value=(b"opt", "jpg", "image/jpeg"))
    @patch('app.upload_file_to_storage', return_value="https://storage/test.jpg")
    @patch('app.insert_cat_record_compat', return_value=(True, {"id": "test"}))
    @patch('app.get_canonical_user_identity', return_value=("user1", "User 1", "avatar"))
    @patch('app.supabase_admin', True)
    @patch('cat_detector.detect_cats')
    def test_upload_success_when_detector_accepts(self, mock_detect, mock_user, mock_insert, mock_upload, mock_opt, mock_val):
        mock_detect.return_value = True
        res = self._post_image(self.cat_bytes.getvalue())
        self.assertEqual(res.status_code, 201)
        mock_upload.assert_called_once()
        mock_detect.assert_called_once()

    @patch('app.validate_image_file', return_value=(True, ""))
    @patch('app.optimize_image_file')
    @patch('app.upload_file_to_storage')
    @patch('app.get_canonical_user_identity', return_value=("user1", "User 1", "avatar"))
    @patch('app.supabase_admin', True)
    @patch('cat_detector.detect_cats')
    def test_upload_fails_when_detector_rejects(self, mock_detect, mock_user, mock_upload, mock_opt, mock_val):
        mock_detect.return_value = False
        res = self._post_image(self.cat_bytes.getvalue())
        self.assertEqual(res.status_code, 400)
        self.assertIn("No cat detected", res.get_data(as_text=True))
        mock_upload.assert_not_called()
        mock_opt.assert_not_called()

    @patch('app.validate_image_file', return_value=(True, ""))
    @patch('app.upload_file_to_storage')
    @patch('app.get_canonical_user_identity', return_value=("user1", "User 1", "avatar"))
    @patch('app.supabase_admin', True)
    @patch('cat_detector.detect_cats')
    def test_upload_fails_when_detector_crashes(self, mock_detect, mock_user, mock_upload, mock_val):
        mock_detect.side_effect = RuntimeError("Cat detector is currently unavailable.")
        res = self._post_image(self.cat_bytes.getvalue())
        self.assertEqual(res.status_code, 503)
        self.assertIn("unavailable", res.get_data(as_text=True))
        mock_upload.assert_not_called()

    @patch('app.validate_image_file', return_value=(True, ""))
    @patch('app.optimize_image_file', return_value=(b"opt", "jpg", "image/jpeg"))
    @patch('app.upload_file_to_storage', return_value="https://storage/test.jpg")
    @patch('app.insert_cat_record_compat', return_value=(True, {"id": "test"}))
    @patch('app.get_canonical_user_identity', return_value=("user1", "User 1", "avatar"))
    @patch('app.supabase_admin', True)
    def test_upload_when_detector_disabled(self, mock_user, mock_insert, mock_upload, mock_opt, mock_val):
        app_module.app.config['CAT_DETECTOR_ENABLED'] = False
        res = self._post_image(self.cat_bytes.getvalue())
        self.assertEqual(res.status_code, 201)
        mock_upload.assert_called_once()
        app_module.app.config['CAT_DETECTOR_ENABLED'] = True

if __name__ == '__main__':
    unittest.main()
