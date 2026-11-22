"""Internal simulator and VNPAY 2.1 sandbox. No live financial transactions."""
import hashlib
import hmac
import os
from urllib.parse import urlencode
from fastapi import HTTPException
from models.extensions import SandboxOrder
from models.operations import Payment
from services.parking_service import now
from services.session_service import visible_session


def sign_vnpay(params, secret):
    values={k:str(v) for k,v in params.items() if k.startswith('vnp_') and k not in {'vnp_SecureHash','vnp_SecureHashType'} and v is not None and str(v)!=''}
    return hmac.new(secret.encode(),urlencode(sorted(values.items())).encode(),hashlib.sha512).hexdigest()


def checkout_token(order):
    secret=os.getenv('JWT_SECRET_KEY')
    if not secret: raise HTTPException(503,'Chưa cấu hình khóa máy chủ')
    message=f'internal-checkout:{order.id}:{order.amount}:{order.expires_at.isoformat()}'
    return hmac.new(secret.encode(),message.encode(),hashlib.sha256).hexdigest()


def check_checkout(order, token):
    if not order or order.provider!='INTERNAL' or not hmac.compare_digest(checkout_token(order),token or ''):
        raise HTTPException(403,'Liên kết thanh toán thử không hợp lệ')


def finish_order(db, order_id, success, transaction_code):
    initial=db.get(SandboxOrder,order_id)
    if not initial: raise HTTPException(404,'Không tìm thấy giao dịch thử')
    # Cash and callbacks acquire the parking session first, so there is one winner.
    from models.operations import ParkingSession
    session=db.query(ParkingSession).filter_by(id=initial.parking_session_id).populate_existing().with_for_update().first()
    order=db.query(SandboxOrder).filter_by(id=order_id).populate_existing().with_for_update().first()
    if order.status!='PENDING':
        if order.status==('SUCCESS' if success else 'FAILED') and order.transaction_code==transaction_code: return order
        raise HTTPException(409,'Giao dịch đã kết thúc với kết quả khác')
    if order.expires_at<=now():
        order.status='EXPIRED';db.commit()
        raise HTTPException(409,'Giao dịch thử đã hết hạn')
    if session.status!='COMPLETED' or order.amount!=session.total_amount:
        raise HTTPException(409,'Lượt gửi hoặc số tiền đã thay đổi')
    if db.query(Payment.id).filter_by(parking_session_id=session.id,status='SUCCESS').first():
        order.status='CANCELLED';db.commit()
        raise HTTPException(409,'Lượt gửi đã được thanh toán bằng giao dịch khác')
    order.status='SUCCESS' if success else 'FAILED'
    order.transaction_code=transaction_code
    order.completed_at=now()
    if success:
        from services.barrier_service import queue_command
        queue_command(db,session,'EXIT')
        db.add(Payment(parking_session_id=session.id,amount=order.amount,payment_method='VNPAY' if order.provider=='VNPAY' else 'VIETQR',
                       status='SUCCESS',transaction_code=transaction_code,paid_at=now()))
        from services.internal_demo import finalize_departure
        finalize_departure(db,session.id)
    db.commit()
    return order


def order_view(order):
    return dict(id=order.id,parking_session_id=order.parking_session_id,provider=order.provider,amount=str(order.amount),
                status='EXPIRED' if order.status=='PENDING' and order.expires_at<=now() else order.status,
                expires_at=order.expires_at,completed_at=order.completed_at,transaction_code=order.transaction_code,sandbox=True)
