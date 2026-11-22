"""Native Flutter tests against a temporary PostgreSQL schema, never the primary lot."""
from pathlib import Path
import os, secrets, shutil, socket, subprocess, sys, tempfile, time
from uuid import uuid4
from datetime import date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import httpx

ROOT=Path(__file__).resolve().parents[3]/'DACN'
TESTS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
load_dotenv(ROOT/'backend/.env')
from database import engine
from main import app
from models.user import User
from models.vehicle import Vehicle
from models.parking_lot import ParkingLot
from models.parking_spot import ParkingSpot
from models.operations import PricingRule
from services.layout_service import initialize_layout
from services.auth_service import hash_password

def main():
    device_id=sys.argv[1] if len(sys.argv)>1 else 'emulator-5554'
    schema='mobile_test_'+uuid4().hex
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    process=None;test_engine=None
    with tempfile.TemporaryDirectory(prefix='parkly-mobile-') as temp:
        try:
            with engine.begin() as conn:conn.execute(text('CREATE SCHEMA '+schema))
            url=engine.url.update_query_dict({'options':'-csearch_path='+schema});test_engine=create_engine(url)
            with test_engine.begin() as conn:conn.exec_driver_sql((ROOT/'backend/database/schema.sql').read_text(encoding='utf-8'))
            with Session(test_engine) as db:
                users=[]
                for role in ['ADMIN','CUSTOMER']:
                    row=User(full_name='Quản trị Android' if role=='ADMIN' else 'Khách hàng Demo',email=role.lower()+'@example.com',password_hash=hash_password('TestParking123!'),role=role,date_of_birth=date(2002,4,23),hometown='Huế')
                    db.add(row);users.append(row)
                lot=ParkingLot(name='Bãi xe Trung tâm',address='Dữ liệu kiểm thử Android');db.add(lot);db.commit();initialize_layout(db,lot.id)
                for spot in db.query(ParkingSpot).filter_by(energy_type='ELECTRIC'):spot.charger_status='READY'
                for vehicle_type,energy_type in [('CAR','GASOLINE'),('CAR','ELECTRIC'),('MOTORBIKE','GASOLINE'),('MOTORBIKE','ELECTRIC')]:
                    db.add(PricingRule(parking_lot_id=lot.id,vehicle_type=vehicle_type,energy_type=energy_type,first_hour_price=5000,additional_hour_price=2000))
                db.add_all([Vehicle(user_id=users[0].id,license_plate='59A1-12345',vehicle_type='MOTORBIKE',energy_type='GASOLINE'),Vehicle(user_id=users[1].id,license_plate='59A1-22222',vehicle_type='MOTORBIKE',energy_type='GASOLINE')]);db.commit()
            env=os.environ.copy();env['DATABASE_URL']=url.render_as_string(hide_password=False);env['JWT_SECRET_KEY']=secrets.token_urlsafe(48)
            env['AI_DETECTOR_MODE']='ocr'  # Native picker fixture tests isolate OCR; YOLO/video evaluated separately.
            env['REDIS_URL']='';env['MQTT_ENABLED']='0'
            module=Path(temp)/'mobile_fixture.py'
            adb=Path(os.getenv('ANDROID_HOME',str(Path.home()/'AppData/Local/Android/sdk')))/'platform-tools/adb.exe'
            artifacts=Path(os.getenv('MOBILE_ARTIFACT_DIR',str(ROOT.parent/'ket_qua/android-test-results')))
            artifacts.mkdir(parents=True,exist_ok=True)
            module.write_text(f"import sys\nsys.path.insert(0,{str(ROOT/'backend')!r})\nfrom main import app\nfrom fastapi import HTTPException\nfrom fastapi.staticfiles import StaticFiles\nfrom pathlib import Path\nimport re, subprocess\napp.mount('/test-fixtures',StaticFiles(directory={str(ROOT.parent/'kiem_thu/fixtures/ai_engine')!r}))\n@app.post('/test-screenshot/{{name}}')\ndef capture(name: str):\n    if not re.fullmatch(r'[A-Za-z0-9_-]{{1,80}}',name): raise HTTPException(400)\n    data=subprocess.check_output([{str(adb)!r},'-s',{device_id!r},'exec-out','screencap','-p'],timeout=15)\n    (Path({str(artifacts)!r})/(name+'.png')).write_bytes(data)\n    return {{'saved': True}}\n",encoding='utf-8')
            with (Path(temp)/'server.log').open('w',encoding='utf-8') as logs:
                process=subprocess.Popen([sys.executable,'-m','uvicorn','mobile_fixture:app','--app-dir',temp,'--host','127.0.0.1','--port',str(port),'--log-level','error'],cwd=ROOT/'backend',env=env,stdout=logs,stderr=logs,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                for _ in range(160):
                    if process.poll() is not None:raise RuntimeError('Android test server stopped during startup')
                    try:
                        if httpx.get(f'http://127.0.0.1:{port}/health/ready',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.25)
                else:raise RuntimeError('Android test server did not become ready')
                flutter=shutil.which('flutter')
                if not flutter:raise RuntimeError('Flutter is not installed')
                for _ in range(120):
                    ready=subprocess.run([str(adb),'-s',device_id,'shell','getprop','sys.boot_completed'],capture_output=True,text=True,timeout=5)
                    if ready.returncode==0 and ready.stdout.strip()=='1':break
                    time.sleep(.5)
                else:raise RuntimeError('Android device is not ready')
                command=[flutter,'drive','--driver='+str(TESTS/'test_driver/integration_test.dart'),'--target='+str(TESTS/'integration_test/app_test.dart'),'-d',device_id,f'--dart-define=API_URL=http://10.0.2.2:{port}','--no-pub']
                print('Running native Android tests; log: '+str(artifacts/'Android-tests.log'),flush=True)
                with (artifacts/'Android-tests.log').open('w',encoding='utf-8') as test_log:
                    result=subprocess.run(command,cwd=ROOT/'mobile_app',env=env,stdout=test_log,stderr=subprocess.STDOUT)
                tail=(artifacts/'Android-tests.log').read_text(encoding='utf-8',errors='replace').splitlines()[-65:]
                print('\n'.join(tail))
                return result.returncode
        finally:
            if process is not None:
                if os.name=='nt':
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                else:process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
            if test_engine is not None:test_engine.dispose()
            with engine.begin() as conn:conn.execute(text('DROP SCHEMA IF EXISTS '+schema+' CASCADE'))

if __name__=='__main__':sys.exit(main())
