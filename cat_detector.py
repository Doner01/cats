import os
import io
import logging
from PIL import Image, ImageOps
from flask import current_app

logger = logging.getLogger(__name__)

_yolo_model = None
_model_loaded = False

def get_model():
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
    if not current_app.config.get("CAT_DETECTOR_ENABLED", False):
        return True
        
    model = get_model()
    if model is None:
        raise RuntimeError("Cat detector is currently unavailable. Model could not be loaded.")

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = ImageOps.exif_transpose(img)
        img.thumbnail((640, 640), Image.Resampling.LANCZOS)
        
        conf_threshold = float(current_app.config.get("CAT_DETECTOR_CONFIDENCE", 0.50))
        
        results = model.predict(source=img, imgsz=640, conf=conf_threshold, verbose=False, device='cpu')
        
        if not results or len(results) == 0:
            logger.info("Cat detection inference complete. Accepted: False. Threshold: %s. Detections: []", conf_threshold)
            return False
            
        result = results[0]
        accepted = False
        detected_objects = []
        
        for box in result.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            xyxy = [round(x, 2) for x in box.xyxy[0].tolist()]
            
            class_name = result.names.get(cls_id, "unknown").lower()
            detected_objects.append({
                "class": class_name,
                "confidence": round(conf, 4),
                "bbox": xyxy
            })
            
            if class_name == "cat" and conf >= conf_threshold:
                accepted = True
                
        log_msg = f"Cat detection inference complete. Accepted: {accepted}. Threshold: {conf_threshold}. Detections: {detected_objects}"
        logger.info(log_msg)
        
        return accepted
    except Exception as e:
        logger.exception("Cat detection inference failed")
        raise RuntimeError("Cat detector encountered an unexpected error.")
