import os
import io
import logging
from PIL import Image
from flask import current_app

logger = logging.getLogger(__name__)

_yolo_model = None
_model_loaded = False

def get_model():
    """Lazily load the YOLOv8 model per worker."""
    global _yolo_model, _model_loaded
    if _model_loaded:
        return _yolo_model

    model_path = current_app.config.get("CAT_DETECTOR_MODEL", "models/yolov8n.pt")
    
    if not os.path.exists(model_path):
        logger.error(f"Cat detector model not found at {model_path}. Please download it.")
        _model_loaded = True
        return None

    try:
        from ultralytics import YOLO
        logger.info(f"Loading YOLO model from {model_path} in worker {os.getpid()}")
        _yolo_model = YOLO(model_path, task='detect')
        _model_loaded = True
        return _yolo_model
    except Exception as e:
        logger.error(f"Failed to load YOLO model: {e}")
        _model_loaded = True
        return None

def detect_cats(image_bytes: bytes) -> bool:
    """
    Returns True if at least one cat is detected.
    Returns False if detection successfully ran but no cats were found.
    Raises RuntimeError if the model is unavailable or fails unexpectedly.
    """
    if not current_app.config.get("CAT_DETECTOR_ENABLED", False):
        return True
        
    model = get_model()
    if model is None:
        raise RuntimeError("Cat detector is currently unavailable.")

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img.thumbnail((640, 640))
        
        conf_threshold = float(current_app.config.get("CAT_DETECTOR_CONFIDENCE", 0.35))
        
        # CPU explicitly for VPS
        results = model.predict(source=img, imgsz=640, conf=conf_threshold, verbose=False, device='cpu')
        
        if not results or len(results) == 0:
            return False
            
        result = results[0]
        cat_class_id = None
        for class_id, class_name in result.names.items():
            if class_name.lower() == 'cat':
                cat_class_id = class_id
                break
                
        if cat_class_id is None:
            cat_class_id = 15
            
        for box in result.boxes:
            if int(box.cls[0]) == cat_class_id:
                return True
                
        return False
    except Exception as e:
        logger.error(f"Cat detection inference failed: {e}")
        raise RuntimeError("Cat detector encountered an unexpected error.")
