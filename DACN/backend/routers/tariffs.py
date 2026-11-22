from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
from fastapi import APIRouter, Depends, HTTPException
from database import get_db
from dependencies import get_current_user
from models.extensions import TariffSchedule
from models.operations import PricingRule,ParkingSession
from models.vehicle import Vehicle
from models.parking_spot import ParkingSpot
from models.parking_area import ParkingArea
from models.parking_lot import ParkingLot
from services.parking_service import management

router=APIRouter(tags=['Time Band Pricing'])

class Band(BaseModel):
    model_config=ConfigDict(extra='forbid')
    start_minute: int=Field(ge=0,lt=1440)
    end_minute: int=Field(gt=0,le=1440)
    hourly_price: Decimal=Field(ge=0,max_digits=12,decimal_places=2)

class BandsInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    bands: list[Band]=Field(max_length=24)

@router.get('/pricing-rules/{rule_id}/schedule')
def get_schedule(rule_id: int,db=Depends(get_db),user=Depends(get_current_user)):
    if not db.get(PricingRule,rule_id): raise HTTPException(404,'Không tìm thấy bảng giá')
    row=db.get(TariffSchedule,rule_id)
    return {'pricing_rule_id':rule_id,'bands':row.bands if row else [],'policy':'Mỗi giờ bắt đầu tính theo mức giá tại thời điểm bắt đầu giờ đó. Có lịch thì thay giá giờ đầu/giờ tiếp theo.'}

@router.put('/pricing-rules/{rule_id}/schedule')
def save_schedule(rule_id: int,data: BandsInput,db=Depends(get_db),user=Depends(get_current_user)):
    management(user)
    initial=db.get(PricingRule,rule_id)
    if not initial: raise HTTPException(404,'Không tìm thấy bảng giá')
    db.query(ParkingLot).filter_by(id=initial.parking_lot_id).with_for_update().first()
    rule=db.query(PricingRule).filter_by(id=rule_id).populate_existing().with_for_update().first()
    active=db.query(ParkingSession.id).join(Vehicle).join(ParkingSpot,ParkingSession.parking_spot_id==ParkingSpot.id).join(ParkingArea).filter(
        ParkingSession.status=='ACTIVE',ParkingArea.parking_lot_id==rule.parking_lot_id,Vehicle.vehicle_type==rule.vehicle_type,Vehicle.energy_type==rule.energy_type).first()
    if active: raise HTTPException(409,'Còn xe đang gửi trong nhóm; không đổi lịch tính phí')
    bands=sorted(data.bands,key=lambda b:b.start_minute)
    if bands:
        end=0
        for b in bands:
            if b.start_minute!=end or b.end_minute<=b.start_minute: raise HTTPException(422,'Các khung giờ phải liên tiếp, không chồng lấn và phủ đủ 00:00–24:00')
            end=b.end_minute
        if end!=1440: raise HTTPException(422,'Lịch giá phải phủ đủ 24 giờ')
    row=db.get(TariffSchedule,rule_id)
    values=[b.model_dump(mode='json') for b in bands]
    if row: row.bands=values
    else: db.add(TariffSchedule(pricing_rule_id=rule_id,bands=values))
    db.commit()
    return get_schedule(rule_id,db,user)
