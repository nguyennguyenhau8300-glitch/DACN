"""Internal operation simulator: real AI and business rules, no external simulator."""
from datetime import timedelta
from decimal import Decimal
import io,json,secrets,time
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from database import SessionLocal
from models.internal_demo import InternalDemoRun
from models.iot_device import IotDevice
from models.parking_spot import ParkingSpot
from models.parking_area import ParkingArea
from models.parking_lot import ParkingLot
from models.operations import ParkingSession
from models.vehicle import Vehicle
from models.extensions import SandboxOrder
from services import ai_service
from services.iot_service import apply_device_telemetry, hash_key, devices_allow_entry, load_devices_for_availability
from services.parking_service import now
from services.vehicle_service import plate_expression
from schemas.iot_device import Telemetry

SAMPLES=Path(__file__).resolve().parents[1]/'test_data'


def sample_rows():
    generated = json.loads((SAMPLES/'manifest.json').read_text(encoding='utf-8'))
    checked = SAMPLES/'verified-samples.json'
    verified = json.loads(checked.read_text(encoding='utf-8')) if checked.is_file() else []
    return verified + generated


def sample(ident):
    row=next((r for r in sample_rows() if r['id']==ident),None)
    if not row:raise HTTPException(404,'Không tìm thấy ảnh mẫu')
    return row,SAMPLES/row['filename']


def prepare(db,user):
    vehicles=[]
    for item in sample_rows():
        if not item['id'].endswith('_clear'):continue
        vehicle=db.query(Vehicle).filter(plate_expression(Vehicle.license_plate)==item['plate']).first()
        if vehicle:
            if vehicle.brand not in ('Xe mẫu nội bộ','XE MÔ PHỎNG') or (vehicle.vehicle_type,vehicle.energy_type)!=(item['vehicle_type'],item['energy_type']):
                raise HTTPException(409,'Biển số mẫu đã thuộc xe khác; không ghi đè hồ sơ có sẵn')
        else:
            vehicle=Vehicle(user_id=user.id,license_plate=item['plate'],vehicle_type=item['vehicle_type'],energy_type=item['energy_type'],brand='Xe mẫu nội bộ')
            db.add(vehicle);db.flush()
        vehicles.append(vehicle)
    return vehicles


def active_lot(db,lot_id):
    lot=db.get(ParkingLot,lot_id)
    if not lot or not lot.is_active:raise HTTPException(409,'Bãi không hoạt động')
    return lot


def _spot(db,spot_id):
    spot=db.query(ParkingSpot).filter_by(id=spot_id).populate_existing().with_for_update().first()
    if not spot:raise HTTPException(404,'Không tìm thấy ô đỗ')
    active_lot(db,db.get(ParkingArea,spot.parking_area_id).parking_lot_id)
    return spot


def internal_signal(db,spot_id,kind,payload):
    spot=_spot(db,spot_id)
    if kind=='CHARGER' and spot.energy_type!='ELECTRIC':raise HTTPException(422,'Chỉ ô điện có điểm sạc')
    if kind=='CHARGER' and payload.get('charger_status')=='CHARGING' and spot.charger_status!='READY':
        raise HTTPException(409,'Điểm sạc chưa được đưa vào vận hành')
    device=db.query(IotDevice).filter_by(parking_spot_id=spot.id,kind=kind).populate_existing().with_for_update().first()
    if device and not device.simulation_only:raise HTTPException(409,'Ô này đang gắn thiết bị giao thức; không ghi đè bằng giả lập nội bộ')
    if not device:
        device=IotDevice(device_code=f'INTERNAL-{kind}-{spot.id}',parking_spot_id=spot.id,kind=kind,
            key_hash=hash_key(secrets.token_urlsafe(32)),enabled=True,simulation_only=True,monitoring_since=now())
        db.add(device);db.flush()
    if not device.enabled:raise HTTPException(409,'Thiết bị giả lập đang bị tắt')
    data=Telemetry.model_validate({'sequence':device.last_sequence+1,**payload})
    return apply_device_telemetry(db,device,spot,data)


def begin(db,user,ident,lot_id,kind,spec):
    active_lot(db,lot_id)
    old=db.get(InternalDemoRun,ident)
    if old:
        if (old.user_id,old.parking_lot_id,old.kind,old.request_spec)!=(user.id,lot_id,kind,spec):raise HTTPException(409,'Mã yêu cầu đã dùng cho thao tác khác')
        if old.status=='RUNNING':raise HTTPException(409,'Kịch bản đang xử lý; kiểm tra nhật ký trước khi thử lại')
        return old,False
    row=InternalDemoRun(id=ident,parking_lot_id=lot_id,user_id=user.id,kind=kind,status='RUNNING',request_spec=spec,steps=[],result={})
    db.add(row);db.flush();return row,True


