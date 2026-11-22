"""Real-browser integration tests against an isolated PostgreSQL schema."""
from pathlib import Path
import os,sys,secrets,socket,subprocess,tempfile,time
from uuid import uuid4
from contextlib import contextmanager
from dotenv import load_dotenv
from sqlalchemy import create_engine,text
from sqlalchemy.orm import Session
import httpx
ROOT=Path(__file__).resolve().parents[2]/'DACN'
TESTS=Path(__file__).resolve().parent
MODULES=ROOT/'web_dashboard/node_modules'
if not (MODULES/'vite/bin/vite.js').is_file(): MODULES=ROOT.parent/'node_modules'
WEB=ROOT/'web_dashboard'
sys.path.insert(0,str(ROOT/'backend'))
load_dotenv(ROOT/'backend'/'.env')
from database import engine
from main import app
from models.user import User
from models.parking_lot import ParkingLot
from models.parking_spot import ParkingSpot
from models.parking_area import ParkingArea
from models.vehicle import Vehicle
from models.operations import PricingRule,ParkingSession
from services.auth_service import hash_password
from services.layout_service import initialize_layout
from services.parking_service import now

def unused_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

@contextmanager
def saved_server_logs():
    folder=ROOT.parent/'ket_qua'/('web-server-'+uuid4().hex)
    folder.mkdir(parents=True)
    yield str(folder)

def wait_ready(url,process):
    for _ in range(160):
        if process.poll() is not None:raise RuntimeError('Test server exited during startup')
        try:
            if httpx.get(url,timeout=1).status_code==200:return
        except httpx.HTTPError:pass
        time.sleep(.25)
    raise RuntimeError('Test server did not become ready')

def main():
    schema='frontend_test_'+uuid4().hex
    assert schema.startswith('frontend_test_') and schema[14:].isalnum()
    processes=[];test_engine=None
    with saved_server_logs() as temp:
        try:
            with engine.begin() as conn:conn.execute(text('CREATE SCHEMA '+schema))
            url=engine.url.update_query_dict({'options':'-csearch_path='+schema})
            test_engine=create_engine(url)
            with test_engine.begin() as conn:conn.exec_driver_sql((ROOT/'backend/database/schema.sql').read_text(encoding='utf-8'))
            with Session(test_engine) as db:
                identities = {'ADMIN':'Nguyễn Minh An','SECURITY':'Nhân viên Demo','CUSTOMER':'Khách hàng Demo','MANAGER':'Quản lý Demo'}
                for role, fullname in identities.items():
                    db.add(User(full_name=fullname,email=role.lower()+'@example.com',password_hash=hash_password('TestParking123!'),role=role))
                # Explicit larger fixture keeps existing sensor/camera scenarios independent of defaults.
                lot=ParkingLot(name='Bãi xe Trung tâm',address='Khuôn viên trường · Khu A',car_capacity=50,motorbike_capacity=120,electric_car_capacity=20,electric_motorbike_capacity=50);db.add(lot);db.commit();initialize_layout(db,lot.id)
                spots=db.query(ParkingSpot).order_by(ParkingSpot.id).all()
                for spot in spots:
                    if spot.energy_type=='ELECTRIC':spot.charger_status='READY'
                for spot in spots[8:25]:spot.status='OCCUPIED'
                for spot in spots[40:44]:spot.charger_status='PLANNED'
                for spot in spots[100:104]:spot.status='MAINTENANCE'
                for vt,en in [('CAR','GASOLINE'),('CAR','ELECTRIC'),('MOTORBIKE','GASOLINE'),('MOTORBIKE','ELECTRIC')]:
                    db.add(PricingRule(parking_lot_id=lot.id,vehicle_type=vt,energy_type=en,first_hour_price=10000 if vt=='CAR' else 5000,additional_hour_price=5000 if vt=='CAR' else 2000))
                admin=db.query(User).filter_by(role='ADMIN').one();customer=db.query(User).filter_by(role='CUSTOMER').one()
                vehicle=Vehicle(user_id=admin.id,license_plate='51A-11111',vehicle_type='CAR',energy_type='GASOLINE',brand='Toyota',color='Trắng');db.add(vehicle);db.flush()
                db.add(ParkingSession(vehicle_id=vehicle.id,parking_spot_id=spots[8].id,entry_time=now(),status='ACTIVE',total_amount=0))
                db.add(Vehicle(user_id=customer.id,license_plate='59A1-22222',vehicle_type='MOTORBIKE',energy_type='GASOLINE',brand='Honda',color='Đen'))
                db.commit()
            api_port,web_port=unused_port(),unused_port()
            env=os.environ.copy();env['DATABASE_URL']=url.render_as_string(hide_password=False);env['JWT_SECRET_KEY']=secrets.token_urlsafe(48)
            env['API_PROXY_TARGET']=f'http://127.0.0.1:{api_port}'
            env['E2E_BASE_URL']=f'http://127.0.0.1:{web_port}/dashboard/'
            env['E2E_API_URL']=f'http://127.0.0.1:{api_port}'
            env.update(MQTT_ENABLED='0',REDIS_URL='',PARKLY_SIMULATION_WORKER='0',PARKLY_API_PORT=str(api_port),AI_DETECTOR_MODE='auto')
            env['CAMERA_EVIDENCE_DIR']=str(Path(temp)/'evidence')
            env['AI_IMAGE_DIR']=str(Path(temp)/'plate_images')
            with open(Path(temp)/'servers.log','w',encoding='utf-8') as logs:
                backend=subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port',str(api_port),'--log-level','error'],cwd=ROOT/'backend',env=env,stdout=logs,stderr=logs,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));processes.append(backend)
                wait_ready(env['E2E_API_URL']+'/health/ready',backend)
                frontend=subprocess.Popen(['node',str(MODULES/'vite/bin/vite.js'),'--host','127.0.0.1','--port',str(web_port)],cwd=WEB,env=env,stdout=logs,stderr=logs,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));processes.append(frontend)
                wait_ready(env['E2E_BASE_URL'],frontend)
                # Verify the built version is also served by FastAPI at /dashboard/.
                assert httpx.get(env['E2E_API_URL']+'/dashboard/').status_code==200
                result=subprocess.run(['node',str(MODULES/'@playwright/test/cli.js'),'test','--config',str(TESTS/'playwright.config.js'),*sys.argv[1:]],cwd=WEB,env=env)
                return result.returncode
        except Exception:
            logfile=Path(temp)/'servers.log'
            if logfile.exists():print('\n'.join(logfile.read_text(encoding='utf-8',errors='replace').splitlines()[-30:]))
            raise
        finally:
            for process in reversed(processes):
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
            if test_engine is not None:test_engine.dispose()
            with engine.begin() as conn:conn.execute(text('DROP SCHEMA IF EXISTS '+schema+' CASCADE'))

if __name__=='__main__':sys.exit(main())
