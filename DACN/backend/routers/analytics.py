from datetime import date, datetime, time, timedelta
from decimal import Decimal
import csv
import io
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func
from database import get_db
from dependencies import get_current_user
from models.operations import ParkingSession, Payment
from models.parking_spot import ParkingSpot
from models.parking_area import ParkingArea
from schemas.operations import RevenueReceipts
from services.parking_service import management
from services.revenue_service import successful_payments, is_sandbox_payment

router=APIRouter(tags=['Analytics'])


def sessions_at_lot(db, lot_id):
    spots = db.query(ParkingSpot.id).join(ParkingArea).filter(ParkingArea.parking_lot_id == lot_id)
    return db.query(ParkingSession).filter(ParkingSession.parking_spot_id.in_(spots))


def date_bounds(start, end):
    return datetime.combine(start, time.min), datetime.combine(end, time.max)


def daily_report(db,lot_id,start,end):
    if end<start or (end-start).days>365: raise HTTPException(422,'Khoảng báo cáo từ 1 đến 366 ngày')
    lower, upper = date_bounds(start, end)
    sessions = sessions_at_lot(db, lot_id)
    rows={ (start+timedelta(days=i)).isoformat():dict(date=(start+timedelta(days=i)).isoformat(),entries=0,exits=0,revenue=Decimal(0),sandbox_revenue=Decimal(0)) for i in range((end-start).days+1)}
    for field,key in [(ParkingSession.entry_time,'entries'),(ParkingSession.exit_time,'exits')]:
        for day,count in sessions.with_entities(func.date(field),func.count(ParkingSession.id)).filter(field.between(lower, upper)).group_by(func.date(field)):
            rows[str(day)][key]=count
    payment_day = func.date(Payment.paid_at)
    sandbox = is_sandbox_payment()
    payments = successful_payments(db, sessions).filter(Payment.paid_at.between(lower, upper))
    for day, is_sandbox, total in payments.with_entities(payment_day, sandbox, func.sum(Payment.amount)).group_by(payment_day, sandbox):
        rows[str(day)]['sandbox_revenue' if is_sandbox else 'revenue'] = total
    items=list(rows.values())
    totals={key:sum(r[key] for r in items) for key in ['entries','exits','revenue','sandbox_revenue']}
    for row in items:
        for key in ['revenue','sandbox_revenue']: row[key]=str(row[key])
    for key in ['revenue','sandbox_revenue']: totals[key]=str(totals[key])
    return dict(parking_lot_id=lot_id,from_date=start,to_date=end,timezone='Asia/Ho_Chi_Minh',items=items,totals=totals)

@router.get('/reports/daily')
def report(parking_lot_id: int=Query(gt=0),from_date: date=Query(),to_date: date=Query(),format: Literal['json','csv']='json',db=Depends(get_db),user=Depends(get_current_user)):
    management(user)
    result=daily_report(db,parking_lot_id,from_date,to_date)
    if format=='json': return result
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['Ngay (Viet Nam)','Xe vao','Xe ra','Doanh thu thuc (VND)','Thanh toan thu nghiem (VND)'])
    for row in result['items']: writer.writerow([row[k] for k in ['date','entries','exits','revenue','sandbox_revenue']])
    return Response(('\ufeff'+output.getvalue()).encode('utf-8'),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="parkly-{from_date}-{to_date}.csv"','Cache-Control':'no-store'})


@router.get('/reports/daily/payments', response_model=RevenueReceipts)
def report_payments(parking_lot_id: int = Query(gt=0), payment_date: date = Query(),
                    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                    db=Depends(get_db), user=Depends(get_current_user)):
    management(user)
    lower, upper = date_bounds(payment_date, payment_date)
    sessions = sessions_at_lot(db, parking_lot_id)
    payments = successful_payments(db, sessions).filter(Payment.paid_at.between(lower, upper))
    rows = (payments.join(ParkingSession).add_entity(ParkingSession).add_columns(is_sandbox_payment())
            .order_by(Payment.paid_at.desc(), Payment.id.desc()).offset(offset).limit(limit + 1).all())
    return {'items': [{'payment': payment, 'session': session, 'sandbox': sandbox}
                      for payment, session, sandbox in rows[:limit]],
            'has_more': len(rows) > limit}
