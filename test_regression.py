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

images = {
    "warehouse": "https://images.pexels.com/photos/1797428/pexels-photo-1797428.jpeg?auto=compress&cs=tinysrgb&w=640",
    "landscape": "https://images.unsplash.com/photo-1472214103451-9374bd1c798e?ixlib=rb-4.0.3&auto=format&fit=crop&w=640&q=80",
    "car": "https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?ixlib=rb-4.0.3&auto=format&fit=crop&w=640&q=80",
    "dog": "https://images.unsplash.com/photo-1517849845537-4d257902454a?ixlib=rb-4.0.3&auto=format&fit=crop&w=640&q=80",
    "random_objects": "https://images.unsplash.com/photo-1580587771525-78b9dba3b914?ixlib=rb-4.0.3&auto=format&fit=crop&w=640&q=80",
    "clear_cat": "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?ixlib=rb-4.0.3&auto=format&fit=crop&w=640&q=80",
    "cat_and_person": "https://images.unsplash.com/photo-1520315342629-6ea920342047?ixlib=rb-4.0.3&auto=format&fit=crop&w=640&q=80"
}

headers = {'User-Agent': 'Mozilla/5.0'}

with app.app_context():
    for name, url in images.items():
        print(f"Testing {name}...")
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            print(f"Failed to download {name}")
            continue
            
        try:
            accepted = detect_cats(resp.content)
            print(f"{name} -> {'ACCEPT' if accepted else 'REJECT'}")
        except Exception as e:
            print(f"{name} -> ERROR: {e}")
