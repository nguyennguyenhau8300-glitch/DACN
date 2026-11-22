import io
import logging
import os
import sys
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from fastapi import HTTPException, UploadFile
from PIL.Image import Image
from services.vehicle_service import plate_expression

BACKEND_ROOT=Path(__file__).resolve().parents[1]
PROJECT_ROOT=BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path: sys.path.insert(0,str(BACKEND_ROOT))
from ai_engine.recognizer import recognize, read_image, normalize_plate, MAX_BYTES, ImageError, EngineUnavailable, EngineBusy
from models.vehicle import Vehicle

logger=logging.getLogger(__name__)

def image_dir():
    return Path(os.getenv('AI_IMAGE_DIR',str(PROJECT_ROOT/'backend'/'storage'/'plate_images'))).resolve()

def run_recognition(file: UploadFile, roi: str | None):
    if file.size is not None and file.size>MAX_BYTES: raise HTTPException(413,'Ảnh tối đa 8 MB')
    data=file.file.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES: raise HTTPException(413,'Ảnh tối đa 8 MB')
    region=None
    if roi:
        try: region=[int(x.strip()) for x in roi.split(',')]
        except ValueError: raise HTTPException(422,'ROI cần dạng x,y,width,height')
    try:
        started = perf_counter()
        source = read_image(data)
        result = recognize(source, region, uploaded_photo=True)
    except ImageError as exc: raise HTTPException(422,str(exc))
    except EngineBusy as exc: raise HTTPException(503,str(exc))
    except EngineUnavailable as exc:
        logger.exception('Plate OCR failed')
        raise HTTPException(503,str(exc))
    return source, {**result, 'elapsed_ms': round((perf_counter() - started) * 1000, 1)}

def require_plate(result):
    if result['needs_review'] or not result['plate']:
        raise HTTPException(422,detail={'message':'Cần chụp rõ biển số hoặc chọn ROI; chưa thay đổi lượt gửi','recognition':result})
    return result['plate']

def find_vehicle(db,plate):
    normalized=plate_expression(Vehicle.license_plate)
    matches=db.query(Vehicle).filter(normalized==plate).limit(2).all()
    if not matches: raise HTTPException(404,'Biển số chưa đăng ký; hãy tạo phương tiện trước')
    if len(matches)!=1: raise HTTPException(409,'Có nhiều xe trùng biển số sau chuẩn hóa; cần sửa dữ liệu')
    return matches[0]

def save_evidence(data):
    image=data if isinstance(data, Image) else read_image(data)
    folder=image_dir()
    filename=uuid4().hex+'.jpg'
    path=folder/filename
    try:
        folder.mkdir(parents=True,exist_ok=True)
        image.save(path,format='JPEG',quality=90)
    except OSError:
        discard_evidence(path)
        raise HTTPException(503,'Không lưu được ảnh biển số')
    return path,'/ai/images/'+filename


def discard_evidence(path):
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.exception('Could not remove orphan evidence: %s',path.name)


def preview_assets(source,result):
    import base64
    from PIL import ImageDraw
    display=source.copy();display.thumbnail((960,720))
    sx,sy=display.width/source.width,display.height/source.height
    boxes=result.get('detections') or result.get('candidates') or []
    draw=ImageDraw.Draw(display)
    for item in boxes:
        x1,y1,x2,y2=item['box'];draw.rectangle((x1*sx,y1*sy,x2*sx,y2*sy),outline='#13a46b',width=3)
    def encoded(image):
        buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=85)
        return 'data:image/jpeg;base64,'+base64.b64encode(buffer.getvalue()).decode()
    box=boxes[0]['box'] if len(boxes)==1 else None
    vehicle = preview_vehicle(source, box, result)
    if vehicle['box']:
        x1,y1,x2,y2=vehicle['box']
        draw.rectangle((x1*sx,y1*sy,x2*sx,y2*sy),outline='#2767bf',width=3)
    crop=None
    if box:
        x1,y1,x2,y2=map(int,box);x1=max(0,x1);y1=max(0,y1);x2=min(source.width,x2);y2=min(source.height,y2)
        if x2>x1 and y2>y1:
            crop=source.crop((x1,y1,x2,y2));crop.thumbnail((800,300));crop=encoded(crop)
    return {'annotated_image':encoded(display),'cropped_image':crop,'bounding_box':box,
            'vehicle_detection':vehicle}


def preview_vehicle(source, plate_box, result):
    """Suggest a visible vehicle without changing its registered data."""
    from ai_engine.detector import detect_vehicles

    empty = {'type': None, 'confidence': None, 'box': None}
    if result.get('reason') == 'multiple_plates':
        return {**empty, 'reason': 'ambiguous'}
    try:
        candidates = detect_vehicles(source)
    except Exception:
        logger.exception('Vehicle detection failed')
        return {**empty, 'reason': 'unavailable'}
    if candidates is None:
        return {**empty, 'reason': 'unavailable'}
    if plate_box:
        left, top, right, bottom = plate_box
        area = max(1, (right-left)*(bottom-top))
        candidates = [
            car for car in candidates
            if (max(0, min(right,car['box'][2])-max(left,car['box'][0]))
                * max(0, min(bottom,car['box'][3])-max(top,car['box'][1]))) / area >= .8
        ]
    if len(candidates) > 1:
        return {**empty, 'reason': 'ambiguous'}
    estimate = None
    if plate_box and result.get('plate') and not result.get('needs_review'):
        from ai_engine.vehicle_context import classify_context

        try:
            estimate = classify_context(source,plate_box)
        except Exception:
            logger.exception('Vehicle appearance classification failed')
    if candidates:
        if estimate and estimate['type'] != candidates[0]['type']:
            return {**empty, 'reason': 'inconsistent_vehicle_type'}
        return {**candidates[0], 'reason': 'matched_plate' if plate_box else 'single_visible_vehicle'}
    return estimate or {**empty, 'reason': 'not_visible'}
