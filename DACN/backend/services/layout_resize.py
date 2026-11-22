"""Shrink a layout without deleting any spot with operational/history references."""
from fastapi import HTTPException
from sqlalchemy import text
from models.parking_lot import ParkingLot
from models.parking_area import ParkingArea
from models.parking_spot import ParkingSpot
from models.extensions import RoutingMap
from services.layout_service import CAPACITY_FIELDS, quotas, capacity_summary


def plan_resize(db, lot_id, config):
    limits = quotas(config)
    lot = db.query(ParkingLot).filter_by(id=lot_id).populate_existing().with_for_update().first()
    if lot is None:
        raise HTTPException(404, 'Không tìm thấy bãi xe')
    # Lock before checking references: concurrent bookings/check-ins must finish first.
    spots = db.query(ParkingSpot).filter(ParkingSpot.parking_area_id.in_(
        db.query(ParkingArea.id).filter_by(parking_lot_id=lot_id)
    )).order_by(ParkingSpot.id).populate_existing().with_for_update().all()
    protected = set()
    for table in ('parking_sessions', 'reservations', 'iot_devices', 'sensor_logs', 'incidents'):
        protected.update(db.execute(text(f'SELECT DISTINCT parking_spot_id FROM {table} '
                                        'WHERE parking_spot_id IS NOT NULL')).scalars())
    saved_map = db.query(RoutingMap).filter_by(parking_lot_id=lot_id).with_for_update().first()
    if saved_map:
        protected.update(n['spot_id'] for n in saved_map.graph['nodes'] if n.get('spot_id') is not None)
    remove = []
    for key, limit in limits.items():
        group = [s for s in spots if ('CAR' if s.spot_type == 'DISABLED' else s.spot_type, s.energy_type) == key]
        excess = max(0, len(group) - limit)
        candidates = [s for s in reversed(group) if s.status == 'AVAILABLE' and s.id not in protected]
        if excess > len(candidates):
            raise HTTPException(409, f'Không đủ ô trống chưa có lịch sử để giảm nhóm {key}; dữ liệu được giữ nguyên')
        remove.extend(candidates[:excess])
    return lot, remove


def apply_resize(db, lot, remove, config):
    for spot in remove:
        db.delete(spot)
    for field in CAPACITY_FIELDS:
        setattr(lot, field, getattr(config, field))
    db.flush()
    return capacity_summary(db, lot)
