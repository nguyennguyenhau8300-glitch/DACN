import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path


def use_local_python():
    from importlib.util import find_spec

    if all(find_spec(name) is not None for name in ('fastapi', 'uvicorn', 'sqlalchemy', 'psycopg2', 'dotenv')):
        return
    venv = Path(__file__).resolve().with_name('venv')
    python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file() or Path(sys.prefix).resolve() == venv:
        raise SystemExit('Cài thư viện backend lần đầu bằng python -m pip install -r requirements.txt')
    command = [str(python), str(Path(__file__).resolve()), *sys.argv[1:]]
    if os.name != 'nt':
        os.execv(command[0], command)
    from subprocess import Popen

    with Popen(command) as backend:
        try:
            raise SystemExit(backend.wait())
        except KeyboardInterrupt:
            raise SystemExit(backend.wait())


if __name__ == '__main__':
    use_local_python()
    os.environ.setdefault('PARKLY_LOCAL_WEB_ORIGINS', '1')

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from database import SessionLocal, engine, prepare_schema
from services.http_origins import allowed_origins, loopback_web_origin
from services.parking_service import expire_reservations

def expire_once():
    with SessionLocal() as db:
        expire_reservations(db)

def monitor_once():
    from services.alert_service import sweep_connections
    with SessionLocal() as db:
        sweep_connections(db)

async def monitor_worker():
    while True:
        try:
            await asyncio.to_thread(monitor_once)
        except Exception:
            logging.getLogger(__name__).exception('IoT incident monitoring failed')
        await asyncio.sleep(10)

async def expiration_worker():
    while True:
        try:
            await asyncio.to_thread(expire_once)
        except Exception:
            logging.getLogger(__name__).exception('Reservation expiration failed')
        await asyncio.sleep(30)

async def barrier_worker():
    from services.barrier_service import advance
    def once():
        with SessionLocal() as db: advance(db)
    while True:
        try: await asyncio.to_thread(once)
        except Exception: logging.getLogger(__name__).exception('Virtual barrier failed')
        await asyncio.sleep(1)

@asynccontextmanager
async def lifespan(app):
    worker = asyncio.create_task(expiration_worker())
    monitor = asyncio.create_task(monitor_worker())
    from services import realtime
    events = asyncio.create_task(realtime.worker(engine))
    barriers = asyncio.create_task(barrier_worker())
    from services.simulation_service import worker as simulation_worker
    simulation = asyncio.create_task(simulation_worker())
    from services.mqtt_bridge import start_bridge, stop_bridge
    bridge = await asyncio.to_thread(start_bridge)
    try:
        yield
    finally:
        worker.cancel()
        monitor.cancel()
        events.cancel()
        barriers.cancel()
        simulation.cancel()
        from services.live_camera import stop as stop_camera
        await asyncio.to_thread(stop_camera)
        await asyncio.to_thread(stop_bridge,bridge)
        await asyncio.gather(worker, monitor, events, barriers, simulation, return_exceptions=True)

from fastapi import FastAPI
from sqlalchemy import text

from routers.auth import router as auth_router
from routers.vehicle import router as vehicle_router
from routers.parking_lot import router as parking_lot_router
from routers.parking_area import router as parking_area_router
from routers.parking_spot import router as parking_spot_router
from routers.iot import router as iot_router
from routers.reservation import router as reservation_router


app = FastAPI(
    lifespan=lifespan,
    title="Smart Parking System API",
    description="Backend API cho hệ thống theo dõi và quản lý bãi xe thông minh",
    version="1.1.0"
)

from routers.operations import router as operations_router
app.include_router(operations_router)

app.include_router(auth_router)
app.include_router(vehicle_router)
app.include_router(parking_lot_router)
app.include_router(parking_area_router)
app.include_router(parking_spot_router)
app.include_router(iot_router)
app.include_router(reservation_router)
from routers.alerts import router as alerts_router
app.include_router(alerts_router)

@app.get("/")
def home():
    if (_dashboard_dist / 'index.html').is_file():
        return RedirectResponse('/dashboard/')
    return {
        "message": "Smart Parking System API",
        "status": "running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.get("/database-test")
def database_test():
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("SELECT current_database();")
            )

            database_name = result.scalar()

        return {
            "status": "success",
            "message": "Kết nối PostgreSQL thành công",
            "database": database_name
        }

    except Exception as e:
        return {
            "status": "error",
            "message": "Không kết nối được cơ sở dữ liệu"
        }
