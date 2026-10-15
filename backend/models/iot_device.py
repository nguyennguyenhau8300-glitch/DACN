from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from database import Base

class IotDevice(Base):
    __tablename__ = 'iot_devices'
    __table_args__ = (
        UniqueConstraint('parking_spot_id', 'kind', name='uq_iot_spot_kind'),
        CheckConstraint("kind IN ('SENSOR','CHARGER')", name='iot_device_kind_check'),
        CheckConstraint('offline_after_seconds BETWEEN 10 AND 3600', name='iot_timeout_check'),
    )
    id = Column(Integer, primary_key=True)
    device_code = Column(String(100), nullable=False, unique=True)
    parking_spot_id = Column(Integer, ForeignKey('parking_spots.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = Column(String(20), nullable=False)
    key_hash = Column(String(64), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    offline_after_seconds = Column(Integer, nullable=False, default=90)
    last_seen_at = Column(DateTime)
    last_telemetry_at = Column(DateTime)
    last_sequence = Column(BigInteger, nullable=False, default=0)
    last_payload = Column(JSON)

class IotEvent(Base):
    __tablename__ = 'iot_events'
    __table_args__ = (UniqueConstraint('device_id', 'sequence', name='uq_iot_event_sequence'),)
    id = Column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True)
    device_id = Column(Integer, ForeignKey('iot_devices.id', ondelete='CASCADE'), nullable=False, index=True)
    sequence = Column(BigInteger, nullable=False)
    payload = Column(JSON, nullable=False)
    result = Column(JSON, nullable=False)
    received_at = Column(DateTime, nullable=False)
