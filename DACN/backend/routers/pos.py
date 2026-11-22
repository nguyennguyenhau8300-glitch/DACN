"""Signed parking tickets and staff-only POS lookup; scanning never opens a gate."""
import hashlib
import hmac
from io import BytesIO
import os
import re
import time
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import Response
from pydantic import BaseModel,ConfigDict,Field
from database import get_db
from dependencies import get_current_user
from models.vehicle import Vehicle
from services.session_service import visible_session
from services.parking_service import staff
from schemas.operations import SessionResponse

router=APIRouter(tags=['POS Tickets'])

def signature(payload):
    key=os.getenv('JWT_SECRET_KEY')
    if not key: raise HTTPException(503,'Chưa cấu hình khóa máy chủ')
    return hmac.new(key.encode(),('pos-ticket:'+payload).encode(),hashlib.sha256).hexdigest()

def decode(code):
    if not re.fullmatch(r'PARKLY1\.[1-9][0-9]{0,9}\.[0-9]{10}\.[a-f0-9]{64}',code): raise HTTPException(400,'Mã này không phải vé gửi xe Parkly hợp lệ')
    version,session,expiry,proof=code.split('.')
    payload=f'{version}.{session}.{expiry}'
    if not hmac.compare_digest(signature(payload),proof): raise HTTPException(400,'Chữ ký vé không hợp lệ')
    if int(expiry)<time.time(): raise HTTPException(409,'Vé đã hết hạn; yêu cầu cấp lại')
    return int(session)

class Scan(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    code: str=Field(min_length=1,max_length=512)

@router.get('/parking-sessions/{session_id}/ticket')
def issue(session_id: int,request: Request,db=Depends(get_db),user=Depends(get_current_user)):
    row=visible_session(db,session_id,user)
    payload=f'PARKLY1.{row.id}.{int(time.time())+30*86400}'
    code=payload+'.'+signature(payload)
    base=os.getenv('PUBLIC_BASE_URL',str(request.base_url).rstrip('/'))
    return {'parking_session_id':row.id,'code':code,'qr_url':f'{base}/pos/ticket/qr?code={code}','notice':'Mã vé dùng để tra cứu; không thay thế đăng nhập nhân viên hoặc xác nhận thanh toán.'}

@router.get('/pos/ticket/qr')
def ticket_qr(code: str):
    decode(code)
    import qrcode
    image=qrcode.make(code);output=BytesIO();image.save(output,format='PNG')
    return Response(output.getvalue(),media_type='image/png',headers={'Cache-Control':'no-store'})

@router.post('/pos/scan')
def scan(data: Scan,db=Depends(get_db),user=Depends(get_current_user)):
    staff(user)
    row=visible_session(db,decode(data.code),user)
    vehicle=db.get(Vehicle,row.vehicle_id)
    return {'session':SessionResponse.model_validate(row),'vehicle':{'license_plate':vehicle.license_plate,'vehicle_type':vehicle.vehicle_type,'energy_type':vehicle.energy_type}}
