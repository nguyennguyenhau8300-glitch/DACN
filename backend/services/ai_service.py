import io
import logging
import os
import sys
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException, UploadFile
from services.vehicle_service import plate_expression

PROJECT_ROOT=Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0,str(PROJECT_ROOT))
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
        result=recognize(data,region)
    except ImageError as exc: raise HTTPException(422,str(exc))
    except EngineBusy as exc: raise HTTPException(503,str(exc))
    except EngineUnavailable as exc:
        logger.exception('Plate OCR failed')
        raise HTTPException(503,str(exc))
    return data,result

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
    image=read_image(data)
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
