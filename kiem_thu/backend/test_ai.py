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


def test_holdout_audit_detects_shared_captures_and_reused_pixels(tmp_path):
    from ai_engine.split_audit import audit_holdout

    labels = []
    for index, split in enumerate(('train', 'val', 'test'), 1):
        file = tmp_path / f'{split}.png'
        Image.new('RGB', (20, 20), (10 * index, 0, 0)).save(file)
        labels.append({'image': file.name, 'split': split, 'plate': f'51A-10{index}00',
                       'vehicle_group': f'vehicle-{index}', 'capture_session': f'capture-{index}',
                       'camera_id': f'camera-{index}', 'label_source': 'manual'})
    assert audit_holdout(labels, tmp_path)['passed']
    labels[2]['capture_session'] = labels[0]['capture_session']
    labels[2]['camera_id'] = labels[1]['camera_id'].upper()
    labels[2]['plate'] = labels[0]['plate'].replace('-', '')
    (tmp_path / 'test.png').write_bytes((tmp_path / 'train.png').read_bytes())
    audit = audit_holdout(labels, tmp_path)
    assert not audit['passed']
    assert audit['overlap']['train:test'] == {
        'image_sha256': 1, 'plate': 1, 'vehicle_group': 0, 'capture_session': 1, 'camera_id': 0,
    }
    assert audit['overlap']['val:test']['camera_id'] == 1
    labels[2]['roi'] = [0, 0, 10, 10]
    with pytest.raises(ValueError, match='ảnh nguyên khung'):
        audit_holdout(labels, tmp_path)


def test_evaluator_exports_wrong_reads_separately_from_review_and_blank(tmp_path, monkeypatch):
    import csv
    from ai_engine import evaluate

    image = tmp_path / 'image.png'
    image.write_bytes(png())
    def recognize_photo(_image, roi, *, uploaded_photo):
        assert uploaded_photo and roi is None
        return {**accepted('59A112346'), 'elapsed_ms': 50.0}
    monkeypatch.setattr(evaluate, 'recognize', recognize_photo)
    row = evaluate.score_image({'image': image.name, 'plate': '59-A1 123.45', 'condition': 'mờ'}, tmp_path, photo=True)
    assert row['outcome'] == 'wrong_plate_accepted' and not row['needs_review']
    summary = evaluate.summarize([row])
    assert summary['conditions'] == {'mờ': {'wrong_plate_accepted': 1}}
    assert summary['wrong_accepts'] == 1 and summary['character_error_rate'] == 1 / 9
    assert evaluate.plate_outcome('59A112345', None) == 'review_required'
    assert evaluate.plate_outcome(None, None) == 'correct_rejection'
    errors = tmp_path / 'errors.csv'
    evaluate.write_errors(errors, [row])
    with errors.open(encoding='utf-8-sig', newline='') as file:
        assert list(csv.DictReader(file))[0]['predicted'] == '59A112346'

def test_group_two_line_plate_and_order():
    candidates,_=collect_candidates(['123.45','59A1'],[.96,.95],[box(30,80,150,40),box(40,10,120,40)])
    assert [c['plate'] for c in candidates]==['59A112345']
    assert candidates[0]['confidence']==.95

@pytest.mark.parametrize('second_row_y,expected',[(673,['62N191400']),(560,[])])
def test_group_tilted_motorbike_plate_with_slight_row_overlap(second_row_y,expected):
    candidates,_=collect_candidates(['62-N1','914.00'],[.99,.98],
        [box(617,354,889,450),box(541,second_row_y,1033,446)])
    assert [candidate['plate'] for candidate in candidates]==expected

def test_no_merge_distant_plates_or_guess():
    c,_=collect_candidates(['59A1','12345','30A-888.88'],[.99]*3,[box(10,10,100,30),box(900,400,100,30),box(400,10,200,30)])
    assert [v['plate'] for v in c]==['30A88888']
    assert normalize_plate('59-A1 123.45')=='59A112345'
    c,_=collect_candidates(['3OA12345'],[.99],[box(0,0,100,40)])
    assert c==[]

