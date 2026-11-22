from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, JSON
from database import Base
from services.parking_service import now


class RoutingMap(Base):
    __tablename__ = 'routing_maps'
    parking_lot_id = Column(Integer, ForeignKey('parking_lots.id', ondelete='CASCADE'), primary_key=True)
    revision = Column(Integer, nullable=False, default=1)
    graph = Column(JSON, nullable=False)


class SandboxOrder(Base):
    __tablename__ = 'sandbox_orders'
    id = Column(String(40), primary_key=True)
    parking_session_id = Column(Integer, ForeignKey('parking_sessions.id'), nullable=False, index=True)
    provider = Column(String(20), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String(20), nullable=False, default='PENDING')
    created_at = Column(DateTime, nullable=False, default=now)
    expires_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)
    transaction_code = Column(String(100), unique=True)


class TariffSchedule(Base):
    __tablename__ = 'tariff_schedules'
    pricing_rule_id = Column(Integer, ForeignKey('pricing_rules.id', ondelete='CASCADE'), primary_key=True)
    bands = Column(JSON, nullable=False)


class BarrierCommand(Base):
    __tablename__ = 'barrier_commands'
    id = Column(String(40), primary_key=True)
    parking_lot_id = Column(Integer, ForeignKey('parking_lots.id'), nullable=False, index=True)
    parking_session_id = Column(Integer, ForeignKey('parking_sessions.id'), nullable=False)
    direction = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False, default='SIMULATED')
    created_at = Column(DateTime, nullable=False, default=now)
    opened_at = Column(DateTime)

