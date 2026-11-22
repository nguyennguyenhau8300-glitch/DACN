"""One bounded live RTSP pipeline, authenticated preview and durable cropped evidence."""
import base64
from datetime import datetime
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from uuid import uuid4
from fastapi import HTTPException
from database import SessionLocal, engine
from models.simulation import CameraObservation
from models.operations import ParkingSession
from models.parking_spot import ParkingSpot
from models.parking_area import ParkingArea
from models.vehicle import Vehicle
from models.user import User
from services.parking_service import now
from services.simulation_service import ROOT, require_site

_controller=None
_guard=threading.RLock()


def evidence_path(ident):
    return Path(os.getenv('CAMERA_EVIDENCE_DIR',str(ROOT/'backend/storage/camera_crops')))/f'{ident}.jpg'


def record_evidence(db,lot_id,actor_id,result,jpeg,frame_id,captured_at,mode):
    from ai_engine.recognizer import read_image
    from schemas.operations import CheckIn, CheckOut
    from services.session_service import check_in, check_out
    from services.vehicle_service import normalized_plate
    require_site(db,lot_id)
    user=db.get(User,actor_id)
    if not user or not user.is_active or user.role not in ('ADMIN','MANAGER','SECURITY'):
        raise HTTPException(403,'Tài khoản vận hành không còn quyền')
    plate=result.get('plate')
    if not plate or result.get('needs_review'):raise HTTPException(422,'Chưa có biển số đủ tin cậy')
    detections=result.get('detections') or []
    box=detections[0]['box'] if len(detections)==1 else result['candidates'][0]['box']
    image=read_image(jpeg);x1,y1,x2,y2=[int(v) for v in box]
    x1,y1,x2,y2=max(0,x1),max(0,y1),min(image.width,x2),min(image.height,y2)
    if x2<=x1 or y2<=y1:raise HTTPException(422,'Khung biển số không hợp lệ')
    ident=uuid4().hex;path=evidence_path(ident);path.parent.mkdir(parents=True,exist_ok=True)
    image.crop((x1,y1,x2,y2)).save(path,format='JPEG',quality=90)
    values=dict(id=ident,parking_lot_id=lot_id,license_plate=plate,confidence=float(result['confidence']),
        detection_confidence=detections[0]['confidence'] if len(detections)==1 else None,
        box=[x1,y1,x2,y2],frame_id=frame_id,captured_at=captured_at,recorded_at=now(),direction=mode,
        outcome='DETECTED',message='Đã lưu crop từ khung RTSP mô phỏng',source_kind='RTSP')
    try:
        if mode!='PREVIEW':
            # Only vehicles provisioned for this isolated demonstration may be transacted.
            site=require_site(db,lot_id)
            allowed=json.loads((ROOT/'backend/ai_engine/assets/camera-demo.json').read_text())['plates']
            vehicle=db.query(Vehicle).filter(Vehicle.license_plate.in_(allowed),Vehicle.user_id==site.created_by).all()
            vehicle=next((v for v in vehicle if normalized_plate(v.license_plate)==plate),None)
            if not vehicle:raise HTTPException(409,'Biển số không thuộc xe của bãi demo; chỉ lưu bằng chứng')
            url=f'/simulation/observations/{ident}/image'
            if mode=='ENTRY':
                spots=db.query(ParkingSpot).join(ParkingArea).filter(ParkingArea.parking_lot_id==lot_id,
                    ParkingSpot.spot_type==vehicle.vehicle_type,ParkingSpot.energy_type==vehicle.energy_type,ParkingSpot.status=='AVAILABLE').order_by(ParkingSpot.id).all()
                if not spots:raise HTTPException(409,'Không có ô demo phù hợp đang trống')
                session=check_in(CheckIn(vehicle_id=vehicle.id,parking_spot_id=spots[0].id,entry_plate_image=url,
                                        entry_plate_confidence=result['confidence']),db,user,commit=False,recognized_plate=plate)
                values.update(outcome='CHECKED_IN',message='Xe vào: đã xác nhận bằng nghiệp vụ chung',parking_session_id=session.id)
            else:
                session=db.query(ParkingSession).join(ParkingSpot).join(ParkingArea).filter(ParkingSession.vehicle_id==vehicle.id,
                    ParkingSession.status=='ACTIVE',ParkingArea.parking_lot_id==lot_id).first()
                if not session:raise HTTPException(409,'Không có lượt đang gửi tại bãi demo')
                session=check_out(session.id,CheckOut(exit_plate_image=url,exit_plate_confidence=result['confidence']),
                                  db,user,commit=False,recognized_plate=plate)
                values.update(outcome='CHECKED_OUT',message='Xe ra: chờ thanh toán để mở barie ảo',parking_session_id=session.id)
        row=CameraObservation(**values);db.add(row);db.commit();return row
    except HTTPException as exc:
        db.rollback();values.update(outcome='REJECTED',message=str(exc.detail)[:250]);values.pop('parking_session_id',None)
        row=CameraObservation(**values);db.add(row)
        try:db.commit();return row
        except Exception:db.rollback();path.unlink(missing_ok=True);raise
    except Exception:
        db.rollback();path.unlink(missing_ok=True);raise