def test_detected_plate_crop_combines_rows_with_overlapping_ocr_boxes():
    boxes=[box(25,9,69,43),box(17,33,80,47)]
    candidates,_=collect_candidates(['59-X1','374.38'],[.95,.99],boxes,single_plate_crop=True)
    assert [candidate['plate'] for candidate in candidates]==['59X137438']
    candidates,_=collect_candidates(['59-X1','374.38'],[.95,.99],boxes)
    assert candidates==[]

def test_ocr_middle_dot_is_a_plate_separator():
    candidates,_=collect_candidates(['51A·853.25'],[.95],[box(10,10,100,30)])
    assert [candidate['plate'] for candidate in candidates]==['51A85325']

@pytest.mark.parametrize('x,expected',[(32,'51A85325'),(250,None)])
def test_cropped_photo_can_retry_only_the_same_plate(x,expected):
    from types import SimpleNamespace
    detector=[{'box':[20,30,145,110],'confidence':.95}]
    partial=SimpleNamespace(txts=['853.25'],scores=[.99],boxes=[box(10,10,65,24)])
    full=SimpleNamespace(txts=['51A-853.25'],scores=[.99],boxes=[box(x,45,110,32)])
    with patch('ai_engine.detector.detect',return_value=detector), \
         patch('ai_engine.recognizer._get_engine') as engine:
        engine.return_value.side_effect=[partial,full]
        result=recognize(png(),uploaded_photo=True)
    assert result['plate']==expected
    assert result['needs_review']==(expected is None)
    assert engine.return_value.call_count==2

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
    monkeypatch.setattr(ai_service,'recognize',lambda *args, **kwargs:accepted())
    files={'file':('plate.png',png(),'image/png')}
    r=c.post('/ai/check-in',files=files,data={'parking_spot_id':spot.id});assert r.status_code==201,r.text
    data=r.json();sid=data['id'];assert float(data['entry_plate_confidence'])==.97
    assert c.get(data['entry_plate_image']).status_code==200
    monkeypatch.setattr(ai_service,'recognize',lambda *args, **kwargs:accepted('30A12345'))
    assert c.post(f'/ai/check-out/{sid}',files=files).status_code==409
    assert db.get(ParkingSession,sid).status=='ACTIVE'
    assert len(list(tmp_path.glob('*.jpg')))==1
    monkeypatch.setattr(ai_service,'recognize',lambda *args, **kwargs:accepted())
    r=c.post(f'/ai/check-out/{sid}',files=files);assert r.status_code==200,r.text
    assert r.json()['exit_plate_image'] and spot.status=='AVAILABLE'
    app.dependency_overrides[get_current_user]=lambda:user
    assert c.get(data['entry_plate_image']).status_code==403
    assert c.post('/ai/recognize',files=files).status_code==403

def test_review_and_unknown_vehicle_never_create_session(setup,monkeypatch,tmp_path):
    c,db,admin,user,spot,vehicle=setup
    monkeypatch.setattr(ai_service,'image_dir',lambda:tmp_path)
    files={'file':('plate.png',png(),'image/png')}
    monkeypatch.setattr(ai_service,'recognize',lambda *args, **kwargs:{'plate':None,'confidence':.4,'needs_review':True,'reason':'low_confidence'})
    assert c.post('/ai/check-in',files=files,data={'parking_spot_id':spot.id}).status_code==422
    monkeypatch.setattr(ai_service,'recognize',lambda *args, **kwargs:accepted('30A12345'))
    assert c.post('/ai/check-in',files=files,data={'parking_spot_id':spot.id}).status_code==404
    assert db.query(ParkingSession).count()==0 and spot.status=='AVAILABLE'
    assert list(tmp_path.iterdir())==[]

def test_failed_checkin_removes_evidence(setup,monkeypatch,tmp_path):
    c,db,admin,user,spot,vehicle=setup
    monkeypatch.setattr(ai_service,'image_dir',lambda:tmp_path)
    monkeypatch.setattr(ai_service,'recognize',lambda *args, **kwargs:accepted())
    spot.status='MAINTENANCE';db.commit()
    r=c.post('/ai/check-in',files={'file':('p.png',png(),'image/png')},data={'parking_spot_id':spot.id})
    assert r.status_code==409,r.text
    assert list(tmp_path.iterdir())==[]
    assert db.query(ParkingSession).count()==0

