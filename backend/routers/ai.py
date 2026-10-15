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

@router.post('/recognize')
def recognize_plate(file: UploadFile=File(...),roi: str | None=Form(None),user=Depends(operator)):
    """Upload JPEG/PNG/WebP; optional ROI = x,y,width,height. Does not write to DB."""
    _,result=ai_service.run_recognition(file,roi)
    return result

@router.post('/check-in',response_model=SessionResponse,status_code=201)
def photo_check_in(file: UploadFile=File(...),parking_spot_id: int=Form(...,gt=0),
    reservation_id: int | None=Form(None,gt=0),roi: str | None=Form(None),
    db: Session=Depends(get_db),user=Depends(operator)):
    data,result=ai_service.run_recognition(file,roi)
    plate=ai_service.require_plate(result)
    vehicle=ai_service.find_vehicle(db,plate)
    path,url=ai_service.save_evidence(data)
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
    data,result=ai_service.run_recognition(file,roi)
    plate=ai_service.require_plate(result)
    if normalize_plate(vehicle.license_plate)!=plate:
        raise HTTPException(409,'Biển số ảnh ra không khớp xe của lượt gửi; chưa check-out')
    path,url=ai_service.save_evidence(data)
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
