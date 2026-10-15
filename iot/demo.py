"""One-command demo using a temporary PostgreSQL schema and a real HTTP server."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
load_dotenv(ROOT/'backend'/'.env')
from database import engine
from services.auth_service import hash_password
from simulator import configure, run_round, request_json


def main():
    parser=argparse.ArgumentParser(description='Demo IoT trên bãi thử 170 ô; tự dọn sau khi chạy')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    schema='iot_demo_'+uuid4().hex
    # Generated identifier only; never accept a user-supplied schema for deletion.
    assert schema.startswith('iot_demo_') and len(schema)==41 and schema[9:].isalnum()
    demo_engine=None; process=None
    with tempfile.TemporaryDirectory(prefix='smart-parking-iot-') as temp:
        try:
            with engine.begin() as conn:
                conn.execute(text('CREATE SCHEMA '+schema))
            url=engine.url.update_query_dict({'options':'-csearch_path='+schema})
            demo_engine=create_engine(url)
            password=secrets.token_urlsafe(24)
            with demo_engine.begin() as conn:
                conn.exec_driver_sql((ROOT/'database'/'schema.sql').read_text(encoding='utf-8'))
                conn.execute(text("INSERT INTO users(full_name,email,password_hash,role) VALUES (:name,:email,:password,'ADMIN')"),
                             {'name':'IoT Demo Admin','email':'iot-demo@example.com','password':hash_password(password)})
            with socket.socket() as listener:
                listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
            env=os.environ.copy();env['DATABASE_URL']=url.render_as_string(hide_password=False)
            env['JWT_SECRET_KEY']=secrets.token_urlsafe(48)
            with open(Path(temp)/'server.log','w',encoding='utf-8') as log:
                process=subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port',str(port),'--log-level','error'],
                                         cwd=ROOT/'backend',env=env,stdout=log,stderr=log,
                                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=15) as client:
                    for _ in range(80):
                        if process.poll() is not None: raise RuntimeError('Server demo dừng khi khởi động')
                        try:
                            if client.get('/health/ready').status_code==200: break
                        except httpx.TransportError: pass
                        time.sleep(0.25)
                    else: raise RuntimeError('Server demo chưa sẵn sàng')
                    token=request_json(client,'POST','/auth/login',json={'email':'iot-demo@example.com','password':password})['access_token']
                    headers={'Authorization':'Bearer '+token}
                    lot=request_json(client,'POST','/parking-lots',headers=headers,json={'name':'Bãi mô phỏng IoT','address':'Dữ liệu demo'})
                    layout=request_json(client,'POST',f"/parking-lots/{lot['id']}/initialize-layout",headers=headers)
                    print(f"Đã tạo bãi thử: {layout['total_configured_spots']} ô đỗ",flush=True)
                    config_path=Path(temp)/'devices.local.json'
                    config=configure(client,token,lot['id'],config_path)
                    print(f"Thiết bị mô phỏng: {len(config['devices'])} (170 cảm biến + 70 điểm sạc)",flush=True)
                    spots=request_json(client,'GET','/parking-spots',params={'parking_lot_id':lot['id']},headers=headers)
                    # Commission simulated charging points only inside the temporary schema.
                    for spot in spots:
                        if spot['energy_type']=='ELECTRIC':
                            request_json(client,'PATCH',f"/parking-spots/{spot['id']}/charging-status",headers=headers,json={'charger_status':'READY'})
                    snapshots=[]
                    for i in range(3):
                        result=run_round(client,config,config_path,'cycle',i)
                        capacity=request_json(client,'GET',f"/parking-lots/{lot['id']}/capacity",headers=headers)
                        snapshots.append({'round':i+1,**result,'available_for_booking':sum(g['available_for_booking'] for g in capacity['groups'])})
                        print(f"Vòng {i+1}: {result['sent']} bản tin; {snapshots[-1]['available_for_booking']} chỗ có thể đặt",flush=True)
                    fault=run_round(client,config,config_path,'charger-fault',3)
                    fault_capacity=request_json(client,'GET',f"/parking-lots/{lot['id']}/capacity",headers=headers)
                    fault_available=sum(g['available_for_booking'] for g in fault_capacity['groups'])
                    print(f'Lỗi sạc mô phỏng: còn {fault_available} chỗ có thể đặt (các chỗ xe xăng)',flush=True)
                    sensor=config['devices'][0]
                    with demo_engine.begin() as conn:
                        conn.execute(text("UPDATE iot_devices SET last_seen_at=last_seen_at-INTERVAL '1 hour', last_telemetry_at=last_telemetry_at-INTERVAL '1 hour' WHERE device_code=:code"),{'code':sensor['device_code']})
                    devices=request_json(client,'GET','/iot/devices',headers=headers)
                    offline=next(d for d in devices if d['device_code']==sensor['device_code'])
                    heartbeat=request_json(client,'POST',f"/iot/devices/{sensor['device_code']}/heartbeat",headers={'X-API-Key':sensor['api_key']})
                    print(f"Mất kết nối: {offline['connection_status']}; heartbeat khôi phục kết nối nhưng số đo vẫn cũ: {not heartbeat['telemetry_fresh']}",flush=True)
                    report={'mode':'simulation','spots':len(spots),'devices':len(config['devices']),
                            'sensor_devices':sum(d['kind']=='SENSOR' for d in config['devices']),
                            'charger_devices':sum(d['kind']=='CHARGER' for d in config['devices']),
                            'groups':[{k:g[k] for k in ['vehicle_type','energy_type','capacity']} for g in capacity['groups']],
                            'rounds':snapshots,'charger_fault_available':fault_available,
                            'offline_detected':offline['connection_status']=='OFFLINE',
                            'heartbeat_does_not_refresh_measurement':not heartbeat['telemetry_fresh']}
                    assert [r['available_for_booking'] for r in snapshots]==[170,0,170],report
                    assert fault_available==100 and report['offline_detected'] and report['heartbeat_does_not_refresh_measurement'],report
                    if args.report:
                        args.report.parent.mkdir(parents=True,exist_ok=True)
                        args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                    print('Demo hoàn tất. Dữ liệu bãi chính được giữ nguyên.',flush=True)
        finally:
            if process is not None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill();process.wait(timeout=10)
            if demo_engine is not None: demo_engine.dispose()
            with engine.begin() as conn: conn.execute(text('DROP SCHEMA IF EXISTS '+schema+' CASCADE'))

if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: print('Đã dừng demo và dọn bãi thử.')
