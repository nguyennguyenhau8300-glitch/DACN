"""Idempotent local launcher for API/web/Android with optional advanced protocol services."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
PYTHON=ROOT/'backend/venv/Scripts/python.exe'

def listening(port):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=.5): return True
    except OSError: return False

def api_ready(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/openapi.json',timeout=2) as response:
            return '/internal-simulation/state' in json.load(response).get('paths',{})
    except Exception: return False

def start(command,log,env):
    with log.open('a',encoding='utf-8') as output:
        return subprocess.Popen(command,cwd=ROOT,env=env,stdout=output,stderr=output,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--advanced-protocols',action='store_true');args=parser.parse_args()
    state={'mqtt':listening(1883),'redis_protocol':listening(6379),'web_8001':api_ready(8001),'android_8002':api_ready(8002)}
    if args.check: print(json.dumps(state));return
    work=ROOT.parent/'work';work.mkdir(exist_ok=True)
    env=os.environ.copy();env.update(REDIS_URL='redis://127.0.0.1:6379/0' if args.advanced_protocols else '',REDIS_BACKEND_KIND='PROTOCOL_SIMULATOR',MQTT_ENABLED='1' if args.advanced_protocols else '0',MQTT_HOST='127.0.0.1',AI_DETECTOR_MODE='auto',PYTHONDONTWRITEBYTECODE='1')
    subprocess.run([str(PYTHON),str(ROOT/'backend/scripts/migrate_extensions.py')],cwd=ROOT/'backend',check=True,env=env)
    if args.advanced_protocols and (not state['mqtt'] or not state['redis_protocol']):
        flags=[]
        if state['mqtt']: flags=['--redis-only']
        elif state['redis_protocol']: flags=['--mqtt-only']
        start([str(PYTHON),str(ROOT/'backend/iot/local_services.py'),*flags],work/'services.log',env)
        for _ in range(50):
            if listening(1883) and listening(6379): break
            time.sleep(.2)
        else: raise SystemExit('Khong khoi dong duoc dich vu. Xem work/services.log')
    for port in [8001,8002]:
        if api_ready(port): continue
        if listening(port): raise SystemExit(f'Cong {port} dang chay phien ban cu/chuong trinh khac. Tat backend cu roi chay lai.')
        server_env={**env,'PARKLY_SIMULATION_WORKER':'1' if args.advanced_protocols and port==8001 else '0','PARKLY_API_PORT':str(port)}
        start([str(PYTHON),str(ROOT/'tools/run_dashboard.py'),'--port',str(port),*(['--lan'] if port==8002 else [])],work/f'backend-{port}.log',server_env)
        for _ in range(80):
            if api_ready(port): break
            time.sleep(.25)
        else: raise SystemExit(f'Backend {port} chua san sang. Xem work/backend-{port}.log')
    print('Parkly: http://127.0.0.1:8001/dashboard/  |  Android: cong LAN 8002')
    print('Gia lap noi bo: khong can MQTT, Redis, RTSP, FFmpeg hay Wokwi.' if not args.advanced_protocols else 'Che do giao thuc nang cao dang bat.')

if __name__=='__main__': main()
