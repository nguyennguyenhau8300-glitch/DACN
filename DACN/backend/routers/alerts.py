from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models.incident import Incident
from services.parking_service import now, staff

router = APIRouter(prefix='/alerts', tags=['Alerts & Incident Journal'])


def view(row):
    return {c.name: getattr(row, c.name) for c in Incident.__table__.columns}


@router.get('')
def list_alerts(parking_lot_id: int | None = Query(None, gt=0),
                status: Literal['ALL', 'OPEN', 'ACKNOWLEDGED', 'RESOLVED'] = 'ALL',
                kind: Literal['ALL', 'OVERHEAT', 'CHARGER_FAULT', 'CONNECTION_LOST', 'WRONG_PARKING'] = 'ALL',
                limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                db: Session = Depends(get_db), user=Depends(get_current_user)):
    staff(user)
    scope = db.query(Incident)
    if parking_lot_id is not None:
        scope = scope.filter_by(parking_lot_id=parking_lot_id)
    open_count = scope.filter(Incident.status != 'RESOLVED').count()
    unacknowledged_count = scope.filter_by(status='OPEN').count()
    query = scope
    if status == 'OPEN':
        query = query.filter(Incident.status != 'RESOLVED')
    elif status != 'ALL':
        query = query.filter_by(status=status)
    if kind != 'ALL':
        query = query.filter_by(kind=kind)
    total = query.count()
    rows = query.order_by(case((Incident.status == 'RESOLVED', 1), else_=0), Incident.opened_at.desc(), Incident.id.desc()).offset(offset).limit(limit).all()
    return {'items': [view(r) for r in rows], 'total': total, 'open_count': open_count,
            'unacknowledged_count': unacknowledged_count}


@router.patch('/{incident_id}/acknowledge')
def acknowledge(incident_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    staff(user)
    row = db.query(Incident).filter_by(id=incident_id).with_for_update().first()
    if row is None:
        raise HTTPException(404, 'Không tìm thấy sự cố')
    if row.status == 'RESOLVED':
        raise HTTPException(409, 'Sự cố đã kết thúc')
    if row.status == 'OPEN':
        row.status = 'ACKNOWLEDGED'
        row.acknowledged_at = now()
        row.acknowledged_by = user.id
    db.commit()
    db.refresh(row)
    return view(row)