def test_bad_upload_and_roi_api(setup):
    c,*_=setup
    assert c.post('/ai/recognize',files={'file':('a.jpg',b'fake','image/jpeg')}).status_code==422
    assert c.post('/ai/recognize',files={'file':('a.png',png(),'image/png')},data={'roi':'a,b,c,d'}).status_code==422


def test_vehicle_preview_matches_the_plate_not_an_adjacent_vehicle(monkeypatch):
    from ai_engine import detector, vehicle_context
    from services.ai_service import preview_vehicle

    image=Image.new('RGB',(400,200),'white')
    motorbike={'type':'MOTORBIKE','box':[20,20,180,190],'confidence':.8}
    car={'type':'CAR','box':[200,0,400,199],'confidence':.95}
    monkeypatch.setattr(detector,'detect_vehicles',lambda image:[motorbike,car])
    monkeypatch.setattr(vehicle_context,'classify_context',lambda *_:None)
    result=preview_vehicle(image,[70,90,140,140],accepted())
    assert result['type']=='MOTORBIKE' and result['reason']=='matched_plate'
    assert preview_vehicle(image,None,{'reason':'multiple_plates'})['type'] is None
    assert preview_vehicle(image,[183,90,197,140],accepted())['type'] is None
    monkeypatch.setattr(vehicle_context,'classify_context',lambda *_:{'type':'CAR','confidence':.99})
    assert preview_vehicle(image,[70,90,140,140],accepted())['reason']=='inconsistent_vehicle_type'


def test_photo_preprocessing_rejects_different_plate_strings(monkeypatch):
    from PIL import ImageDraw
    from ai_engine import recognizer

    image=Image.new('RGB',(180,75),'white')
    ImageDraw.Draw(image).rectangle((20,15,140,60),fill='black')
    first={'plate':'51A12345','confidence':.95,'box':[20,15,140,60]}
    conflicting={**first,'plate':'51A12845','confidence':.98}
    monkeypatch.setattr(recognizer,'read_plate_text',lambda *a,**kw:([conflicting.copy()],[],False))
    _,needs_review=recognizer.confirm_photo_read(image,0,0,[first],detected_crop=True,minimum=.85)
    assert needs_review


@pytest.mark.parametrize('detections,expected_plate',[
    ([], '62N191400'),
    ([{'box':[20,15,170,100]}, {'box':[220,30,370,115]}], None),
])
def test_photo_upload_fallback_preserves_ambiguity(setup,detections,expected_plate):
    from types import SimpleNamespace
    client,db,*_=setup
    output=SimpleNamespace(txts=['62-N1','914.00'],scores=[.99,.98],
        boxes=[box(30,15,130,50),box(20,50,150,50)])
    with patch('ai_engine.detector.detect',return_value=detections), \
         patch('ai_engine.recognizer._get_engine',return_value=lambda image:output) as ocr:
        response=client.post('/ai/recognize',files={'file':('plate.png',png(),'image/png')})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['plate']==expected_plate
    assert result['needs_review']==bool(detections)
    if detections:
        ocr.assert_not_called()
        assert result['reason']=='multiple_plates'
    else:
        ocr.assert_called_once()
        assert result['bounding_box']==[20,15,170,100]
        assert result['cropped_image'].startswith('data:image/jpeg;base64,')
    assert db.query(ParkingSession).count()==0


@pytest.mark.skipif(__import__('os').getenv('RUN_AI_MODEL_TESTS')!='1',reason='Opt-in real OCR model smoke test')
def test_real_ocr_photo_roundtrip(setup,monkeypatch,tmp_path):
    c,db,admin,user,spot,vehicle=setup
    monkeypatch.setattr(ai_service,'image_dir',lambda:tmp_path)
    data=(Path(__file__).resolve().parents[1]/'fixtures/ai_engine/double.png').read_bytes()
    r=c.post('/ai/recognize',files={'file':('double.png',data,'image/png')})
    assert r.status_code==200 and r.json()['plate']=='59A112345',r.text
    r=c.post('/ai/check-in',files={'file':('double.png',data,'image/png')},data={'parking_spot_id':spot.id})
    assert r.status_code==201,r.text
    sid=r.json()['id']
    r=c.post(f'/ai/check-out/{sid}',files={'file':('double.png',data,'image/png')})
    assert r.status_code==200 and r.json()['status']=='COMPLETED',r.text
    assert len(list(tmp_path.glob('*.jpg')))==2
