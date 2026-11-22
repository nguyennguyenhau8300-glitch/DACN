from test_backend import setup
from main import app
from dependencies import get_current_user
from models.operations import ParkingSession, Payment
from models.vehicle import Vehicle
from services.parking_service import now


def test_payment_filter_is_scoped_to_session_and_customer_ownership(setup):
    c,db,a,u,s,v=setup
    other=Vehicle(user_id=a.id,license_plate='30F-90909',vehicle_type='CAR');db.add(other);db.flush()
    own=ParkingSession(vehicle_id=v.id,parking_spot_id=s.id,entry_time=now(),exit_time=now(),status='COMPLETED',total_amount=5000)
    hidden=ParkingSession(vehicle_id=other.id,parking_spot_id=s.id,entry_time=now(),exit_time=now(),status='COMPLETED',total_amount=10000)
    db.add_all([own,hidden]);db.flush()
    db.add_all([Payment(parking_session_id=row.id,amount=row.total_amount,payment_method='CASH',status='SUCCESS',paid_at=now()) for row in [own,hidden]]);db.commit()
    response=c.get('/payments',params={'parking_session_id':own.id,'limit':1})
    assert response.status_code==200 and response.json()[0]['parking_session_id']==own.id
    assert len(response.json())==1
    app.dependency_overrides[get_current_user]=lambda:u
    assert len(c.get('/payments',params={'parking_session_id':own.id}).json())==1
    assert c.get('/payments',params={'parking_session_id':hidden.id}).json()==[]
    assert c.get('/payments',params={'parking_session_id':0}).status_code==422
