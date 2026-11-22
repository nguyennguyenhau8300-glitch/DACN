from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from database import get_db
from dependencies import get_current_user
from models.vehicle import Vehicle
from models.parking_lot import ParkingLot
from models.extensions import RoutingMap
from services.parking_service import management
from services.navigation_service import get_map, lot_spots, validate_graph, recommend

router=APIRouter(tags=['Navigation'])

class Node(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    id: str=Field(min_length=1,max_length=60)
    kind: Literal['LANE','ENTRANCE','DESTINATION','SPOT']
    label: str=Field(default='',max_length=100)
    x: float=Field(ge=-10000,le=10000)
    y: float=Field(ge=-10000,le=10000)
    spot_id: int | None=Field(default=None,gt=0)

class Edge(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    source: str
    target: str
    distance: float=Field(gt=0,le=100000)
    directed: bool=False
    blocked: bool=False

class MapInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision: int=Field(ge=0)
    name: str=Field(min_length=1,max_length=120)
    units: Literal['mét','mét mô phỏng']='mét mô phỏng'
    nodes: list[Node]=Field(min_length=2,max_length=1200)
    edges: list[Edge]=Field(max_length=4000)

@router.get('/parking-lots/{lot_id}/map')
def read_map(lot_id: int,db=Depends(get_db),user=Depends(get_current_user)):
    return get_map(db,lot_id)

@router.put('/parking-lots/{lot_id}/map')
def save_map(lot_id: int,data: MapInput,db=Depends(get_db),user=Depends(get_current_user)):
    management(user)
    if not db.query(ParkingLot).filter_by(id=lot_id).with_for_update().first(): raise HTTPException(404,'Không tìm thấy bãi')
    row=db.get(RoutingMap,lot_id)
    if data.revision!=(row.revision if row else 0): raise HTTPException(409,'Sơ đồ đã thay đổi; tải lại trước khi lưu')
    graph=data.model_dump(exclude={'revision'})
    validate_graph(graph,{s.id for s in lot_spots(db,lot_id)})
    if row: row.graph=graph;row.revision+=1
    else: db.add(RoutingMap(parking_lot_id=lot_id,revision=1,graph=graph))
    db.commit()
    return get_map(db,lot_id)

@router.get('/parking-lots/{lot_id}/recommendation')
def suggestion(lot_id: int,vehicle_id: int=Query(gt=0),entrance: str | None=None,destination: str | None=None,
               walk_weight: float=Query(1,ge=0,le=10,allow_inf_nan=False),db=Depends(get_db),user=Depends(get_current_user)):
    vehicle=db.get(Vehicle,vehicle_id)
    if not vehicle: raise HTTPException(404,'Không tìm thấy phương tiện')
    if user.role=='CUSTOMER' and vehicle.user_id!=user.id: raise HTTPException(403,'Chỉ gợi ý cho xe của bạn')
    return recommend(db,lot_id,vehicle,entrance,destination,walk_weight)
