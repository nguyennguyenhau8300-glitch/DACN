from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Boolean, Float, UniqueConstraint
from database import Base
from services.parking_service import now


class SimulationSite(Base):
    __tablename__ = 'simulation_sites'
    parking_lot_id = Column(Integer, ForeignKey('parking_lots.id'), primary_key=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    enabled = Column(Boolean, nullable=False, default=False)
    paused_devices = Column(JSON, nullable=False, default=list)
    desired_states = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=now)


class SimulationAction(Base):
    __tablename__ = 'simulation_actions'
    __table_args__ = (UniqueConstraint('device_id', 'sequence', name='uq_simulation_sequence'),)
    id = Column(String(40), primary_key=True)
    parking_lot_id = Column(Integer, ForeignKey('simulation_sites.parking_lot_id'), nullable=False)
    device_id = Column(Integer, ForeignKey('iot_devices.id'), nullable=False)
    sequence = Column(Integer, nullable=False)
    transport = Column(String(10), nullable=False)
    origin = Column(String(20), nullable=False)
    payload = Column(JSON, nullable=False)
    ack = Column(JSON)
    status = Column(String(20), nullable=False, default='PENDING')
    sent_at = Column(DateTime, nullable=False, default=now)
    completed_at = Column(DateTime)
    elapsed_ms = Column(Float)


class CameraObservation(Base):
    __tablename__ = 'camera_observations'
    id = Column(String(40), primary_key=True)
    parking_lot_id = Column(Integer, ForeignKey('simulation_sites.parking_lot_id'), nullable=False, index=True)
    parking_session_id = Column(Integer, ForeignKey('parking_sessions.id'))
    license_plate = Column(String(20), nullable=False)
    confidence = Column(Float, nullable=False)
    detection_confidence = Column(Float)
    box = Column(JSON, nullable=False)
    frame_id = Column(Integer, nullable=False)
    captured_at = Column(DateTime, nullable=False)
    recorded_at = Column(DateTime, nullable=False, default=now)
    direction = Column(String(10), nullable=False)
    outcome = Column(String(20), nullable=False)
    message = Column(String(250), nullable=False)
    source_kind = Column(String(10), nullable=False, default='RTSP')
