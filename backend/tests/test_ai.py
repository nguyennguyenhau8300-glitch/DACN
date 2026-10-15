import io
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from test_backend import setup
from main import app
from dependencies import get_current_user
from models.operations import ParkingSession
from services import ai_service
from ai_engine.recognizer import collect_candidates,normalize_plate,read_image,ImageError,recognize,MAX_BYTES

def png():
    data=io.BytesIO();Image.new('RGB',(400,200),'white').save(data,format='PNG');return data.getvalue()

def accepted(plate='59A112345',confidence=.97):
    return {'plate':plate,'confidence':confidence,'needs_review':False,'reason':'accepted','candidates':[]}

def box(x,y,w,h):return [[x,y],[x+w,y],[x+w,y+h],[x,y+h]]

def test_group_two_line_plate_and_order():
    candidates,_=collect_candidates(['123.45','59A1'],[.96,.95],[box(30,80,150,40),box(40,10,120,40)])
    assert [c['plate'] for c in candidates]==['59A112345']
    assert candidates[0]['confidence']==.95

def test_no_merge_distant_plates_or_guess():
    c,_=collect_candidates(['59A1','12345','30A-888.88'],[.99]*3,[box(10,10,100,30),box(900,400,100,30),box(400,10,200,30)])
    assert [v['plate'] for v in c]==['30A88888']
    assert normalize_plate('59-A1 123.45')=='59A112345'
    c,_=collect_candidates(['3OA12345'],[.99],[box(0,0,100,40)])
    assert c==[]

def test_invalid_images_and_roi():
    for value in [b'',b'not an image',b'a'*(MAX_BYTES+1)]:
        with pytest.raises(ImageError):read_image(value)
    with pytest.raises(ImageError):recognize(png(),[0,0,999,200])

@pytest.mark.parametrize('texts,scores,expected',[
    (['30A12345'],[.4],'low_confidence'),
    (['30A12345','59A112345'],[.99,.99],'multiple_plates'),
    ([],[],'no_plate')])
def test_conservative_decision(texts,scores,expected):
    from types import SimpleNamespace
    output=SimpleNamespace(txts=texts,scores=scores,boxes=[box(10,10+i*100,200,40) for i in range(len(texts))])
    with patch('ai_engine.recognizer._get_engine',return_value=lambda img:output):
        result=recognize(png())
    assert result['plate'] is None and result['needs_review']
    assert result['reason']==expected

def test_photo_checkin_checkout_and_protected_evidence(setup,monkeypatch,tmp_path):
    c,db,admin,user,spot,vehicle=setup
    monkeypatch.setattr(ai_service,'image_dir',lambda:tmp_path)
    monkeypatch.setattr(ai_service,'recognize',lambda *args:accepted())
    files={'file':('plate.png',png(),'image/png')}
    r=c.post('/ai/check-in',files=files,data={'parking_spot_id':spot.id});assert r.status_code==201,r.text
    data=r.json();sid=data['id'];assert float(data['entry_plate_confidence'])==.97
    assert c.get(data['entry_plate_image']).status_code==200
    monkeypatch.setattr(ai_service,'recognize',lambda *args:accepted('30A12345'))
    assert c.post(f'/ai/check-out/{sid}',files=files).status_code==409
    assert db.get(ParkingSession,sid).status=='ACTIVE'
    assert len(list(tmp_path.glob('*.jpg')))==1
    monkeypatch.setattr(ai_service,'recognize',lambda *args:accepted())
    r=c.post(f'/ai/check-out/{sid}',files=files);assert r.status_code==200,r.text
    assert r.json()['exit_plate_image'] and spot.status=='AVAILABLE'
    app.dependency_overrides[get_current_user]=lambda:user
    assert c.get(data['entry_plate_image']).status_code==403
    assert c.post('/ai/recognize',files=files).status_code==403

def test_review_and_unknown_vehicle_never_create_session(setup,monkeypatch,tmp_path):
    c,db,admin,user,spot,vehicle=setup
    monkeypatch.setattr(ai_service,'image_dir',lambda:tmp_path)
    files={'file':('plate.png',png(),'image/png')}
    monkeypatch.setattr(ai_service,'recognize',lambda *args:{'plate':None,'confidence':.4,'needs_review':True,'reason':'low_confidence'})
    assert c.post('/ai/check-in',files=files,data={'parking_spot_id':spot.id}).status_code==422
    monkeypatch.setattr(ai_service,'recognize',lambda *args:accepted('30A12345'))
    assert c.post('/ai/check-in',files=files,data={'parking_spot_id':spot.id}).status_code==404
    assert db.query(ParkingSession).count()==0 and spot.status=='AVAILABLE'
    assert list(tmp_path.iterdir())==[]

def test_failed_checkin_removes_evidence(setup,monkeypatch,tmp_path):
    c,db,admin,user,spot,vehicle=setup
    monkeypatch.setattr(ai_service,'image_dir',lambda:tmp_path)
    monkeypatch.setattr(ai_service,'recognize',lambda *args:accepted())
    spot.status='MAINTENANCE';db.commit()
    r=c.post('/ai/check-in',files={'file':('p.png',png(),'image/png')},data={'parking_spot_id':spot.id})
    assert r.status_code==409,r.text
    assert list(tmp_path.iterdir())==[]
    assert db.query(ParkingSession).count()==0

def test_bad_upload_and_roi_api(setup):
    c,*_=setup
    assert c.post('/ai/recognize',files={'file':('a.jpg',b'fake','image/jpeg')}).status_code==422
    assert c.post('/ai/recognize',files={'file':('a.png',png(),'image/png')},data={'roi':'a,b,c,d'}).status_code==422


@pytest.mark.skipif(__import__('os').getenv('RUN_AI_MODEL_TESTS')!='1',reason='Opt-in real OCR model smoke test')
def test_real_ocr_photo_roundtrip(setup,monkeypatch,tmp_path):
    c,db,admin,user,spot,vehicle=setup
    monkeypatch.setattr(ai_service,'image_dir',lambda:tmp_path)
    data=(Path(__file__).resolve().parents[2]/'ai_engine/examples/double.png').read_bytes()
    r=c.post('/ai/recognize',files={'file':('double.png',data,'image/png')})
    assert r.status_code==200 and r.json()['plate']=='59A112345',r.text
    r=c.post('/ai/check-in',files={'file':('double.png',data,'image/png')},data={'parking_spot_id':spot.id})
    assert r.status_code==201,r.text
    sid=r.json()['id']
    r=c.post(f'/ai/check-out/{sid}',files={'file':('double.png',data,'image/png')})
    assert r.status_code==200 and r.json()['status']=='COMPLETED',r.text
    assert len(list(tmp_path.glob('*.jpg')))==2
