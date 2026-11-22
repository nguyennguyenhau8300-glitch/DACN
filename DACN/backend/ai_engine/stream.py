"""Video/RTSP ALPR, stable observations, reconnect, optional real backend actions.
The generated demo video is SYNTHETIC. Preview is the default; actions require staff login.
"""
import argparse
from getpass import getpass
import json
from pathlib import Path
import time
import cv2
import httpx
from ai_engine.recognizer import recognize,normalize_plate

def run(args):
    remote=str(args.source).lower().startswith(('rtsp://','rtsps://'))
    if not remote and not Path(args.source).is_file(): raise SystemExit('Không tìm thấy video')
    client=httpx.Client(base_url=args.api_base,timeout=120)
    if args.mode!='preview':
        login=client.post('/auth/login',json={'email':input('Email nhân viên: '),'password':getpass('Mật khẩu: ')})
        login.raise_for_status();token=login.json()['access_token'];client.headers['Authorization']='Bearer '+token
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter();frames=processed=accepted=0;previous=None;stable=0;acted={};latencies=[];writer=None
    try:
        with output.open('w',encoding='utf-8') as log:
            while True:
                cap=cv2.VideoCapture(args.source,cv2.CAP_FFMPEG,[cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,5000,cv2.CAP_PROP_READ_TIMEOUT_MSEC,5000]) if remote else cv2.VideoCapture(args.source)
                if not cap.isOpened():
                    cap.release()
                    if not remote or args.once: raise RuntimeError('Không mở được nguồn camera hoặc video')
                    time.sleep(3);continue
                while True:
                    if args.max_processed and processed>=args.max_processed: break
                    ok,frame=cap.read()
                    if not ok: break
                    frames+=1
                    if frames%args.every: continue
                    _,encoded=cv2.imencode('.jpg',frame)
                    result=recognize(encoded.tobytes(),uploaded_photo=not args.synthetic);processed+=1
                    latencies.append(result['elapsed_ms']);plate=result['plate']
                    stable=stable+1 if plate and plate==previous else 1 if plate else 0
                    previous=plate
                    event={'frame':frames,'plate':plate,'confidence':result['confidence'],'reason':result['reason'],'stable_observations':stable,'elapsed_ms':result['elapsed_ms'],'action':'preview'}
                    if plate: accepted+=1
                    if args.mode!='preview' and plate and stable>=args.stable and time.monotonic()-acted.get(plate,-1e20)>args.cooldown:
                        if args.mode=='entry':
                            if not args.spot_id: raise RuntimeError('--spot-id bắt buộc cho entry')
                            response=client.post('/ai/check-in',data={'parking_spot_id':str(args.spot_id)},files={'file':('frame.jpg',encoded.tobytes(),'image/jpeg')})
                        else:
                            rows=client.get('/parking-sessions',params={'session_status':'ACTIVE','limit':500});rows.raise_for_status()
                            vehicles=client.get('/dashboard-data/vehicles');vehicles.raise_for_status()
                            ids={v['id'] for v in vehicles.json() if normalize_plate(v['license_plate'])==plate}
                            matches=[s for s in rows.json() if s['vehicle_id'] in ids]
                            if len(matches)!=1: event['action']='no_unique_active_session';response=None
                            else: response=client.post(f"/ai/check-out/{matches[0]['id']}",files={'file':('frame.jpg',encoded.tobytes(),'image/jpeg')})
                        if response is not None:
                            event.update(action='committed' if response.is_success else 'rejected',http_status=response.status_code)
                        acted[plate]=time.monotonic()
                    log.write(json.dumps(event,ensure_ascii=False)+'\n');log.flush()
                    if args.annotated:
                        if writer is None: writer=cv2.VideoWriter(args.annotated,cv2.VideoWriter_fourcc(*'mp4v'),max(1,10/args.every),(frame.shape[1],frame.shape[0]))
                        cv2.putText(frame,'SYNTHETIC DEMO' if args.synthetic else 'ALPR PREVIEW',(12,24),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,220,255),2)
                        cv2.putText(frame,plate or result['reason'],(12,52),cv2.FONT_HERSHEY_SIMPLEX,.7,(100,255,150),2)
                        writer.write(frame)
                cap.release()
                if not remote or args.once or (args.max_processed and processed>=args.max_processed): break
                previous=None;stable=0;time.sleep(3)
    finally:
        client.close()
        if writer: writer.release()
    elapsed=time.perf_counter()-start
    summary={'source_kind':'RTSP' if remote else 'video','synthetic':args.synthetic,'frames':frames,'processed':processed,'accepted_frames':accepted,
             'elapsed_seconds':round(elapsed,2),'processed_fps':round(processed/elapsed,2),'alpr_p95_ms':sorted(latencies)[min(len(latencies)-1,int(len(latencies)*.95))] if latencies else None}
    output.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',default=str(Path(__file__).resolve().parents[3]/'ket_qua/ai/stream-events.jsonl'))
    parser.add_argument('--mode',choices=['preview','entry','exit'],default='preview');parser.add_argument('--api-base',default='http://127.0.0.1:8001')
    parser.add_argument('--spot-id',type=int);parser.add_argument('--every',type=int,default=3);parser.add_argument('--stable',type=int,default=3)
    parser.add_argument('--cooldown',type=float,default=30);parser.add_argument('--once',action='store_true');parser.add_argument('--synthetic',action='store_true');parser.add_argument('--annotated')
    parser.add_argument('--max-processed',type=int,default=0)
    args=parser.parse_args()
    if args.every<1 or args.stable<1 or args.cooldown<0 or args.max_processed<0: parser.error('Tham số lấy mẫu không hợp lệ')
    run(args)
