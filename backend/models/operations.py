from sqlalchemy import Column, Integer, String, DateTime, Numeric, Boolean, ForeignKey, Text
from sqlalchemy.sql import func
from database import Base

class ParkingSession(Base):
    __tablename__ = 'parking_sessions'
    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey('vehicles.id'), nullable=False)
    parking_spot_id = Column(Integer, ForeignKey('parking_spots.id', ondelete='SET NULL'))
    reservation_id = Column(Integer, ForeignKey('reservations.id', ondelete='SET NULL'))
    entry_time = Column(DateTime, nullable=False, server_default=func.now())
    exit_time = Column(DateTime)
    entry_plate_image = Column(Text)
    exit_plate_image = Column(Text)
    entry_plate_confidence = Column(Numeric(5,4))
    exit_plate_confidence = Column(Numeric(5,4))
    status = Column(String(20), nullable=False, default='ACTIVE')
    total_amount = Column(Numeric(12,2), nullable=False, default=0)

class PricingRule(Base):
    __tablename__ = 'pricing_rules'
    id = Column(Integer, primary_key=True)
    parking_lot_id = Column(Integer, ForeignKey('parking_lots.id', ondelete='CASCADE'), nullable=False)
    vehicle_type = Column(String(20), nullable=False)
    energy_type = Column(String(20), nullable=False, default='GASOLINE', server_default='GASOLINE')
    first_hour_price = Column(Numeric(12,2), nullable=False)
    additional_hour_price = Column(Numeric(12,2), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

class Payment(Base):
    __tablename__ = 'payments'
    id = Column(Integer, primary_key=True)
    parking_session_id = Column(Integer, ForeignKey('parking_sessions.id'), nullable=False)
    amount = Column(Numeric(12,2), nullable=False)
    payment_method = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default='PENDING')
    transaction_code = Column(String(100))
    paid_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
