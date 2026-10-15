from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from database import Base


class SensorLog(Base):
    __tablename__ = "sensor_logs"

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        index=True
    )

    parking_spot_id = Column(
        Integer,
        ForeignKey(
            "parking_spots.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    sensor_status = Column(
        String(20),
        nullable=False
    )

    recorded_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )