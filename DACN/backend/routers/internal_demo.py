from typing import Literal
from uuid import UUID,uuid4
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import FileResponse
from pydantic import BaseModel,ConfigDict,Field
from database import get_db
from dependencies import get_current_user
from models.internal_demo import InternalDemoRun
from models.operations import ParkingSession
from models.extensions import SandboxOrder
from models.parking_spot import ParkingSpot
from models.parking_area import ParkingArea
from services.parking_service import management,staff
from services import internal_demo as service

router=APIRouter(tags=['Internal operation simulator'])

class SensorInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    parking_spot_id:int=Field(gt=0)
    sensor_status:Literal['AVAILABLE','OCCUPIED']
    request_id:UUID=Field(default_factory=uuid4)

class ChargerInput(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    parking_spot_id:int=Field(gt=0)
    scenario:Literal['READY','PLUGGED','CHARGING','OVERHEAT','FAULT']
    power_kw:float=Field(default=7,gt=0,le=1000)
    request_id:UUID=Field(default_factory=uuid4)

class PresetInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    parking_lot_id:int=Field(gt=0)
    parking_session_id:int|None=Field(default=None,gt=0)
    request_id:UUID=Field(default_factory=uuid4)


def view(db,row):
    from services.payment_gateway import checkout_token,order_view
    session=db.get(ParkingSession,row.parking_session_id) if row.parking_session_id else None
    result={key:getattr(row,key) for key in ['id','kind','status','parking_lot_id','parking_session_id','steps','result','created_at','completed_at']}
    result['session_status']=session.status if session else None
    if row.sandbox_order_id:
        order=db.get(SandboxOrder,row.sandbox_order_id)
        if order:
            token=checkout_token(order)
            result['checkout']={**order_view(order),'qr_url':f'/checkout/internal/{order.id}/qr?token={token}',
                                'checkout_url':f'/checkout/internal/{order.id}?token={token}'}
    return result


@router.get('/ai/samples')
def samples(user=Depends(get_current_user)):
    staff(user)
    return [{**{k:r[k] for k in ['id','label','vehicle_type','energy_type']},'synthetic':True,'image_url':f'/ai/samples/{r["id"]}/image'} for r in service.sample_rows()]


@router.get('/ai/samples/{ident}/image')
def sample_image(ident:str,user=Depends(get_current_user)):
    staff(user);_,path=service.sample(ident)
    return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})


@router.post('/internal-simulation/prepare')
def prepare(db=Depends(get_db),user=Depends(get_current_user)):
    management(user);rows=service.prepare(db,user);db.commit()
    return {'vehicles':[{'id':r.id,'license_plate':r.license_plate,'vehicle_type':r.vehicle_type,'energy_type':r.energy_type} for r in rows],
            'notice':'Đã chuẩn bị bốn xe mẫu. Chưa tạo lượt gửi, chưa ghi nhận tiền.'}


@router.post('/api/v1/iot/simulate-sensor')
def sensor(data:SensorInput,db=Depends(get_db),user=Depends(get_current_user)):
    management(user)
    return view(db,service.signal_run(db,user,data.request_id.hex,data.parking_spot_id,'SENSOR',{'sensor_status':data.sensor_status}))


@router.post('/api/v1/iot/simulate-charger')
def charger(data:ChargerInput,db=Depends(get_db),user=Depends(get_current_user)):
    management(user)
    payload={'charger_status':'FAULT' if data.scenario in ('OVERHEAT','FAULT') else 'CHARGING' if data.scenario=='CHARGING' else 'READY',
             'temperature_c':70 if data.scenario=='OVERHEAT' else 30,'power_kw':data.power_kw if data.scenario=='CHARGING' else 0}
    return view(db,service.signal_run(db,user,data.request_id.hex,data.parking_spot_id,'CHARGER',payload))


@router.get('/internal-simulation/state')
def state(parking_lot_id:int,db=Depends(get_db),user=Depends(get_current_user)):
    from services.simulation_service import site_devices
    management(user);service.active_lot(db,parking_lot_id)
    devices={(d.parking_spot_id,d.kind):d for d in site_devices(db,parking_lot_id)}
    spots=db.query(ParkingSpot).join(ParkingArea).filter(ParkingArea.parking_lot_id==parking_lot_id).order_by(ParkingSpot.id).all()
    runs=db.query(InternalDemoRun).filter_by(parking_lot_id=parking_lot_id).order_by(InternalDemoRun.created_at.desc()).limit(25).all()
    entries=db.query(InternalDemoRun).join(ParkingSession,InternalDemoRun.parking_session_id==ParkingSession.id).filter(
        InternalDemoRun.parking_lot_id==parking_lot_id,InternalDemoRun.kind=='ENTRY',ParkingSession.status=='ACTIVE').all()
    waiting=db.query(InternalDemoRun).filter_by(parking_lot_id=parking_lot_id,kind='EXIT',status='AWAITING_PAYMENT').all()
    return {'parking_lot_id':parking_lot_id,'mode':'INTERNAL','spots':[{
        **{k:getattr(s,k) for k in ['id','spot_code','spot_type','energy_type','status','charger_status']},
        'sensor_payload':devices[(s.id,'SENSOR')].last_payload if (s.id,'SENSOR') in devices else None,
        'charger_payload':devices[(s.id,'CHARGER')].last_payload if (s.id,'CHARGER') in devices else None} for s in spots],
        'runs':[view(db,r) for r in runs],'active_demo_sessions':[r.parking_session_id for r in entries],
        'pending_checkouts':[view(db,r) for r in waiting]}


@router.post('/internal-simulation/presets/entry')
def entry(data:PresetInput,db=Depends(get_db),user=Depends(get_current_user)):
    management(user)
    return view(db,service.entry_run(db,user,data.request_id.hex,data.parking_lot_id))


@router.post('/internal-simulation/presets/exit')
def exit(data:PresetInput,db=Depends(get_db),user=Depends(get_current_user)):
    management(user)
    if not data.parking_session_id:raise HTTPException(422,'Chọn lượt xe mẫu đang gửi')
    return view(db,service.exit_run(db,user,data.request_id.hex,data.parking_lot_id,data.parking_session_id))


@router.post('/internal-simulation/runs/{ident}/confirm-payment')
def confirm(ident:str,db=Depends(get_db),user=Depends(get_current_user)):
    from services.payment_gateway import finish_order
    management(user);run=db.get(InternalDemoRun,ident)
    if not run or run.kind!='EXIT' or not run.sandbox_order_id:raise HTTPException(404,'Không tìm thấy kịch bản thanh toán')
    if run.status=='DONE':return view(db,run)
    finish_order(db,run.sandbox_order_id,True,'SANDBOX-INTERNAL-'+run.sandbox_order_id)
    db.refresh(run);return view(db,run)
