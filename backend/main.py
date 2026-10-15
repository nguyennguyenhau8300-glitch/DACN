import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from database import SessionLocal
from services.parking_service import expire_reservations

def expire_once():
    with SessionLocal() as db:
        expire_reservations(db)

async def expiration_worker():
    while True:
        try:
            await asyncio.to_thread(expire_once)
        except Exception:
            logging.getLogger(__name__).exception('Reservation expiration failed')
        await asyncio.sleep(30)

@asynccontextmanager
async def lifespan(app):
    worker = asyncio.create_task(expiration_worker())
    try:
        yield
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass

from fastapi import FastAPI
from sqlalchemy import text

from database import engine
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
    version="1.0.0"
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

@app.get("/")
def home():
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
    allow_origins=[v.strip() for v in os.getenv('CORS_ORIGINS','http://localhost:3000,http://localhost:5173').split(',') if v.strip()],
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
    return {'status': 'ready'}

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

# A built dashboard is served alongside the API. Hash navigation needs no catch-all.
from pathlib import Path
from fastapi.staticfiles import StaticFiles
_dashboard_dist = Path(__file__).resolve().parents[1] / 'web_dashboard' / 'dist'
if (_dashboard_dist / 'index.html').is_file():
    app.mount('/dashboard', StaticFiles(directory=str(_dashboard_dist), html=True), name='dashboard')
