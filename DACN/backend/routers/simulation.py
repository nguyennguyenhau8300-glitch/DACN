import asyncio
import os
import re
import time
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict
from database import get_db, SessionLocal
from dependencies import get_current_user
from models.simulation import SimulationSite, SimulationAction, CameraObservation
from models.iot_device import IotDevice
from models.parking_area import ParkingArea
from models.parking_spot import ParkingSpot
from models.user import User
from services.parking_service import staff, management, now
from services.simulation_service import create_site, require_site, site_devices, set_enabled, send_action, ROOT
from services import live_camera
from services.auth_service import decode_access_token

router=APIRouter(tags=['Protocol simulation'])


class Enable(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled: bool


class Action(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: UUID
    device_id: int
    transport: Literal['MQTT','HTTP']='MQTT'
    scenario: Literal['EMPTY','OCCUPIED','WRONG_VEHICLE','READY','CHARGING','OVERHEAT','FAULT','OFFLINE','RESUME']


class CameraStart(BaseModel):
    model_config=ConfigDict(extra='forbid')
    mode: Literal['PREVIEW','ENTRY','EXIT']='PREVIEW'


class WokwiConfig(BaseModel):
    model_config=ConfigDict(extra='forbid')
    device_id:int


@router.get('/simulation/sites')
def sites(db=Depends(get_db),user=Depends(get_current_user)):
    staff(user)
    return [{'parking_lot_id':s.parking_lot_id,'enabled':s.enabled,'synthetic':True} for s in db.query(SimulationSite).all()]


@router.post('/simulation/sites',status_code=201)
def provision(db=Depends(get_db),user=Depends(get_current_user)):
    management(user);site=create_site(db,user)
    return {'parking_lot_id':site.parking_lot_id,'enabled':site.enabled,'synthetic':True}


def action_view(row):
    return {key:getattr(row,key) for key in ['id','device_id','sequence','transport','origin','payload','ack','status','sent_at','completed_at','elapsed_ms']}


@router.get('/simulation/{lot_id}/state')
def state(lot_id:int,db=Depends(get_db),user=Depends(get_current_user)):
    from services.iot_service import device_view
    from services.layout_service import capacity_summary
    from models.parking_lot import ParkingLot
    staff(user);site=require_site(db,lot_id)
    devices=site_devices(db,lot_id)
    spots=db.query(ParkingSpot).join(ParkingArea).filter(ParkingArea.parking_lot_id==lot_id).order_by(ParkingSpot.id).all()
    actions=db.query(SimulationAction).filter_by(parking_lot_id=lot_id,origin='PANEL').order_by(SimulationAction.sent_at.desc()).limit(30).all()
    result={'parking_lot_id':lot_id,'enabled':site.enabled,'paused_devices':site.paused_devices,'synthetic':True,
        'notice':'Mô phỏng phần mềm qua MQTT/HTTP/RTSP; không có phần cứng trong vòng thử nghiệm.',
        'devices':[device_view(d) for d in devices],
        'spots':[dict(id=s.id,spot_code=s.spot_code,spot_type=s.spot_type,energy_type=s.energy_type,status=s.status) for s in spots],
        'capacity':capacity_summary(db,db.get(ParkingLot,lot_id)),
        'actions':[action_view(a) for a in actions],'camera':{k:v for k,v in live_camera.status(lot_id).items() if k!='jpeg'}}
    return result


@router.post('/simulation/{lot_id}/enabled')
def enable(lot_id:int,data:Enable,db=Depends(get_db),user=Depends(get_current_user)):
    management(user)
    if not data.enabled:live_camera.stop(lot_id)
    site=set_enabled(db,lot_id,data.enabled)
    return {'enabled':site.enabled,'parking_lot_id':lot_id}


@router.post('/simulation/{lot_id}/actions')
def action(lot_id:int,data:Action,request:Request,db=Depends(get_db),user=Depends(get_current_user)):
    staff(user);site=require_site(db,lot_id,True)
    if not site.enabled:raise HTTPException(409,'Bật bộ mô phỏng trước')
    device=next((d for d in site_devices(db,lot_id) if d.id==data.device_id),None)
    if not device:raise HTTPException(404,'Thiết bị không thuộc bãi demo')
    if data.scenario in ('OFFLINE','RESUME'):
        paused=set(site.paused_devices)
        if data.scenario=='OFFLINE':paused.add(device.id)
        else:paused.discard(device.id)
        site.paused_devices=sorted(paused);db.commit()
        return {'status':'PAUSED' if data.scenario=='OFFLINE' else 'RESUMED',
            'message':'Đã ngừng phát telemetry. Chờ 15–25 giây để bộ giám sát báo mất kết nối.' if data.scenario=='OFFLINE' else 'Đã tiếp tục phát dữ liệu theo chu kỳ'}
    if device.id in site.paused_devices:raise HTTPException(409,'Thiết bị đang ngắt kết nối; chọn kết nối lại trước')
    if device.kind=='SENSOR':
        if data.scenario not in ('EMPTY','OCCUPIED','WRONG_VEHICLE'):raise HTTPException(422,'Chọn kịch bản cảm biến ô đỗ')
        payload={'sensor_status':'AVAILABLE' if data.scenario=='EMPTY' else 'OCCUPIED'}
        if data.scenario=='WRONG_VEHICLE':
            spot=db.get(ParkingSpot,device.parking_spot_id)
            payload.update(observed_vehicle_type='MOTORBIKE' if spot.spot_type=='CAR' else 'CAR',observed_energy_type='GASOLINE')
    else:
        if data.scenario not in ('READY','CHARGING','OVERHEAT','FAULT'):raise HTTPException(422,'Chọn kịch bản điểm sạc')
        payload={'charger_status':{'READY':'READY','CHARGING':'CHARGING','OVERHEAT':'FAULT','FAULT':'FAULT'}[data.scenario],
                 'temperature_c':85 if data.scenario=='OVERHEAT' else 30,'power_kw':1.5 if data.scenario=='CHARGING' else 0}
    port=(request.scope.get('server') or ('127.0.0.1',8001))[1] or 8001
    return action_view(send_action(db,lot_id,device.id,payload,data.transport,data.request_id.hex,port))


@router.post('/simulation/{lot_id}/camera/start')
def start_camera(lot_id:int,data:CameraStart,db=Depends(get_db),user=Depends(get_current_user)):
    staff(user);site=require_site(db,lot_id)
    if not site.enabled:raise HTTPException(409,'Bật bộ mô phỏng trước')
    return live_camera.start(lot_id,user.id,data.mode)


@router.post('/simulation/{lot_id}/camera/stop')
def stop_camera(lot_id:int,db=Depends(get_db),user=Depends(get_current_user)):
    staff(user);require_site(db,lot_id);live_camera.stop(lot_id);return {'state':'STOPPED'}


@router.get('/simulation/observations')
def observations(parking_lot_id:int,limit:int=Query(40,ge=1,le=100),db=Depends(get_db),user=Depends(get_current_user)):
    staff(user)
    rows=db.query(CameraObservation).filter_by(parking_lot_id=parking_lot_id).order_by(CameraObservation.recorded_at.desc()).limit(limit).all()
    return [{**{c.name:getattr(row,c.name) for c in CameraObservation.__table__.columns},
             'image_url':f'/simulation/observations/{row.id}/image','synthetic':True} for row in rows]


@router.get('/simulation/observations/{ident}/image')
def image(ident:str,db=Depends(get_db),user=Depends(get_current_user)):
    staff(user)
    if not re.fullmatch(r'[0-9a-f]{32}',ident) or not db.get(CameraObservation,ident):raise HTTPException(404,'Không tìm thấy bằng chứng')
    path=live_camera.evidence_path(ident)
    if not path.is_file():raise HTTPException(404,'Ảnh bằng chứng không còn trên máy chủ')
    return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})


