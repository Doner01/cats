import io
import logging
import os
from typing import Any

from flask import current_app
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

_yolo_model: Any = None
_model_loaded = False


def get_model() -> Any:
    global _yolo_model, _model_loaded

    if _model_loaded:
        return _yolo_model

    model_path = str(
        current_app.config.get("CAT_DETECTOR_MODEL", "models/yolov8n.pt")
    )

    if not os.path.exists(model_path):
        logger.error("Cat detector model not found at %s. Please download it.", model_path)
        _model_loaded = True
        return None

    try:
        from ultralytics import YOLO

        logger.info("Loading YOLO model from %s in worker %s", model_path, os.getpid())
        _yolo_model = YOLO(model_path, task="detect")
        _model_loaded = True
        return _yolo_model
    except Exception:
        logger.exception("Failed to load YOLO model")
        _model_loaded = True
        return None


def detect_cats(image_bytes: bytes) -> bool:
    if not current_app.config.get("CAT_DETECTOR_ENABLED", False):
        return True

    model = get_model()
    if model is None:
        raise RuntimeError(
            "Cat detector is currently unavailable. Model could not be loaded."
        )

    try:
        with Image.open(io.BytesIO(image_bytes)) as opened:
            img = ImageOps.exif_transpose(opened).convert("RGB")

        img.thumbnail((640, 640), Image.Resampling.LANCZOS)

        conf_threshold = float(
            current_app.config.get("CAT_DETECTOR_CONFIDENCE", 0.50)
        )

        # Ultralytics types allow either a list or an iterator. Converting to a
        # list makes indexing/emptiness checks explicit and keeps Pylance happy.
        raw_results = model.predict(
            source=img,
            imgsz=640,
            conf=conf_threshold,
            verbose=False,
            device="cpu",
            stream=False,
        )
        results = list(raw_results)

        if not results:
            logger.info(
                "Cat detection inference complete. Accepted: False. "
                "Threshold: %s. Detections: []",
                conf_threshold,
            )
            return False

        # Detection mode should return an Ultralytics Results object. Keep the
        # runtime check fail-closed so an unexpected result type is never accepted.
        result: Any = results[0]
        boxes = getattr(result, "boxes", None)
        names = getattr(result, "names", None)

        if boxes is None or not isinstance(names, dict):
            raise RuntimeError("Unexpected YOLO detection result format.")

        accepted = False
        detected_objects = []

        for box in boxes:
            cls_id = int(box.cls[0])
            confidence = float(box.conf[0])
            xyxy = [round(float(x), 2) for x in box.xyxy[0].tolist()]
            class_name = str(names.get(cls_id, "unknown")).lower()

            detected_objects.append(
                {
                    "class": class_name,
                    "confidence": round(confidence, 4),
                    "bbox": xyxy,
                }
            )

            if class_name == "cat" and confidence >= conf_threshold:
                accepted = True

        logger.info(
            "Cat detection inference complete. Accepted: %s. "
            "Threshold: %s. Detections: %s",
            accepted,
            conf_threshold,
            detected_objects,
        )
        return accepted

    except Exception as exc:
        logger.exception("Cat detection inference failed")
        raise RuntimeError(
            "Cat detector encountered an unexpected error."
        ) from exc
