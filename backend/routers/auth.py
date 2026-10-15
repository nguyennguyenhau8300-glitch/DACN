from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.user import User
from models.vehicle import Vehicle
from services.vehicle_service import normalized_plate, plate_expression
from sqlalchemy.exc import IntegrityError

from schemas.user import (
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    UserProfileUpdate,
)

from services.auth_service import (
    create_access_token,
    hash_password,
    verify_password,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


# =========================================================
# ĐĂNG KÝ TÀI KHOẢN
# =========================================================
@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register(
    data: UserRegister,
    db: Session = Depends(get_db)
):
    existing_user = (
        db.query(User)
        .filter(User.email == data.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email đã được sử dụng"
        )

    if data.vehicle and db.query(Vehicle).filter(
        plate_expression(Vehicle.license_plate) == normalized_plate(data.vehicle.license_plate)
    ).first():
        raise HTTPException(409, 'Biển số xe đã được đăng ký; hãy kiểm tra lại hoặc liên hệ nhân viên')

    new_user = User(
        full_name=data.full_name,
        email=data.email,
        password_hash=hash_password(data.password),
        phone=data.phone,
        date_of_birth=data.date_of_birth,
        hometown=data.hometown,
        role="CUSTOMER"
    )

    db.add(new_user)
    try:
        db.flush()
        if data.vehicle:
            db.add(Vehicle(user_id=new_user.id, **data.vehicle.model_dump()))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Email hoặc biển số đã được đăng ký')
    db.refresh(new_user)

    return new_user


# =========================================================
# ĐĂNG NHẬP
# =========================================================
@router.post(
    "/login",
    response_model=TokenResponse
)
def login(
    data: UserLogin,
    db: Session = Depends(get_db)
):
    user = (
        db.query(User)
        .filter(User.email == data.email)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác"
        )

    if not verify_password(
        data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị khóa"
        )

    access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }


# =========================================================
# THÔNG TIN TÀI KHOẢN ĐANG ĐĂNG NHẬP
# =========================================================
@router.get(
    "/me",
    response_model=UserResponse
)
def get_me(
    current_user: User = Depends(get_current_user)
):
    return current_user


@router.patch('/me', response_model=UserResponse)
def update_my_profile(data: UserProfileUpdate, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    for key, value in data.model_dump().items():
        setattr(current_user, key, value)
    db.commit()
    db.refresh(current_user)
    return current_user