def signal_run(db,user,ident,spot_id,kind,payload):
    spot=db.get(ParkingSpot,spot_id)
    if not spot:raise HTTPException(404,'Không tìm thấy ô đỗ')
    lot_id=db.get(ParkingArea,spot.parking_area_id).parking_lot_id
    run,new=begin(db,user,ident,lot_id,kind,{'spot_id':spot_id,'payload':payload})
    if not new:return run
    result=internal_signal(db,spot_id,kind,payload)
    run.status='DONE';run.completed_at=now();run.result=result
    run.steps=[{'label':'Cập nhật cảm biến' if kind=='SENSOR' else 'Cập nhật điểm sạc','status':'DONE','at':now().isoformat()}]
    db.commit();return run


def _evidence(data,result):
    paths=[]
    try:
        path,url=ai_service.save_evidence(data);paths.append(path)
        boxes=result.get('detections') or result.get('candidates') or []
        crop_url=None
        if len(boxes)==1:
            image=ai_service.read_image(data);box=tuple(map(int,boxes[0]['box']));crop=image.crop(box)
            buffer=io.BytesIO();crop.save(buffer,format='JPEG',quality=90)
            path,crop_url=ai_service.save_evidence(buffer.getvalue());paths.append(path)
        return paths,{'image_url':url,'crop_url':crop_url,'plate':result['plate'],'confidence':result['confidence'],
                      'bounding_box':boxes[0]['box'] if len(boxes)==1 else None}
    except Exception:
        for path in paths:ai_service.discard_evidence(path)
        raise


def entry_run(db,user,ident,lot_id):
    from ai_engine.recognizer import recognize
    from schemas.operations import CheckIn
    from services.session_service import check_in
    run,new=begin(db,user,ident,lot_id,'ENTRY',{'sample_id':'car_electric_clear'})
    if not new:return run
    db.commit();steps=[];paths=[]
    def step(label):steps.append({'label':label,'status':'DONE','at':now().isoformat()})
    try:
        item,file=sample('car_electric_clear');data=file.read_bytes();result=recognize(data)
        plate=ai_service.require_plate(result)
        if plate!=item['plate']:raise HTTPException(422,'AI chưa đọc đúng xe mẫu; không tiếp tục kịch bản')
        step('Camera lấy ảnh mẫu → YOLOv8 và RapidOCR nhận diện')
        prepare(db,user)
        vehicle=db.query(Vehicle).filter(plate_expression(Vehicle.license_plate)==plate).populate_existing().with_for_update().one()
        if db.query(ParkingSession).filter_by(vehicle_id=vehicle.id,status='ACTIVE').first():raise HTTPException(409,'Xe mẫu đang có lượt gửi; chạy kịch bản xe ra trước')
        candidates=db.query(ParkingSpot).join(ParkingArea).filter(ParkingArea.parking_lot_id==lot_id,
            ParkingSpot.spot_type=='CAR',ParkingSpot.energy_type=='ELECTRIC',ParkingSpot.status=='AVAILABLE',ParkingSpot.charger_status=='READY').order_by(ParkingSpot.id).with_for_update(of=ParkingSpot,skip_locked=True).all()
        devices, overheated = load_devices_for_availability(db, [candidate.id for candidate in candidates])
        spot = next((candidate for candidate in candidates
                     if all(device.simulation_only for device in devices.get(candidate.id, ()))
                     and devices_allow_entry(devices.get(candidate.id, ()), overheated_ids=overheated)), None)
        if not spot:raise HTTPException(409,'Không có ô ô tô điện trống, sạc sẵn sàng và phù hợp giả lập nội bộ')
        paths,evidence=_evidence(data,result)
        internal_signal(db,spot.id,'SENSOR',{'sensor_status':'AVAILABLE'})
        internal_signal(db,spot.id,'CHARGER',{'charger_status':'READY','power_kw':0,'temperature_c':30})
        session=check_in(CheckIn(vehicle_id=vehicle.id,parking_spot_id=spot.id,entry_plate_image=evidence['image_url'],
            entry_plate_confidence=Decimal(str(result['confidence']))),db,user,commit=False,recognized_plate=plate)
        step('Nhận xe hợp lệ → xếp lệnh mở barie vào')
        internal_signal(db,spot.id,'SENSOR',{'sensor_status':'OCCUPIED'})
        power=min(7,float(spot.charging_power_kw)) if spot.charging_power_kw is not None else 7
        internal_signal(db,spot.id,'CHARGER',{'charger_status':'CHARGING','power_kw':power,'temperature_c':30})
        step(f'Xe đỗ tại {spot.spot_code} → đang sạc {power:g} kW')
        run=db.get(InternalDemoRun,ident);run.parking_session_id=session.id;run.status='DONE';run.steps=steps
        run.result={**evidence,'spot_code':spot.spot_code,'power_kw':power,'synthetic':True};run.completed_at=now();db.commit();return run
    except Exception as exc:
        db.rollback()
        for path in paths:ai_service.discard_evidence(path)
        run=db.get(InternalDemoRun,ident);run.status='FAILED';run.steps=steps+[{'label':str(exc.detail) if isinstance(exc,HTTPException) else 'Không hoàn tất được kịch bản; dữ liệu giao dịch được giữ nguyên','status':'FAILED','at':now().isoformat()}]
        run.completed_at=now();db.commit();return run