app.add_middleware(CORSMiddleware,
    allow_origins=allowed_origins(), allow_origin_regex=loopback_web_origin(),
    allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(status_code=409, content={'detail':'Dữ liệu trùng hoặc đang được tham chiếu; không thể thực hiện'})

from routers.ai import router as ai_router
app.include_router(ai_router)


from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from database import get_db

@app.get('/health/ready')
def readiness(db: Session = Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status': 'ready', 'service': 'parkly'}

@app.exception_handler(OperationalError)
async def database_operational_error(request, exc):
    code=getattr(exc.orig,'pgcode',None)
    if code in {'40P01','40001','55P03'}:
        return JSONResponse(status_code=409,content={'detail':'Dữ liệu đang được xử lý đồng thời; vui lòng thử lại'})
    return JSONResponse(status_code=503,content={'detail':'Cơ sở dữ liệu tạm thời không khả dụng'})

from routers.iot_devices import router as iot_devices_router
app.include_router(iot_devices_router)

from routers.dashboard import router as dashboard_router
app.include_router(dashboard_router)

from routers.navigation import router as navigation_router
from routers.checkout import router as checkout_router
from routers.analytics import router as analytics_router
from routers.tariffs import router as tariffs_router
from routers.realtime import router as realtime_router
app.include_router(navigation_router)
app.include_router(checkout_router)
app.include_router(analytics_router)
app.include_router(tariffs_router)
app.include_router(realtime_router)
from routers.pos import router as pos_router
app.include_router(pos_router)
from routers.simulation import router as simulation_router
app.include_router(simulation_router)
from routers.internal_demo import router as internal_demo_router
app.include_router(internal_demo_router)

# A built dashboard is served alongside the API. Hash navigation needs no catch-all.
from fastapi.staticfiles import StaticFiles
_dashboard_dist = Path(__file__).resolve().parents[1] / 'web_dashboard' / 'dist'
if (_dashboard_dist / 'index.html').is_file():
    app.mount('/dashboard', StaticFiles(directory=str(_dashboard_dist), html=True), name='dashboard')


@app.get('/mobile.apk', include_in_schema=False)
def download_android_app():
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    package = Path(__file__).resolve().parents[1] / 'mobile_app' / 'dist' / 'Parkly-Android.apk'
    if not package.is_file():
        raise HTTPException(404, 'Chưa có bản cài Android; xem hướng dẫn trong mobile_app/README.md')
    return FileResponse(package, media_type='application/vnd.android.package-archive',
                        filename='Parkly-Android.apk', headers={'Cache-Control':'no-cache'})


def run_dashboard():
    import argparse
    import webbrowser

    import uvicorn
    from sqlalchemy.exc import SQLAlchemyError

    parser = argparse.ArgumentParser(description='Chạy web và API Parkly')
    parser.add_argument('--host', default=os.getenv('PARKLY_HOST', '0.0.0.0'))
    parser.add_argument('--port', type=int, default=os.getenv('PARKLY_API_PORT', '8001'))
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Cổng phải nằm trong khoảng 1–65535.')
    if not (_dashboard_dist / 'index.html').is_file():
        parser.error('Chưa có bản web. Chạy npm ci và npm run build một lần trong web_dashboard.')
    try:
        prepare_schema()
    except SQLAlchemyError:
        raise SystemExit('Không chuẩn bị được database. Kiểm tra PostgreSQL và cấu hình backend/.env.') from None

    browser_host = {'0.0.0.0': '127.0.0.1', '::': '[::1]'}.get(args.host, args.host)
    if ':' in browser_host and not browser_host.startswith('['):
        browser_host = f'[{browser_host}]'
    url = f'http://{browser_host}:{args.port}/dashboard/'
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port))

    async def serve():
        task = asyncio.create_task(server.serve())
        while not server.started and not task.done():
            await asyncio.sleep(0.05)
        if server.started:
            print(f'Parkly: {url}', flush=True)
            if not args.no_browser:
                try:
                    await asyncio.to_thread(webbrowser.open_new_tab, url)
                except webbrowser.Error:
                    pass
        await task

    asyncio.run(serve())


if __name__ == '__main__':
    run_dashboard()
