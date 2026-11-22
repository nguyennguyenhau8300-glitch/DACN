from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from typing import Literal
from uuid import uuid4
import hmac
import os
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from database import get_db
from dependencies import get_current_user
from models.extensions import SandboxOrder
from models.operations import Payment
from services.session_service import visible_session
from services.parking_service import now
from services.payment_gateway import checkout_token,check_checkout,finish_order,order_view,sign_vnpay

router=APIRouter(tags=['Sandbox Checkout'])

class CheckoutInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    parking_session_id: int=Field(gt=0)
    provider: Literal['INTERNAL','VNPAY']='INTERNAL'

@router.post('/checkout/orders',status_code=201)
def create_order(data: CheckoutInput,request: Request,db=Depends(get_db),user=Depends(get_current_user)):
    session=visible_session(db,data.parking_session_id,user,True)
    if session.status!='COMPLETED': raise HTTPException(409,'Trả xe trước khi thanh toán')
    if db.query(Payment.id).filter_by(parking_session_id=session.id,status='SUCCESS').first(): raise HTTPException(409,'Lượt gửi đã thanh toán')
    secret=os.getenv('VNPAY_HASH_SECRET','')
    tmn=os.getenv('VNPAY_TMN_CODE','')
    returned=os.getenv('VNPAY_RETURN_URL','')
    if data.provider=='VNPAY' and not (secret and tmn and returned): raise HTTPException(503,'Chưa cấu hình tài khoản VNPAY sandbox; dùng mô phỏng nội bộ')
    if session.total_amount!=session.total_amount.to_integral_value(): raise HTTPException(409,'Thanh toán QR yêu cầu số tiền nguyên VND')
    order=db.query(SandboxOrder).filter_by(parking_session_id=session.id,provider=data.provider,status='PENDING').filter(SandboxOrder.expires_at>now()).order_by(SandboxOrder.created_at.desc()).first()
    if not order:
        order=SandboxOrder(id=uuid4().hex,parking_session_id=session.id,provider=data.provider,amount=session.total_amount,expires_at=now()+timedelta(minutes=15))
        db.add(order);db.flush()
    base=os.getenv('PUBLIC_BASE_URL',str(request.base_url).rstrip('/'))
    if data.provider=='INTERNAL':
        url=f'{base}/checkout/internal/{order.id}?token={checkout_token(order)}'
    else:
        params={'vnp_Version':'2.1.0','vnp_Command':'pay','vnp_TmnCode':tmn,'vnp_Amount':int(order.amount*100),'vnp_CurrCode':'VND',
                'vnp_TxnRef':order.id,'vnp_OrderInfo':f'Parkly sandbox {order.id}','vnp_OrderType':'other','vnp_Locale':'vn',
                'vnp_ReturnUrl':returned,'vnp_IpAddr':request.client.host if request.client else '127.0.0.1',
                'vnp_CreateDate':order.created_at.strftime('%Y%m%d%H%M%S'),'vnp_ExpireDate':order.expires_at.strftime('%Y%m%d%H%M%S')}
        params['vnp_SecureHash']=sign_vnpay(params,secret)
        url='https://sandbox.vnpayment.vn/paymentv2/vpcpay.html?'+urlencode(sorted(params.items()))
    result={**order_view(order),'checkout_url':url,'qr_url':f'{base}/checkout/internal/{order.id}/qr?token={checkout_token(order)}' if data.provider=='INTERNAL' else None}
    db.commit()
    return result

@router.get('/checkout/orders/{order_id}')
def get_order(order_id: str,db=Depends(get_db),user=Depends(get_current_user)):
    order=db.get(SandboxOrder,order_id)
    if not order: raise HTTPException(404,'Không tìm thấy giao dịch')
    visible_session(db,order.parking_session_id,user)
    return order_view(order)

