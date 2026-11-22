"""Isolated four-space digital model; all telemetry travels through the real protocol."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import threading
import time
from uuid import uuid4
import httpx
from fastapi import HTTPException
from sqlalchemy import func
from database import SessionLocal
from models.simulation import SimulationSite, SimulationAction
from models.parking_lot import ParkingLot
from models.parking_area import ParkingArea
from models.parking_spot import ParkingSpot
from models.iot_device import IotDevice
from models.operations import PricingRule
from models.vehicle import Vehicle
from services.iot_service import hash_key, device_view
from services.parking_service import now
from services.layout_service import initialize_layout

ROOT=Path(__file__).resolve().parents[2]
_stop=threading.Event()


def device_key(code):
    secret=os.getenv('JWT_SECRET_KEY','')
    if not secret: raise HTTPException(503,'Chưa cấu hình khóa máy chủ')
    return hmac.new(secret.encode(),('simulation-device:'+code).encode(),hashlib.sha256).hexdigest()


def site_devices(db,lot_id):
    return db.query(IotDevice).join(ParkingSpot).join(ParkingArea).filter(ParkingArea.parking_lot_id==lot_id).order_by(IotDevice.id).all()


def require_site(db,lot_id,lock=False):
    q=db.query(SimulationSite).filter_by(parking_lot_id=lot_id)
    row=(q.with_for_update() if lock else q).first()
    if not row: raise HTTPException(409,'Chỉ thao tác trên bãi demo giao thức; không sửa bãi thực tế')
    return row


def create_site(db,user):
    # One site per operator; retries cannot create a row on the main lot.
    from models.user import User
    db.query(User).filter_by(id=user.id).with_for_update().first()
    existing=db.query(SimulationSite).first()
    if existing: return existing
    plates=json.loads((ROOT/'backend/ai_engine/assets/camera-demo.json').read_text())['plates']
    if db.query(Vehicle).filter(Vehicle.license_plate.in_(plates)).first():
        raise HTTPException(409,'Biển số trong clip demo đã tồn tại; không thay đổi chủ xe hoặc dữ liệu đó')
    lot=ParkingLot(name='Bãi demo giao thức · AI & IoT',address='Mô phỏng phần mềm — không có phần cứng',
        car_capacity=2,motorbike_capacity=2,electric_car_capacity=1,electric_motorbike_capacity=1)
    db.add(lot);db.flush()
    initialize_layout(db,lot.id,commit=False)
    site=SimulationSite(parking_lot_id=lot.id,created_by=user.id,enabled=False,paused_devices=[])
    db.add(site)
    spots=db.query(ParkingSpot).join(ParkingArea).filter(ParkingArea.parking_lot_id==lot.id).all()
    for spot in spots:
        if spot.energy_type=='ELECTRIC':spot.charger_status='READY'
        for kind in ['SENSOR']+(['CHARGER'] if spot.energy_type=='ELECTRIC' else []):
            code=f'TWIN-{uuid4().hex[:8]}-L{lot.id}-S{spot.id}-{kind}'
            db.add(IotDevice(device_code=code,parking_spot_id=spot.id,kind=kind,key_hash=hash_key(device_key(code)),
                             enabled=False,offline_after_seconds=15,monitoring_since=now()))
    for vt,en in [('CAR','GASOLINE'),('CAR','ELECTRIC'),('MOTORBIKE','GASOLINE'),('MOTORBIKE','ELECTRIC')]:
        db.add(PricingRule(parking_lot_id=lot.id,vehicle_type=vt,energy_type=en,first_hour_price=10000,additional_hour_price=5000))
    for plate,vt,en in zip(plates,['CAR','MOTORBIKE','CAR'],['GASOLINE','GASOLINE','ELECTRIC']):
        # The synthetic video renders two-line B1 plates as MOTORBIKE.
        vt='MOTORBIKE' if len(plate)==9 else 'CAR'
        db.add(Vehicle(user_id=user.id,license_plate=plate,vehicle_type=vt,energy_type=en,brand='XE MÔ PHỎNG'))
    db.commit()
    return site


def set_enabled(db,lot_id,enabled):
    site=require_site(db,lot_id,True);site.enabled=enabled;site.paused_devices=[];site.desired_states={}
    for device in site_devices(db,lot_id):
        device.enabled=enabled;device.last_seen_at=None;device.last_telemetry_at=None;device.monitoring_since=now()
        from services.alert_service import reconcile_alerts
        reconcile_alerts(db,device,db.get(ParkingSpot,device.parking_spot_id))
    db.commit();return site


def mqtt_exchange(code,key,payload):
    import paho.mqtt.client as mqtt
    subscribed=threading.Event();acknowledged=threading.Event();response={}
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='parkly-panel-'+uuid4().hex[:12])
    if os.getenv('MQTT_USER'):client.username_pw_set(os.getenv('MQTT_USER'),os.getenv('MQTT_PASSWORD'))
    if os.getenv('MQTT_TLS')=='1':client.tls_set(ca_certs=os.getenv('MQTT_CA_CERT') or None)
    def connected(c,u,flags,reason,properties):
        if reason==0:c.subscribe(f'parkly/devices/{code}/ack',qos=1)
    def received(c,u,message):
        try:body=json.loads(message.payload)
        except (ValueError,UnicodeDecodeError):return
        if body.get('device_code')==code and body.get('sequence')==payload['sequence']:
            response.update(body);acknowledged.set()
    client.on_connect=connected;client.on_subscribe=lambda *args:subscribed.set();client.on_message=received
    try:
        client.connect(os.getenv('MQTT_HOST','127.0.0.1'),int(os.getenv('MQTT_PORT','1883')),keepalive=20);client.loop_start()
        if not subscribed.wait(3):raise TimeoutError()
        result=client.publish(f'parkly/devices/{code}/telemetry',json.dumps({'api_key':key,'telemetry':payload}),qos=1,retain=False)
        result.wait_for_publish(timeout=2)
        if not acknowledged.wait(5):raise TimeoutError()
        return response
    finally:client.disconnect();client.loop_stop()


def exchange(transport,code,key,payload,port):
    if transport=='MQTT':return mqtt_exchange(code,key,payload)
    # Loopback and the actual bound server port; never trust a user-supplied Host/URL.
    response=httpx.post(f'http://127.0.0.1:{port}/iot/devices/{code}/telemetry',headers={'X-API-Key':key},json=payload,timeout=8)
    response.raise_for_status();return response.json()


def send_action(db,lot_id,device_id,data,transport,request_id,port,origin='PANEL'):
    from schemas.iot_device import Telemetry
    site=require_site(db,lot_id,True)
    if not site.enabled:raise HTTPException(409,'Bật bộ mô phỏng trước khi gửi dữ liệu')
    device=next((d for d in site_devices(db,lot_id) if d.id==device_id),None)
    if device is None:raise HTTPException(404,'Thiết bị không thuộc bãi demo')
    if origin=='KEEPALIVE':
        if device_id in site.paused_devices:raise HTTPException(409,'Bộ phát đang tạm dừng')
        data=(site.desired_states or {}).get(str(device_id),data)
    existing=db.get(SimulationAction,request_id)
    if existing:
        if (existing.parking_lot_id,existing.device_id,existing.transport,existing.payload)!=(lot_id,device_id,transport,data):
            raise HTTPException(409,'Mã yêu cầu đã dùng cho lệnh khác')
        if existing.status=='ACKNOWLEDGED':return existing
        action=existing
    else:
        pending=db.query(SimulationAction).filter_by(device_id=device_id,status='PENDING').first()
        if pending and pending.origin=='KEEPALIVE' and origin=='PANEL':
            for _ in range(15):
                db.refresh(pending)
                if pending.status!='PENDING':break
                time.sleep(.1)
            if pending.status!='PENDING':pending=None
        if pending and (now()-pending.sent_at).total_seconds()<15:raise HTTPException(409,'Thiết bị đang gửi lệnh; chờ ACK rồi thử lại')
        sequence=max(device.last_sequence,db.query(func.max(SimulationAction.sequence)).filter_by(device_id=device_id).scalar() or 0)+1
        Telemetry.model_validate({'sequence':sequence,**data})
        action=SimulationAction(id=request_id,parking_lot_id=lot_id,device_id=device_id,sequence=sequence,
            transport=transport,origin=origin,payload=data,status='PENDING',sent_at=now())
        db.add(action)
        if origin=='PANEL':site.desired_states={**(site.desired_states or {}),str(device_id):data}
    code=device.device_code;payload={'sequence':action.sequence,**data}
    db.commit()  # Release database locks before the receiving backend processes telemetry.
    started=time.perf_counter()
    try:
        ack=exchange(transport,code,device_key(code),payload,port)
        if ack.get('device_code')!=code or ack.get('sequence')!=action.sequence:raise ValueError('ACK mismatch')
        action.ack=ack;action.status='ACKNOWLEDGED'
    except Exception:
        action.status='FAILED';action.ack={'message':'Chưa nhận ACK; kiểm tra broker/backend rồi gửi lại cùng mã yêu cầu'}
    action.completed_at=now();action.elapsed_ms=round((time.perf_counter()-started)*1000,2)
    db.commit();return action


def worker_tick(port):
    with SessionLocal() as db:
        ids=[s.parking_lot_id for s in db.query(SimulationSite).filter_by(enabled=True)]
    for lot_id in ids:
        with SessionLocal() as db:
            site=require_site(db,lot_id)
            devices=[(d.id,d.last_payload or ({'sensor_status':'AVAILABLE'} if d.kind=='SENSOR' else {'charger_status':'READY','temperature_c':30}))
                     for d in site_devices(db,lot_id) if d.enabled and d.id not in site.paused_devices]
        for device_id,payload in devices:
            if _stop.is_set():return
            with SessionLocal() as db:
                try:send_action(db,lot_id,device_id,payload,'MQTT',uuid4().hex,port,'KEEPALIVE')
                except Exception:db.rollback()


async def worker():
    import asyncio
    if os.getenv('PARKLY_SIMULATION_WORKER')!='1':return
    _stop.clear()
    try:
        while True:
            await asyncio.to_thread(worker_tick,int(os.getenv('PARKLY_API_PORT','8001')))
            await asyncio.sleep(5)
    finally:_stop.set()
