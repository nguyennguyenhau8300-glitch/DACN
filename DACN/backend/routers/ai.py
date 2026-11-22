from decimal import Decimal
import re
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from schemas.operations import CheckIn, CheckOut, SessionResponse
from services.parking_service import staff
from services import ai_service
from services.session_service import check_in, check_out, visible_session
from models.vehicle import Vehicle
from ai_engine.recognizer import status, normalize_plate

router=APIRouter(prefix='/ai',tags=['AI License Plate'])

def operator(user=Depends(get_current_user)):
    staff(user)
    return user

@router.get('/status')
def ai_status(user=Depends(operator)):
    return status()

@router.get('/demo/experiment')
def demo_experiment(user=Depends(operator)):
    from pathlib import Path
    import json
    root=Path(__file__).resolve().parents[1]/'ai_engine/artifacts'
    experiment=root/'synthetic-yolov8/experiment.json'
    evaluation=root/'evaluation-synthetic.json'
    stream=root/'stream-events.summary.json'
    result={'dataset_kind':'SYNTHETIC_DEMO','notice':'Ảnh/video tạo bằng chương trình; các số đo này không chứng minh độ chính xác trên camera thật.'}
    if experiment.is_file():
        data=json.loads(experiment.read_text(encoding='utf-8'));result['training']={k:data[k] for k in ['dataset_kind','epochs_requested','elapsed_seconds','metrics_test']}
    if evaluation.is_file():
        data=json.loads(evaluation.read_text(encoding='utf-8'));result['ocr']={k:v for k,v in data.items() if k!='results'}
    if stream.is_file(): result['video']=json.loads(stream.read_text(encoding='utf-8'))
    result['video_available']=(root/'camera-demo-annotated.mp4').is_file()
    return result

@router.get('/demo/video')
def demo_video(user=Depends(operator)):
    from pathlib import Path
    from fastapi import HTTPException
    path=Path(__file__).resolve().parents[1]/'ai_engine/artifacts/camera-demo-annotated.mp4'
    if not path.is_file(): raise HTTPException(404,'Chưa chạy video demo; xem ../docs/huong_dan/ai_engine.md')
    return FileResponse(path,media_type='video/mp4',headers={'Cache-Control':'private, no-store'})

@router.post('/recognize')
def recognize_plate(file: UploadFile=File(...),roi: str | None=Form(None),user=Depends(operator)):
    """Upload JPEG/PNG/WebP; optional ROI = x,y,width,height. Does not write to DB."""
    source,result=ai_service.run_recognition(file,roi)
    return {**result,**ai_service.preview_assets(source,result)}

@router.post('/check-in',response_model=SessionResponse,status_code=201)
def photo_check_in(file: UploadFile=File(...),parking_spot_id: int=Form(...,gt=0),
    reservation_id: int | None=Form(None,gt=0),roi: str | None=Form(None),
    db: Session=Depends(get_db),user=Depends(operator)):
    source,result=ai_service.run_recognition(file,roi)
    plate=ai_service.require_plate(result)
    vehicle=ai_service.find_vehicle(db,plate)
    path,url=ai_service.save_evidence(source)
    try:
        row = check_in(CheckIn(vehicle_id=vehicle.id,parking_spot_id=parking_spot_id,reservation_id=reservation_id,
            entry_plate_image=url,entry_plate_confidence=Decimal(str(result['confidence']))),db,user,commit=False,recognized_plate=plate)
        response=SessionResponse.model_validate(row)
        db.commit()
        return response
    except Exception:
        db.rollback()
        ai_service.discard_evidence(path)
        raise

@router.post('/check-out/{session_id}',response_model=SessionResponse)
def photo_check_out(session_id: int,file: UploadFile=File(...),roi: str | None=Form(None),
    db: Session=Depends(get_db),user=Depends(operator)):
    row=visible_session(db,session_id,user)
    if row.status!='ACTIVE': raise HTTPException(409,'Lượt gửi đã kết thúc')
    vehicle=db.get(Vehicle,row.vehicle_id)
    source,result=ai_service.run_recognition(file,roi)
    plate=ai_service.require_plate(result)
    if normalize_plate(vehicle.license_plate)!=plate:
        raise HTTPException(409,'Biển số ảnh ra không khớp xe của lượt gửi; chưa check-out')
    path,url=ai_service.save_evidence(source)
    try:
        row = check_out(session_id,CheckOut(exit_plate_image=url,
            exit_plate_confidence=Decimal(str(result['confidence']))),db,user,commit=False,recognized_plate=plate)
        response=SessionResponse.model_validate(row)
        db.commit()
        return response
    except Exception:
        db.rollback()
        ai_service.discard_evidence(path)
        raise

@router.get('/images/{filename}')
def evidence(filename: str,user=Depends(operator)):
    if not re.fullmatch(r'[0-9a-f]{32}\.jpg',filename): raise HTTPException(404,'Không tìm thấy ảnh')
    path=ai_service.image_dir()/filename
    if not path.is_file(): raise HTTPException(404,'Không tìm thấy ảnh')
    return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'no-store'})
