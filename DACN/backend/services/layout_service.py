from fastapi import HTTPException
from sqlalchemy import func
from models.parking_lot import ParkingLot
from models.parking_area import ParkingArea
from models.parking_spot import ParkingSpot

GROUPS = [('CAR','GASOLINE','CG','Ô tô xăng'),('CAR','ELECTRIC','CE','Ô tô điện'),
          ('MOTORBIKE','GASOLINE','MG','Xe máy xăng'),('MOTORBIKE','ELECTRIC','ME','Xe máy điện')]
CAPACITY_FIELDS = ['car_capacity','motorbike_capacity','electric_car_capacity','electric_motorbike_capacity']
CHARGING_FIELDS = ['energy_type','charger_type','charging_station_code','charging_port_code','charging_power_kw','charger_status']
SPOT_STATUSES = ('AVAILABLE', 'RESERVED', 'OCCUPIED', 'MAINTENANCE')

def quotas(config):
    if not (1 <= config.car_capacity <= 50 and 1 <= config.motorbike_capacity <= 120):
        raise HTTPException(422,'Sức chứa: 1–50 ô tô và 1–120 xe máy')
    if not (0 <= config.electric_car_capacity <= config.car_capacity and 0 <= config.electric_motorbike_capacity <= config.motorbike_capacity):
        raise HTTPException(422,'Số chỗ điện không được vượt tổng chỗ của loại xe')
    return {('CAR','GASOLINE'):config.car_capacity-config.electric_car_capacity,
        ('CAR','ELECTRIC'):config.electric_car_capacity,
        ('MOTORBIKE','GASOLINE'):config.motorbike_capacity-config.electric_motorbike_capacity,
        ('MOTORBIKE','ELECTRIC'):config.electric_motorbike_capacity}

def counts(db,lot_id,exclude_id=None):
    q=db.query(ParkingSpot.spot_type, ParkingSpot.energy_type, func.count(ParkingSpot.id)).join(ParkingArea).filter(ParkingArea.parking_lot_id==lot_id)
    if exclude_id is not None:q=q.filter(ParkingSpot.id!=exclude_id)
    result={}
    for spot_type, energy_type, count in q.group_by(ParkingSpot.spot_type, ParkingSpot.energy_type):
        key = ('CAR' if spot_type == 'DISABLED' else spot_type, energy_type)
        result[key] = result.get(key, 0) + count
    return result

def lock_lot_for_area(db,area_id):
    area=db.get(ParkingArea,area_id)
    if not area:raise HTTPException(404,'Không tìm thấy khu vực')
    return db.query(ParkingLot).filter_by(id=area.parking_lot_id).populate_existing().with_for_update().first()

def validate_capacity(db,lot,config=None):
    limits=quotas(config or lot)
    for key,count in counts(db,lot.id).items():
        if count>limits.get(key,0):raise HTTPException(409,'Sức chứa mới nhỏ hơn số ô đã tạo; hãy điều chỉnh sơ đồ trước')

def check_new_spot_capacity(db,lot,spot_type,energy_type,exclude_id=None):
    key=('CAR' if spot_type=='DISABLED' else spot_type,energy_type)
    if counts(db,lot.id,exclude_id).get(key,0)>=quotas(lot).get(key,0):
        raise HTTPException(409,'Đã đủ số chỗ cấu hình cho nhóm xe này')

def validate_charging(spot):
    if spot.energy_type=='GASOLINE':
        if spot.charger_type!='NONE' or spot.charger_status!='NOT_APPLICABLE' or any(
            getattr(spot,k) is not None for k in ['charging_station_code','charging_port_code','charging_power_kw']):
            raise HTTPException(422,'Chỗ xe xăng không có cấu hình sạc')
    else:
        expected='SOCKET' if spot.spot_type=='MOTORBIKE' else 'EV_CHARGER'
        if spot.charger_type!=expected or not spot.charging_station_code or not spot.charging_port_code:
            raise HTTPException(422,'Chỗ điện cần đúng loại thiết bị, mã trạm và mã cổng/ổ cắm')
        if spot.charger_status=='NOT_APPLICABLE':
            raise HTTPException(422,'Chỗ điện cần trạng thái thiết bị sạc')

def check_vehicle_spot(vehicle,spot,db,*,allow_in_use=False):
    spot_type='CAR' if spot.spot_type=='DISABLED' else spot.spot_type
    if (vehicle.vehicle_type,vehicle.energy_type)!=(spot_type,spot.energy_type):
        raise HTTPException(400,'Ô đỗ không phù hợp loại xe hoặc nguồn năng lượng')
    from services.iot_service import devices_allow_entry, spot_devices
    if not devices_allow_entry(
        spot_devices(db, spot.id), allow_occupied_sensor=spot.status == 'RESERVED' or allow_in_use,
        allow_busy_charger=allow_in_use,
    ):
        raise HTTPException(409,'Thiết bị IoT chưa có dữ liệu mới hoặc điểm sạc không sẵn sàng')
    if vehicle.energy_type=='ELECTRIC':
        validate_charging(spot)
        if spot.charger_status!='READY':raise HTTPException(409,'Điểm sạc chưa sẵn sàng; chọn ô khác')

