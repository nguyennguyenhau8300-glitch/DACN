"""Virtual relay only. No physical relay/charger/gate is actuated."""
from uuid import uuid4
from models.extensions import BarrierCommand
from models.parking_spot import ParkingSpot
from models.parking_area import ParkingArea
from services.parking_service import now

def queue_command(db,session,direction):
    db.flush()
    if db.query(BarrierCommand.id).filter_by(parking_session_id=session.id,direction=direction).first(): return
    spot=db.get(ParkingSpot,session.parking_spot_id)
    area=db.get(ParkingArea,spot.parking_area_id) if spot else None
    if area: db.add(BarrierCommand(id=uuid4().hex,parking_lot_id=area.parking_lot_id,parking_session_id=session.id,direction=direction,status='QUEUED'))

def advance(db):
    # Committed entry opens a virtual relay. Exit is queued only after payment (or zero fee).
    rows=db.query(BarrierCommand).filter(BarrierCommand.status.in_(['QUEUED','SIMULATED_OPEN'])).order_by(BarrierCommand.id).with_for_update().all()
    for row in rows:
        if row.status=='QUEUED': row.status='SIMULATED_OPEN';row.opened_at=now()
        elif (now()-(row.opened_at or row.created_at)).total_seconds()>=4: row.status='SIMULATED_CLOSED'
    db.commit()