def socket_allowed(token):
    claims=decode_access_token(token)
    if not claims:return False
    try:ident=int(claims['sub'])
    except (KeyError,ValueError,TypeError):return False
    with SessionLocal() as db:
        user=db.get(User,ident)
        return bool(user and user.is_active and user.role in ('ADMIN','MANAGER','SECURITY'))


@router.websocket('/ws/live-camera')
async def frames(socket:WebSocket):
    origin=socket.headers.get('origin')
    allowed={s.strip().rstrip('/') for s in os.getenv('CORS_ORIGINS','http://localhost:3000,http://localhost:5173').split(',')}
    if origin and urlsplit(origin).netloc!=socket.headers.get('host') and origin.rstrip('/') not in allowed:
        await socket.close(code=1008);return
    await socket.accept()
    try:
        auth=await asyncio.wait_for(socket.receive_json(),10)
        token=auth.get('token') if isinstance(auth,dict) else None;lot_id=auth.get('parking_lot_id') if isinstance(auth,dict) else None
        if not isinstance(token,str) or len(token)>8192 or type(lot_id) is not int or not await asyncio.to_thread(socket_allowed,token):
            await socket.close(code=1008);return
        last=None;checked=0
        while True:
            if time.monotonic()-checked>10:
                if not await asyncio.to_thread(socket_allowed,token):await socket.close(code=1008);return
                checked=time.monotonic()
            value=await asyncio.to_thread(live_camera.status,lot_id)
            stamp=(value.get('frame_id'),value['state'])
            if stamp!=last:
                await asyncio.wait_for(socket.send_json({'type':'frame',**value}),3);last=stamp
            else:await asyncio.wait_for(socket.send_json({'type':'ping','state':value['state']}),3)
            await asyncio.sleep(.4)
    except (WebSocketDisconnect,asyncio.TimeoutError,RuntimeError,ValueError):pass


