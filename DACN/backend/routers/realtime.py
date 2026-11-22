import asyncio
import os
import time
from fastapi import APIRouter,WebSocket,WebSocketDisconnect,Depends
from database import SessionLocal
from database import get_db
from models.extensions import BarrierCommand
from models.user import User
from dependencies import get_current_user
from services.auth_service import decode_access_token
from services import realtime
from services.http_origins import accepts_websocket_origin
from services.parking_service import management

router=APIRouter(tags=['Realtime'])
HEARTBEAT_SECONDS = 20

def active_user(token):
    claims=decode_access_token(token)
    if not claims: return False
    try: ident=int(claims['sub'])
    except (KeyError,ValueError,TypeError): return False
    with SessionLocal() as db:
        user=db.get(User,ident)
        return bool(user and user.is_active)

@router.websocket('/ws/events')
async def events(socket: WebSocket):
    if not accepts_websocket_origin(socket.headers.get('origin'), socket.headers.get('host')):
        await socket.close(code=1008);return
    await socket.accept()
    try:
        # Token in the first message, never in URL/access logs.
        auth=await asyncio.wait_for(socket.receive_json(),timeout=10)
        token=auth.get('token','') if isinstance(auth,dict) else ''
        if not isinstance(token,str) or len(token)>8192 or not await asyncio.to_thread(active_user,token):
            await socket.close(code=1008);return
        realtime.join(socket)
        await socket.send_json(realtime.notification('ready'))
        checked=time.monotonic()
        while True:
            if time.monotonic()-checked>=10:
                if not await asyncio.to_thread(active_user,token): await socket.close(code=1008);return
                checked=time.monotonic()
            try: await asyncio.wait_for(socket.receive_text(),timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                if not await asyncio.to_thread(active_user,token): await socket.close(code=1008);return
                await socket.send_json(realtime.notification('ping'))
    except (WebSocketDisconnect,asyncio.TimeoutError,ValueError,RuntimeError): pass
    finally: realtime.leave(socket)

@router.get('/integrations/status')
def status(user=Depends(get_current_user)):
    management(user)
    from ai_engine.detector import detector_status
    return {**realtime.integration_status(),'mqtt_enabled':os.getenv('MQTT_ENABLED')=='1',
            'vnpay_sandbox_configured':all(os.getenv(k) for k in ['VNPAY_TMN_CODE','VNPAY_HASH_SECRET','VNPAY_RETURN_URL']),
            'detector':detector_status()}

@router.get('/barriers')
def barriers(parking_lot_id: int,db=Depends(get_db),user=Depends(get_current_user)):
    from services.parking_service import staff
    staff(user)
    rows=db.query(BarrierCommand).filter_by(parking_lot_id=parking_lot_id).order_by(BarrierCommand.created_at.desc()).limit(50)
    return {'mode':'SIMULATION','notice':'Relay ảo: xe vào đã xác nhận; cổng ra mở sau thanh toán hoặc khi miễn phí. Không điều khiển phần cứng.',
            'items':[dict(id=r.id,parking_session_id=r.parking_session_id,direction=r.direction,status=r.status,created_at=r.created_at,opened_at=r.opened_at) for r in rows]}