def spot_availability(db, rows):
    """Annotate booking eligibility and return charging readiness for each displayed spot."""
    from services.iot_service import devices_allow_entry, load_devices_for_availability
    from services.parking_service import now

    devices, overheated = load_devices_for_availability(db, [spot.id for spot, _ in rows])
    at = now()
    result = []
    for spot, lot_active in rows:
        attached = devices.get(spot.id, ())
        charging_ready = spot.charger_status == 'READY' and devices_allow_entry(
            (device for device in attached if device.kind == 'CHARGER'), at=at, overheated_ids=overheated,
        )
        spot.available_for_booking = bool(
            lot_active and spot.status == 'AVAILABLE'
            and (spot.energy_type == 'GASOLINE' or charging_ready)
            and devices_allow_entry(attached, at=at, overheated_ids=overheated)
        )
        result.append((spot, charging_ready))
    return result


def parking_snapshot(db, lot):
    query = db.query(ParkingSpot).join(ParkingArea).filter(ParkingArea.parking_lot_id == lot.id)
    spots = query.order_by(ParkingSpot.id).all()
    states = spot_availability(db, [(spot, lot.is_active) for spot in spots])
    limits = quotas(lot)
    groups = {
        (vt, en): {'vehicle_type': vt, 'energy_type': en, 'label': label, 'capacity': limits[(vt, en)],
                   'configured_spots': 0, 'available_for_booking': 0, 'status_counts': dict.fromkeys(SPOT_STATUSES, 0),
                   'charging_points': 0, 'ready_charging_points': 0}
        for vt, en, _, label in GROUPS
    }
    for spot, charging_ready in states:
        spot_type = 'CAR' if spot.spot_type == 'DISABLED' else spot.spot_type
        group = groups.get((spot_type, spot.energy_type))
        if group is None:
            continue
        group['configured_spots'] += 1
        group['available_for_booking'] += spot.available_for_booking
        if spot.status in group['status_counts']:
            group['status_counts'][spot.status] += 1
        group['charging_points'] += spot.charger_type != 'NONE'
        group['ready_charging_points'] += charging_ready
    capacity = {'parking_lot_id': lot.id, 'total_capacity': sum(limits.values()),
                'total_configured_spots': len(spots), 'groups': list(groups.values())}
    return {'spots': spots, 'capacity': capacity}


def capacity_summary(db, lot):
    return parking_snapshot(db, lot)['capacity']

def initialize_layout(db,lot_id,*,commit=True):
    lot=db.query(ParkingLot).filter_by(id=lot_id).populate_existing().with_for_update().first()
    if not lot:raise HTTPException(404,'Không tìm thấy bãi xe')
    validate_capacity(db,lot)
    existing=counts(db,lot.id);created=0
    station_codes={row[0] for row in db.query(ParkingSpot.charging_station_code).filter(ParkingSpot.charging_station_code.isnot(None))}
    for vt,en,prefix,label in GROUPS:
        needed=quotas(lot)[(vt,en)]-existing.get((vt,en),0)
        if needed==0:continue
        area=db.query(ParkingArea).filter_by(parking_lot_id=lot.id,name=label).order_by(ParkingArea.id).first()
        if area is None:
            area=ParkingArea(parking_lot_id=lot.id,name=label,floor_number=1)
            db.add(area);db.flush()
        used={s[0] for s in db.query(ParkingSpot.spot_code).filter_by(parking_area_id=area.id)}
        index=1
        for _ in range(needed):
            while f'{prefix}-{index:03}' in used or f'L{lot.id}-{prefix}-{index:03}' in station_codes:index+=1
            code=f'{prefix}-{index:03}';used.add(code);index+=1
            values=dict(parking_area_id=area.id,spot_code=code,spot_type=vt,energy_type=en,status='AVAILABLE')
            if en=='ELECTRIC':
                values.update(charger_type='SOCKET' if vt=='MOTORBIKE' else 'EV_CHARGER',
                    charging_station_code=f'L{lot.id}-{code}',charging_port_code='01',charger_status='PLANNED')
            if en=='ELECTRIC':station_codes.add(values['charging_station_code'])
            db.add(ParkingSpot(**values));created+=1
    db.flush()
    result=capacity_summary(db,lot);result['created_spots']=created
    if commit:db.commit()
    return result
