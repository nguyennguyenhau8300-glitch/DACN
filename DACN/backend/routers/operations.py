from services import session_service
from services.session_service import visible_session
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models.operations import ParkingSession, PricingRule, Payment
from models.vehicle import Vehicle
from models.parking_spot import ParkingSpot
from models.parking_lot import ParkingLot
from models.parking_area import ParkingArea
from models.reservation import Reservation
from schemas.operations import CheckIn, CheckOut, SessionResponse, PricingCreate, PricingResponse, PaymentCreate, PaymentResponse
from services.parking_service import now, staff, management, expire_reservations
from services.revenue_service import successful_payments, is_sandbox_payment
router = APIRouter(tags=['Parking Operations'])


@router.get('/pricing-rules', response_model=list[PricingResponse])
def list_prices(parking_lot_id: int | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(PricingRule)
    if parking_lot_id is not None: q = q.filter_by(parking_lot_id=parking_lot_id)
    from models.extensions import TariffSchedule
    rows=q.order_by(PricingRule.id).all()
    schedules={s.pricing_rule_id:s.bands for s in db.query(TariffSchedule).filter(TariffSchedule.pricing_rule_id.in_([r.id for r in rows]))}
    return [{**PricingResponse.model_validate(r).model_dump(),'time_bands':schedules.get(r.id,[])} for r in rows]

@router.post('/pricing-rules', response_model=PricingResponse, status_code=201)
def create_price(data: PricingCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    management(user)
    lot = db.query(ParkingLot).filter_by(id=data.parking_lot_id).with_for_update().first()
    if not lot: raise HTTPException(404, 'Không tìm thấy bãi xe')
    if data.is_active and db.query(PricingRule).filter_by(parking_lot_id=lot.id, vehicle_type=data.vehicle_type, energy_type=data.energy_type, is_active=True).first():
        raise HTTPException(409, 'Đã có bảng giá hoạt động; cập nhật bảng giá hiện tại')
    row = PricingRule(**data.model_dump()); db.add(row); db.commit(); db.refresh(row)
    return row

@router.put('/pricing-rules/{rule_id}', response_model=PricingResponse)
def update_price(rule_id: int, data: PricingCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    management(user)
    lot = db.query(ParkingLot).filter_by(id=data.parking_lot_id).with_for_update().first()
    if not lot: raise HTTPException(404, 'Không tìm thấy bãi xe')
    row = db.query(PricingRule).filter_by(id=rule_id).with_for_update().first()
    if not row: raise HTTPException(404, 'Không tìm thấy bảng giá')
    if row.parking_lot_id != data.parking_lot_id or row.vehicle_type != data.vehicle_type or row.energy_type != data.energy_type:
        raise HTTPException(400, 'Không được đổi bãi hoặc loại xe của bảng giá')
    if db.query(ParkingSession).join(ParkingSpot, ParkingSession.parking_spot_id == ParkingSpot.id).join(
        ParkingArea).join(Vehicle, ParkingSession.vehicle_id == Vehicle.id).filter(
        ParkingSession.status=='ACTIVE', Vehicle.vehicle_type==row.vehicle_type, Vehicle.energy_type==row.energy_type,
        ParkingArea.parking_lot_id==lot.id).first():
        raise HTTPException(409, 'Không thể thay bảng giá khi có xe đang gửi')
    if data.is_active and db.query(PricingRule).filter(PricingRule.id != rule_id, PricingRule.parking_lot_id==lot.id,
        PricingRule.vehicle_type==data.vehicle_type, PricingRule.energy_type==data.energy_type, PricingRule.is_active==True).first():
        raise HTTPException(409, 'Đã có bảng giá hoạt động')
    for k,v in data.model_dump().items(): setattr(row,k,v)
    db.commit(); db.refresh(row); return row

@router.post('/parking-sessions/check-in', response_model=SessionResponse, status_code=201)
def check_in(data: CheckIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return session_service.check_in(data, db, user)

@router.get('/parking-sessions', response_model=list[SessionResponse])
def list_sessions(parking_lot_id: int | None = None, session_status: str | None = None, limit: int = Query(100,ge=1,le=500), offset: int = Query(0,ge=0), db: Session = Depends(get_db), user=Depends(get_current_user)):
    q=db.query(ParkingSession)
    if parking_lot_id is not None:
        q=q.join(ParkingSpot,ParkingSession.parking_spot_id==ParkingSpot.id).join(ParkingArea).filter(ParkingArea.parking_lot_id==parking_lot_id)
    if user.role not in {'ADMIN','MANAGER','SECURITY'}: q=q.join(Vehicle).filter(Vehicle.user_id==user.id)
    if session_status: q=q.filter(ParkingSession.status==session_status.upper())
    return q.order_by(ParkingSession.id.desc()).offset(offset).limit(limit).all()

@router.get('/parking-sessions/{session_id}', response_model=SessionResponse)
def session_detail(session_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return visible_session(db,session_id,user)

@router.post('/parking-sessions/{session_id}/check-out', response_model=SessionResponse)
def check_out(session_id: int, data: CheckOut, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return session_service.check_out(session_id, data, db, user)

@router.post('/payments', response_model=PaymentResponse, status_code=201)
def pay_cash(data: PaymentCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    staff(user)
    session=visible_session(db,data.parking_session_id,user,True)
    if session.status!='COMPLETED': raise HTTPException(409, 'Cần check-out trước khi thu tiền')
    if db.query(Payment).filter_by(parking_session_id=session.id,status='SUCCESS').first():
        raise HTTPException(409, 'Lượt gửi đã thanh toán')
    row=Payment(parking_session_id=session.id,amount=session.total_amount,payment_method='CASH',status='SUCCESS',paid_at=now(),transaction_code='CASH-'+uuid4().hex)
    from services.barrier_service import queue_command
    queue_command(db,session,'EXIT')
    from services.internal_demo import finalize_departure
    finalize_departure(db,session.id)
    db.add(row); db.commit(); db.refresh(row); return row

@router.get('/payments', response_model=list[PaymentResponse])
def payments(parking_lot_id: int | None=None, parking_session_id: int | None=Query(None,gt=0), limit: int=Query(100,ge=1,le=500), offset: int=Query(0,ge=0), db: Session=Depends(get_db), user=Depends(get_current_user)):
    q=db.query(Payment)
    if parking_session_id is not None:
        q=q.filter(Payment.parking_session_id==parking_session_id)
    if parking_lot_id is not None:
        spot_ids=db.query(ParkingSpot.id).join(ParkingArea).filter(ParkingArea.parking_lot_id==parking_lot_id)
        session_ids=db.query(ParkingSession.id).filter(ParkingSession.parking_spot_id.in_(spot_ids))
        q=q.filter(Payment.parking_session_id.in_(session_ids))
    if user.role not in {'ADMIN','MANAGER','SECURITY'}:
        q=q.join(ParkingSession).join(Vehicle).filter(Vehicle.user_id==user.id)
    return q.order_by(Payment.id.desc()).offset(offset).limit(limit).all()

@router.get('/payments/{payment_id}', response_model=PaymentResponse)
def payment_detail(payment_id: int, db: Session=Depends(get_db), user=Depends(get_current_user)):
    row=db.get(Payment,payment_id)
    if not row: raise HTTPException(404,'Không tìm thấy thanh toán')
    visible_session(db,row.parking_session_id,user)
    return row

@router.post('/reservations/expire')
def expire(db: Session=Depends(get_db), user=Depends(get_current_user)):
    management(user); return {'expired':expire_reservations(db)}

@router.get('/reports/summary')
def report(parking_lot_id: int | None=None,db: Session=Depends(get_db),user=Depends(get_current_user)):
    from sqlalchemy import func
    management(user)
    spots=db.query(ParkingSpot)
    sessions=db.query(ParkingSession)
    if parking_lot_id is not None:
        spot_ids=db.query(ParkingSpot.id).join(ParkingArea).filter(ParkingArea.parking_lot_id==parking_lot_id)
        spots=spots.filter(ParkingSpot.id.in_(spot_ids))
        sessions=sessions.filter(ParkingSession.parking_spot_id.in_(spot_ids))
    payments=successful_payments(db, sessions).filter(~is_sandbox_payment())
    return {'spots':{state:spots.filter(ParkingSpot.status==state).count() for state in ['AVAILABLE','RESERVED','OCCUPIED','MAINTENANCE']},
            'active_sessions':sessions.filter(ParkingSession.status=='ACTIVE').count(),
            'completed_sessions':sessions.filter(ParkingSession.status=='COMPLETED').count(),
            'revenue':str(payments.with_entities(func.coalesce(func.sum(Payment.amount),0)).scalar())}


from pydantic import BaseModel
from typing import Literal
from schemas.user import UserResponse
from models.user import User

class UserAccessUpdate(BaseModel):
    role: Literal['ADMIN','MANAGER','SECURITY','CUSTOMER']
    is_active: bool

@router.get('/users', response_model=list[UserResponse])
def users(limit: int=Query(100,ge=1,le=500),offset: int=Query(0,ge=0),db: Session=Depends(get_db),user=Depends(get_current_user)):
    if user.role!='ADMIN': raise HTTPException(403,'Chỉ ADMIN được quản lý tài khoản')
    return db.query(User).order_by(User.id).offset(offset).limit(limit).all()

@router.patch('/users/{user_id}/access', response_model=UserResponse)
def update_access(user_id: int,data: UserAccessUpdate,db: Session=Depends(get_db),user=Depends(get_current_user)):
    if user.role!='ADMIN': raise HTTPException(403,'Chỉ ADMIN được quản lý tài khoản')
    db.query(User).filter_by(role='ADMIN').order_by(User.id).populate_existing().with_for_update().all()
    actor=db.query(User).filter_by(id=user.id).populate_existing().first()
    if not actor or actor.role!='ADMIN' or not actor.is_active:
        raise HTTPException(403,'Quyền ADMIN đã thay đổi')
    row=db.query(User).filter_by(id=user_id).populate_existing().with_for_update().first()
    if not row: raise HTTPException(404,'Không tìm thấy tài khoản')
    if user_id==user.id and (data.role!='ADMIN' or not data.is_active):
        raise HTTPException(409,'Không thể tự khóa hoặc hạ quyền ADMIN')
    row.role=data.role;row.is_active=data.is_active;db.commit();db.refresh(row);return row
