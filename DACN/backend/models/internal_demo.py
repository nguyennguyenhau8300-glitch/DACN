from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON
from database import Base
from services.parking_service import now


class InternalDemoRun(Base):
    __tablename__='internal_demo_runs'
    id=Column(String(40),primary_key=True)
    parking_lot_id=Column(Integer,ForeignKey('parking_lots.id'),nullable=False,index=True)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    kind=Column(String(20),nullable=False)
    status=Column(String(30),nullable=False)
    parking_session_id=Column(Integer,ForeignKey('parking_sessions.id'))
    sandbox_order_id=Column(String(40),ForeignKey('sandbox_orders.id'))
    request_spec=Column(JSON,nullable=False)
    steps=Column(JSON,nullable=False,default=list)
    result=Column(JSON,nullable=False,default=dict)
    created_at=Column(DateTime,nullable=False,default=now)
    completed_at=Column(DateTime)
