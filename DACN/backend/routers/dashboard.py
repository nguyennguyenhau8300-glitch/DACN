from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models.vehicle import Vehicle
from models.reservation import Reservation
from models.parking_spot import ParkingSpot
from models.parking_area import ParkingArea
from schemas.vehicle import VehicleResponse
from schemas.reservation import ReservationResponse
from services.parking_service import staff
from services.reservation_policy import reservation_views

router=APIRouter(prefix='/dashboard-data',tags=['Dashboard'])

@router.get('/vehicles',response_model=list[VehicleResponse])
def operator_vehicles(db: Session=Depends(get_db),user=Depends(get_current_user)):
    staff(user)
    return db.query(Vehicle).order_by(Vehicle.id.desc()).all()

@router.get('/reservations',response_model=list[ReservationResponse])
def operator_reservations(parking_lot_id: int | None=None,db: Session=Depends(get_db),user=Depends(get_current_user)):
    staff(user)
    query=db.query(Reservation)
    if parking_lot_id is not None:
        query=query.join(ParkingSpot).join(ParkingArea).filter(ParkingArea.parking_lot_id==parking_lot_id)
    return reservation_views(query.order_by(Reservation.created_at.desc()))


from fastapi import HTTPException
from pydantic import EmailStr, ConfigDict
from models.user import User
from schemas.vehicle import VehicleCreate
from services.vehicle_service import normalized_plate, plate_expression

class CustomerVehicleCreate(VehicleCreate):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    customer_email: EmailStr | None = None

@router.post('/vehicles',response_model=VehicleResponse,status_code=201)
def register_customer_vehicle(data: CustomerVehicleCreate,db: Session=Depends(get_db),user=Depends(get_current_user)):
    staff(user)
    owner=None
    if data.customer_email is not None:
        owner=db.query(User).filter(User.email==str(data.customer_email),User.role=='CUSTOMER',User.is_active==True).first()
        if not owner:
            raise HTTPException(404,'Không tìm thấy tài khoản khách hàng đang hoạt động với email này')
    if db.query(Vehicle.id).filter(plate_expression(Vehicle.license_plate)==normalized_plate(data.license_plate)).first():
        raise HTTPException(409,'Biển số đã tồn tại; hãy chọn xe đã đăng ký, không đăng ký lại hoặc đổi chủ xe')
    row=Vehicle(**data.model_dump(exclude={'customer_email'}),user_id=owner.id if owner else None)
    db.add(row);db.commit();db.refresh(row)
    return row
