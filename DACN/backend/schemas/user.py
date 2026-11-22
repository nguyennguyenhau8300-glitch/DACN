from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import date, datetime, timedelta, timezone
from schemas.vehicle import VehicleCreate


class ProfileInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    date_of_birth: date | None = None
    hometown: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator('full_name', 'hometown', mode='before')
    @classmethod
    def trim_profile(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('date_of_birth')
    @classmethod
    def valid_birth_date(cls, value):
        today = datetime.now(timezone(timedelta(hours=7))).date()
        if value is not None and value > today:
            raise ValueError('Ngày sinh không được ở tương lai')
        return value


class UserProfileUpdate(ProfileInput):
    date_of_birth: date
    hometown: str = Field(min_length=1, max_length=200)
    model_config = {'extra': 'forbid'}


class PasswordInput(BaseModel):
    @field_validator('password', check_fields=False)
    @classmethod
    def password_bytes(cls, value):
        if len(value.encode('utf-8')) > 72:
            raise ValueError('Mật khẩu tối đa 72 byte UTF-8')
        return value

class UserRegister(PasswordInput, ProfileInput):
    vehicle: VehicleCreate | None = None
    full_name: str = Field(
        min_length=2,
        max_length=100
    )

    email: EmailStr

    password: str = Field(
        min_length=6,
        max_length=72
    )

    phone: str | None = Field(
        default=None,
        max_length=20
    )


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    phone: str | None
    role: str
    is_active: bool
    date_of_birth: date | None = None
    hometown: str | None = None

    model_config = {
        "from_attributes": True
    }

class UserLogin(PasswordInput):
    email: EmailStr
    password: str = Field(
        min_length=6,
        max_length=100
    )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse
