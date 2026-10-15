from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint
)
from sqlalchemy.sql import func

from database import Base


class ParkingSpot(Base):
    __tablename__ = "parking_spots"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    parking_area_id = Column(
        Integer,
        ForeignKey(
            "parking_areas.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    spot_code = Column(
        String(30),
        nullable=False
    )

    spot_type = Column(
        String(20),
        nullable=False,
        default="CAR"
    )

    status = Column(
        String(20),
        nullable=False,
        default="AVAILABLE"
    )

    position_x = Column(
        Numeric(10, 2),
        nullable=True
    )

    position_y = Column(
        Numeric(10, 2),
        nullable=True
    )

    sensor_code = Column(
        String(100),
        nullable=True
    )

    energy_type = Column(String(20), nullable=False, default='GASOLINE', server_default='GASOLINE')
    charger_type = Column(String(20), nullable=False, default='NONE', server_default='NONE')
    charging_station_code = Column(String(100))
    charging_port_code = Column(String(30))
    charging_power_kw = Column(Numeric(8,2))
    charger_status = Column(String(20), nullable=False, default='NOT_APPLICABLE', server_default='NOT_APPLICABLE')

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "parking_area_id",
            "spot_code",
            name="parking_spots_parking_area_id_spot_code_key"
        ),
    )