@router.get('/simulation/firmware/{name}')
def firmware(name:Literal['sensor','diagram','wokwi'],user=Depends(get_current_user)):
    staff(user)
    paths={'sensor':ROOT/'backend/iot/esp32/parkly_sensor.ino','diagram':ROOT/'backend/iot/esp32/wiring.svg','wokwi':ROOT/'backend/iot/wokwi/diagram.json'}
    path=paths[name]
    if not path.is_file():raise HTTPException(404,'Chưa có file tham khảo')
    return FileResponse(path,filename=path.name,headers={'Cache-Control':'private, no-store'})


@router.post('/simulation/{lot_id}/wokwi-config')
def wokwi_config(lot_id:int,data:WokwiConfig,db=Depends(get_db),user=Depends(get_current_user)):
    from sqlalchemy import func
    from services.simulation_service import device_key
    from services.iot_service import hash_key
    import json
    if user.role!='ADMIN':raise HTTPException(403,'Chỉ ADMIN được xuất cấu hình khóa thiết bị')
    site=require_site(db,lot_id,True)
    if not site.enabled:raise HTTPException(409,'Bật bộ mô phỏng trước')
    device=next((d for d in site_devices(db,lot_id) if d.id==data.device_id and d.kind=='SENSOR'),None)
    if not device:raise HTTPException(404,'Chọn cảm biến thuộc bãi demo')
    key=device_key(device.device_code)
    if hash_key(key)!=device.key_hash:raise HTTPException(409,'Khóa đã được đổi thủ công; không xuất khóa cũ')
    site.paused_devices=sorted(set(site.paused_devices)|{device.id})
    sequence=max(device.last_sequence,db.query(func.max(SimulationAction.sequence)).filter_by(device_id=device.id).scalar() or 0)+1000
    values={'WIFI_SSID':'Wokwi-GUEST','WIFI_PASSWORD':'','MQTT_HOST':'host.wokwi.internal',
            'MQTT_USER':os.getenv('MQTT_USER',''),'MQTT_PASSWORD':os.getenv('MQTT_PASSWORD',''),
            'DEVICE_CODE':device.device_code,'DEVICE_API_KEY':key}
    body='// Local demo credentials. Do not publish or commit this file.\n'
    body+='\n'.join('#define '+k+' '+json.dumps(v) for k,v in values.items())
    body+=f'\n#define DEVICE_SEQUENCE_START {sequence}ULL\n'
    db.commit()
    return Response(body,media_type='text/plain',headers={'Content-Disposition':'attachment; filename="secrets.h"','Cache-Control':'private, no-store'})