class LiveCamera:
    def __init__(self,lot_id,actor_id,mode):
        self.lot_id=lot_id;self.actor_id=actor_id;self.mode=mode
        self.stop_event=threading.Event();self.lock=threading.Lock();self.children=[]
        self.latest=None;self.output=None;self.counter=0;self.state='STARTING';self.error=''
        self.url='';self.processed=0;self.started=time.monotonic();self.last_observation=None
        self.thread=threading.Thread(target=self.run,name='parkly-rtsp',daemon=True)

    def snapshot(self):
        with self.lock:
            return {'parking_lot_id':self.lot_id,'mode':self.mode,'state':self.state,'error':self.error,
                'rtsp_url':self.url,'synthetic':True,'processed_frames':self.processed,
                'elapsed_seconds':round(time.monotonic()-self.started,1),'last_observation':self.last_observation,
                **(self.output or {})}

    def start_source(self):
        import imageio_ffmpeg
        binary=ROOT/'tools/bin/mediamtx/mediamtx.exe';source=ROOT/'backend/ai_engine/assets/camera-demo.mp4'
        if not binary.is_file():binary=ROOT.parent/'cong_cu_phat_trien/tools/bin/mediamtx/mediamtx.exe'
        if not binary.is_file() or not source.is_file():raise RuntimeError('Thiếu MediaMTX hoặc clip RTSP đầu vào')
        with socket.socket() as sock:
            try:sock.bind(('127.0.0.1',8554))
            except OSError:sock.bind(('127.0.0.1',0))
            port=sock.getsockname()[1]
        self.url=f'rtsp://127.0.0.1:{port}/'+('cam_out' if self.mode=='EXIT' else 'cam_in')
        work=ROOT.parent/'work'/('live-camera-'+uuid4().hex);work.mkdir(parents=True)
        config=work/'mediamtx.yml'
        config.write_text(f'rtsp: yes\nrtspAddress: 127.0.0.1:{port}\nrtspTransports: [tcp]\nrtmp: no\nhls: no\nwebrtc: no\nsrt: no\npaths:\n  all_others:\n    source: publisher\n')
        self.log=(work/'processes.log').open('w',encoding='utf-8')
        def spawn(command):
            child=subprocess.Popen(command,cwd=ROOT,stdout=self.log,stderr=self.log,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));self.children.append(child)
        spawn([str(binary),str(config)])
        if self.stop_event.wait(.5):return
        spawn([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-re','-stream_loop','-1','-i',str(source),
               '-an','-c:v','libx264','-preset','ultrafast','-tune','zerolatency','-g','10','-f','rtsp','-rtsp_transport','tcp',self.url])
        self.stop_event.wait(1)

    def read(self):
        import cv2
        while not self.stop_event.is_set():
            cap=cv2.VideoCapture(self.url,cv2.CAP_FFMPEG,[cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,2000,cv2.CAP_PROP_READ_TIMEOUT_MSEC,2000])
            try:
                while not self.stop_event.is_set():
                    ok,frame=cap.read()
                    if not ok:break
                    with self.lock:
                        self.counter+=1;self.latest=(self.counter,now(),frame)
            finally:cap.release()
            if not self.stop_event.is_set():
                with self.lock:self.state='RECONNECTING'
                self.stop_event.wait(1)

    def run(self):
        lease=None;reader=None
        try:
            if engine.dialect.name=='postgresql':
                from sqlalchemy import text
                lease=engine.connect().execution_options(isolation_level='AUTOCOMMIT')
                if not lease.execute(text('SELECT pg_try_advisory_lock(96644,:lot)'),{'lot':self.lot_id}).scalar():
                    raise RuntimeError('Camera bãi này đang được xử lý ở backend khác')
            self.start_source()
            reader=threading.Thread(target=self.read,name='parkly-rtsp-reader',daemon=True);reader.start()
            import cv2
            from ai_engine.recognizer import recognize
            previous=None;stable=0;seen={};last_frame=0;last_capture=None
            while not self.stop_event.wait(.12):
                with self.lock:current=self.latest
                if not current or current[0]==last_frame:continue
                frame_id,captured_at,frame=current;last_frame=frame_id
                if last_capture and (captured_at-last_capture).total_seconds()>1.5:previous=None;stable=0
                last_capture=captured_at
                ok,raw=cv2.imencode('.jpg',frame)
                if not ok:continue
                result=recognize(raw.tobytes());plate=result.get('plate')
                stable=stable+1 if plate and plate==previous else 1 if plate else 0;previous=plate
                boxes=result.get('detections') or result.get('candidates') or []
                display=frame.copy()
                for box in boxes:
                    x1,y1,x2,y2=map(int,box['box']);cv2.rectangle(display,(x1,y1),(x2,y2),(20,230,110),2)
                    text=f'{plate or "REVIEW"} | OCR {result["confidence"]:.2f} | YOLO {box.get("confidence",0):.2f}'
                    cv2.putText(display,text,(max(0,x1),max(45,y1-8)),cv2.FONT_HERSHEY_SIMPLEX,.47,(20,255,120),1)
                cv2.putText(display,f'SYNTHETIC RTSP | frame {frame_id} | {captured_at:%H:%M:%S}',(12,22),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,220,255),1)
                ok,annotated=cv2.imencode('.jpg',display,[cv2.IMWRITE_JPEG_QUALITY,75])
                if not ok:continue
                with self.lock:
                    self.processed+=1;self.state='RUNNING'
                    self.output={'frame_id':frame_id,'captured_at':captured_at.isoformat(),'jpeg':base64.b64encode(annotated).decode(),
                        'plate':plate,'confidence':result['confidence'],'boxes':boxes,'alpr_ms':result['elapsed_ms'],'stable_frames':stable}
                if plate and not result['needs_review'] and stable>=3 and time.monotonic()-seen.get(plate,-1000)>30:
                    with SessionLocal() as db:
                        row=record_evidence(db,self.lot_id,self.actor_id,result,raw.tobytes(),frame_id,captured_at,self.mode)
                        with self.lock:self.last_observation={'id':row.id,'outcome':row.outcome,'message':row.message,'parking_session_id':row.parking_session_id}
                    seen[plate]=time.monotonic()
                self.stop_event.wait(.2)
        except Exception as exc:
            with self.lock:
                self.state='ERROR';self.error=str(exc) if isinstance(exc,RuntimeError) else 'Luồng AI bị lỗi; kiểm tra cấu hình hoặc khởi động lại'
        finally:
            self.stop_event.set()
            for child in reversed(self.children):
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=3)
                    except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
            if reader:reader.join(timeout=4)
            if hasattr(self,'log'):self.log.close()
            if lease:
                from sqlalchemy import text
                try:lease.execute(text('SELECT pg_advisory_unlock(96644,:lot)'),{'lot':self.lot_id})
                finally:lease.close()
            with self.lock:
                if self.state!='ERROR':self.state='STOPPED'

    def stop(self):
        self.stop_event.set();self.thread.join(timeout=10)
        if self.thread.is_alive():raise HTTPException(409,'Camera đang đóng kết nối; chờ vài giây rồi thử lại')


def start(lot_id,actor_id,mode):
    global _controller
    with _guard:
        if _controller and _controller.thread.is_alive():
            if (_controller.lot_id,_controller.mode)==(lot_id,mode):return _controller.snapshot()
            raise HTTPException(409,'Dừng camera hiện tại trước khi đổi bãi/chế độ')
        _controller=LiveCamera(lot_id,actor_id,mode);_controller.thread.start();return _controller.snapshot()


def stop(lot_id=None):
    with _guard:
        if _controller and (lot_id is None or _controller.lot_id==lot_id):_controller.stop()


def status(lot_id):
    with _guard:
        return _controller.snapshot() if _controller and _controller.lot_id==lot_id else {'state':'STOPPED','parking_lot_id':lot_id,'synthetic':True}
