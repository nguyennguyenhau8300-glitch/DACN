from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class DeviceCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    device_code: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    parking_spot_id: int = Field(gt=0)
    kind: Literal['SENSOR','CHARGER']
    offline_after_seconds: int = Field(default=90, ge=10, le=3600)

class DeviceAccess(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool

class Telemetry(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    sequence: int = Field(gt=0, le=9223372036854775807, strict=True)
    sensor_status: Literal['AVAILABLE','OCCUPIED'] | None = None
    charger_status: Literal['READY','CHARGING','FAULT','OFFLINE'] | None = None
    power_kw: float | None = Field(default=None, ge=0, le=1000)
    energy_kwh: float | None = Field(default=None, ge=0, le=1_000_000_000)
    temperature_c: float | None = Field(default=None, ge=-50, le=200)
    observed_vehicle_type: Literal['CAR','MOTORBIKE'] | None = None
    observed_energy_type: Literal['GASOLINE','ELECTRIC'] | None = None

    @model_validator(mode='after')
    def consistent_payload(self):
        if (self.sensor_status is None) == (self.charger_status is None):
            raise ValueError('Cần đúng một loại dữ liệu: cảm biến hoặc điểm sạc')
        if self.sensor_status is not None and (self.power_kw is not None or self.energy_kwh is not None or self.temperature_c is not None):
            raise ValueError('Cảm biến ô đỗ không gửi số đo điện')
        observed = self.observed_vehicle_type is not None or self.observed_energy_type is not None
        if observed and (self.sensor_status != 'OCCUPIED' or self.observed_vehicle_type is None or self.observed_energy_type is None):
            raise ValueError('Thông tin xe quan sát cần đủ loại xe và năng lượng, chỉ gửi khi cảm biến báo OCCUPIED')
        if self.charger_status != 'CHARGING' and self.power_kw not in (None, 0):
            raise ValueError('Chỉ trạng thái CHARGING mới có công suất lớn hơn 0')
        return self
