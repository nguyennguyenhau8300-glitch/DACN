from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, JSON, String, text
from database import Base


class Incident(Base):
    __tablename__ = 'incidents'
    __table_args__ = (
        Index('uq_incident_open_device_kind', 'device_id', 'kind', unique=True,
              postgresql_where=text("status != 'RESOLVED'"), sqlite_where=text("status != 'RESOLVED'")),
        Index('ix_incident_lot_time', 'parking_lot_id', 'opened_at'),
    )
    id = Column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True)
    device_id = Column(Integer, ForeignKey('iot_devices.id', ondelete='SET NULL'))
    parking_lot_id = Column(Integer, ForeignKey('parking_lots.id', ondelete='CASCADE'), nullable=False)
    parking_spot_id = Column(Integer, ForeignKey('parking_spots.id', ondelete='SET NULL'))
    device_code = Column(String(100), nullable=False)
    spot_code = Column(String(30), nullable=False)
    kind = Column(String(30), nullable=False)
    severity = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default='OPEN')
    message = Column(String(500), nullable=False)
    details = Column(JSON, nullable=False)
    opened_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    acknowledged_at = Column(DateTime)
    acknowledged_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    resolved_at = Column(DateTime)
    resolution = Column(String(300))
