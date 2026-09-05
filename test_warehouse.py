import requests
from io import BytesIO
from cat_detector import detect_cats
from flask import Flask
import logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.config["CAT_DETECTOR_ENABLED"] = True
app.config["CAT_DETECTOR_MODEL"] = "models/yolov8n.pt"
app.config["CAT_DETECTOR_CONFIDENCE"] = 0.50

# A public warehouse image
url = "https://images.pexels.com/photos/1797428/pexels-photo-1797428.jpeg?auto=compress&cs=tinysrgb&w=640"

headers = {'User-Agent': 'Mozilla/5.0'}
resp = requests.get(url, headers=headers)

with app.app_context():
    accepted = detect_cats(resp.content)
    print(f"warehouse -> {'ACCEPT' if accepted else 'REJECT'}")