def exit_run(db,user,ident,lot_id,session_id):
    from schemas.operations import CheckOut
    from services.session_service import check_out
    run,new=begin(db,user,ident,lot_id,'EXIT',{'session_id':session_id})
    if not new:return run
    source=db.query(InternalDemoRun).filter_by(kind='ENTRY',parking_session_id=session_id,parking_lot_id=lot_id,status='DONE').first()
    if not source:raise HTTPException(409,'Kịch bản chỉ áp dụng cho lượt xe được tạo bởi giả lập nội bộ')
    session=db.query(ParkingSession).filter_by(id=session_id).populate_existing().with_for_update().first()
    if not session or session.status!='ACTIVE':raise HTTPException(409,'Lượt gửi không còn đang hoạt động')
    db.query(Vehicle).filter_by(id=session.vehicle_id).with_for_update().first()
    internal_signal(db,session.parking_spot_id,'CHARGER',{'charger_status':'READY','power_kw':0,'temperature_c':30})
    session=check_out(session.id,CheckOut(),db,user,commit=False)
    run.parking_session_id=session.id;run.steps=[{'label':'Ngắt sạc → kết thúc lượt gửi → tính phí từ thời gian thực','status':'DONE','at':now().isoformat()}]
    if session.total_amount==0:
        internal_signal(db,session.parking_spot_id,'SENSOR',{'sensor_status':'AVAILABLE'})
        run.status='DONE';run.steps=run.steps+[{'label':'Lượt miễn phí → mở barie ra và trả ô về sẵn sàng','status':'DONE','at':now().isoformat()}]
    else:
        order=SandboxOrder(id=uuid4().hex,parking_session_id=session.id,provider='INTERNAL',amount=session.total_amount,expires_at=now()+timedelta(minutes=15))
        db.add(order);db.flush();run.sandbox_order_id=order.id;run.status='AWAITING_PAYMENT'
        db.flush()
        internal_signal(db,session.parking_spot_id,'SENSOR',{'sensor_status':'OCCUPIED'})
        run.steps=run.steps+[{'label':'Đã tạo QR thanh toán thử; chờ xác nhận, ô vẫn đang giữ xe','status':'WAITING','at':now().isoformat()}]
    run.result={'amount':str(session.total_amount),'synthetic':True};run.completed_at=now();db.commit();return run


def finalize_departure(db,session_id):
    run=db.query(InternalDemoRun).filter_by(kind='EXIT',parking_session_id=session_id,status='AWAITING_PAYMENT').with_for_update().first()
    if not run:return
    session=db.get(ParkingSession,session_id)
    if run.sandbox_order_id:
        order=db.get(SandboxOrder,run.sandbox_order_id)
        if order and order.status=='PENDING':order.status='CANCELLED';order.completed_at=now()
    run.status='DONE';run.completed_at=now()
    db.flush()
    internal_signal(db,session.parking_spot_id,'SENSOR',{'sensor_status':'AVAILABLE'})
    run.steps=[{**s,'status':'DONE' if s['status']=='WAITING' else s['status']} for s in run.steps]+[
        {'label':'Đã xác nhận thanh toán mô phỏng → mở barie ra → ô sẵn sàng','status':'DONE','at':now().isoformat()}]
    db.flush()
