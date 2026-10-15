import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from getpass import getpass
from database import SessionLocal
from models.user import User
from services.auth_service import hash_password
from schemas.user import UserRegister

def main():
    data=UserRegister(full_name=input('Họ tên: '),email=input('Email: '),password=getpass('Mật khẩu: '))
    with SessionLocal() as db:
        if db.query(User).filter_by(email=str(data.email)).first():
            raise SystemExit('Email đã tồn tại; không thay đổi tài khoản')
        db.add(User(full_name=data.full_name,email=str(data.email),password_hash=hash_password(data.password),role='ADMIN'))
        db.commit()
    print('Đã tạo ADMIN')
if __name__=='__main__': main()
