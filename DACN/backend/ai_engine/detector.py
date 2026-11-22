"""YOLOv8 plate detection for uploaded photos and the synthetic demo."""
import os
from pathlib import Path
import threading

_models = {}
_lock=threading.Lock()
DEFAULT=Path(__file__).resolve().parent/'artifacts/synthetic-yolov8/weights/best.pt'
PHOTO_MODEL=Path(__file__).resolve().parent/'artifacts/real-photo-yolov8/best.pt'
VEHICLE_MODEL=Path(__file__).resolve().parent/'artifacts/vehicle-yolov8/yolov8n.pt'
VEHICLE_CLASSES={2: 'CAR', 3: 'MOTORBIKE'}

def model_path(*, photo=False):
    if os.getenv('AI_DETECTOR_MODE','auto').lower()=='ocr': return None
    if photo:
        configured = os.getenv('AI_PHOTO_YOLO_MODEL')
        if configured:
            return Path(configured).resolve()
    configured=os.getenv('AI_YOLO_MODEL')
    if configured:
        return Path(configured).resolve()
    if photo and PHOTO_MODEL.is_file():
        return PHOTO_MODEL
    return DEFAULT if DEFAULT.is_file() else None

def detector_status(*, photo=False):
    path=model_path(photo=photo)
    sources = {
        DEFAULT: ('SYNTHETIC_DEMO', 'Trọng số huấn luyện trên ảnh tổng hợp.'),
        PHOTO_MODEL: ('VIETNAMESE_PHOTO_DATASET', 'Trọng số tinh chỉnh trên ảnh biển số Việt Nam công khai.'),
    }
    kind, notice = sources.get(path, ('USER_CONFIGURED', 'Trọng số từ cấu hình.') if path else ('NOT_CONFIGURED', 'Đang dùng OCR.'))
    return {'engine':'YOLOv8','configured':path is not None,'weights_available':bool(path and path.is_file()),
            'loaded':path in _models,'dataset_kind':kind,'notice':notice}

def predict(path, image, *, size, confidence, classes=None):
    with _lock:
        if path not in _models:
            os.environ.setdefault('YOLO_AUTOINSTALL', 'false')
            from ultralytics import YOLO
            if not _models and not any(name in os.environ for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS')):
                import torch
                torch.set_num_threads(min(torch.get_num_threads(),4))
            _models[path] = YOLO(str(path))
        return _models[path].predict(image, imgsz=size, conf=confidence, classes=classes,
                                     device='cpu', verbose=False)[0].boxes


def detect(image, *, photo=False, size=None):
    path=model_path(photo=photo)
    if path is None: return None
    if not path.is_file(): raise FileNotFoundError('Không tìm thấy trọng số YOLO đã cấu hình')
    size = size or (416 if photo and path != DEFAULT else 320)
    prediction=predict(path, image, size=size, confidence=float(os.getenv('AI_DETECTION_CONFIDENCE','0.35')), classes=[0])
    boxes=[]
    for box,score in zip(prediction.xyxy.tolist(), prediction.conf.tolist()):
        x1,y1,x2,y2=box
        pad=max(4,(y2-y1)*.08)
        boxes.append({'box':[max(0,int(x1-pad)),max(0,int(y1-pad)),min(image.width,int(x2+pad)),min(image.height,int(y2+pad))],
                      'confidence':round(score,4)})
    return boxes


def detect_vehicles(image):
    """Return YOLOv8 COCO car and motorcycle boxes in original-image pixels."""
    if not VEHICLE_MODEL.is_file():
        return None
    boxes = predict(VEHICLE_MODEL, image, size=640, confidence=.45, classes=list(VEHICLE_CLASSES))
    return [
        {'type': VEHICLE_CLASSES[int(label)], 'confidence': round(score, 4),
         'box': [round(value) for value in box]}
        for box, score, label in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist())
    ]