def page(order,token,done=False):
    # IDs/signatures are generated server-side; no untrusted HTML is interpolated.
    value=f'{order.amount:,.0f}'.replace(',','.')
    controls='' if done or order.status!='PENDING' or order.expires_at<=now() else f'<form method="post"><input type="hidden" name="token" value="{token}"><button name="result" value="success">Mô phỏng thành công</button><button name="result" value="failed">Mô phỏng thất bại</button></form>'
    return HTMLResponse(f'<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Parkly · Thanh toán thử</title><style>body{{font:18px system-ui;background:#f3f7f2;color:#155b49;margin:5vh auto;padding:24px;max-width:520px}}main{{background:white;border-radius:24px;padding:28px}}button{{padding:16px;margin:8px;border:0;border-radius:10px;cursor:pointer;background:#155b49;color:white}}small{{overflow-wrap:anywhere}}</style><main><h1>parkly</h1><h2>Thanh toán mô phỏng nội bộ</h2><p>Không chuyển tiền. Không nhập thông tin ngân hàng.</p><h2>{value} VND</h2><p>Trạng thái: {order.status}</p><small>Mã thử: {order.id}</small>{controls}<p><a href="/dashboard/#payments">Về Parkly</a></p></main></html>',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"})

@router.get('/checkout/internal/{order_id}',response_class=HTMLResponse)
def internal_page(order_id: str,token: str,db=Depends(get_db)):
    order=db.get(SandboxOrder,order_id);check_checkout(order,token)
    return page(order,token)

@router.post('/checkout/internal/{order_id}',response_class=HTMLResponse)
def internal_finish(order_id: str,token: str=Form(),result: Literal['success','failed']=Form(),db=Depends(get_db)):
    order=db.get(SandboxOrder,order_id);check_checkout(order,token)
    order=finish_order(db,order_id,result=='success','SANDBOX-INTERNAL-'+order_id)
    return page(order,token,True)

@router.get('/checkout/internal/{order_id}/qr')
def internal_qr(order_id: str,token: str,request: Request,db=Depends(get_db)):
    order=db.get(SandboxOrder,order_id);check_checkout(order,token)
    import qrcode
    url=f"{os.getenv('PUBLIC_BASE_URL',str(request.base_url).rstrip('/'))}/checkout/internal/{order_id}?token={token}"
    image=qrcode.make(url);out=BytesIO();image.save(out,format='PNG')
    return Response(out.getvalue(),media_type='image/png',headers={'Cache-Control':'no-store'})

def verified_params(request):
    pairs=list(request.query_params.multi_items())
    if len({k for k,v in pairs})!=len(pairs): raise HTTPException(400,'Tham số callback bị lặp')
    params=dict(pairs);secret=os.getenv('VNPAY_HASH_SECRET','')
    if not secret or not hmac.compare_digest(sign_vnpay(params,secret),params.get('vnp_SecureHash','')): raise HTTPException(400,'Chữ ký VNPAY không hợp lệ')
    if params.get('vnp_TmnCode')!=os.getenv('VNPAY_TMN_CODE'): raise HTTPException(400,'Sai mã website VNPAY')
    return params

@router.get('/checkout/vnpay/ipn')
def vnpay_ipn(request: Request,db=Depends(get_db)):
    try: params=verified_params(request)
    except HTTPException: return {'RspCode':'97','Message':'Invalid signature'}
    order=db.get(SandboxOrder,params.get('vnp_TxnRef',''))
    if not order or order.provider!='VNPAY': return {'RspCode':'01','Message':'Order not found'}
    if not params.get('vnp_Amount','').isdigit() or Decimal(params['vnp_Amount'])!=order.amount*100: return {'RspCode':'04','Message':'Invalid amount'}
    success=params.get('vnp_ResponseCode')=='00' and params.get('vnp_TransactionStatus')=='00'
    transaction=params.get('vnp_TransactionNo','')
    if success and (not transaction.isdigit() or int(transaction)==0): return {'RspCode':'99','Message':'Invalid transaction'}
    code='SANDBOX-VNPAY-'+(transaction if success else 'FAILED-'+order.id)
    try:
        finish_order(db,order.id,success,code)
        return {'RspCode':'00','Message':'Confirm success'}
    except HTTPException as exc:
        return {'RspCode':'02' if exc.status_code==409 else '99','Message':'Order already settled or expired'}

@router.get('/checkout/vnpay/return')
def vnpay_return(request: Request,db=Depends(get_db)):
    params=verified_params(request)
    # Browser return never credits a payment: only verified IPN can do that.
    return {'sandbox':True,'notice':'Đã nhận kết quả chuyển hướng; kiểm tra trạng thái giao dịch trong Parkly. Chỉ IPN đã xác minh mới ghi nhận thanh toán.','order_id':params.get('vnp_TxnRef')}
