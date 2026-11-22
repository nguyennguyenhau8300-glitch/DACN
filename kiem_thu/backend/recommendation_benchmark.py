"""Evaluate Parkly's recommendation API on a disposable 95-spot PostgreSQL schema."""
import argparse
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import random
import secrets
import socket
from statistics import mean, median
import subprocess
import sys
from time import perf_counter, sleep
from uuid import uuid4

from dotenv import load_dotenv
import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[2] / 'DACN/backend'
sys.path.insert(0, str(BACKEND))
load_dotenv(BACKEND/'.env')
from database import engine
from models.operations import PricingRule
from models.parking_lot import ParkingLot
from models.parking_spot import ParkingSpot
from models.user import User
from models.vehicle import Vehicle
from services.auth_service import hash_password
from services.layout_service import initialize_layout


SEED = 20261120
GROUPS = {
    'CG': ('CAR', 'GASOLINE', '30F-20261'),
    'CE': ('CAR', 'ELECTRIC', '30F-20262'),
    'MG': ('MOTORBIKE', 'GASOLINE', '59B1-20263'),
    'ME': ('MOTORBIKE', 'ELECTRIC', '59B1-20264'),
}
MODES = {'drive': 0, 'balanced': 1, 'walk': 3}
EXPECTED_SPOTS = {'CG':20, 'CE':10, 'MG':40, 'ME':25}
CLOSED_AISLE = ('lane-4','lane-5')
INFINITY = Decimal('Infinity')


@dataclass(frozen=True)
class Spot:
    id: int
    code: str


@dataclass(frozen=True)
class Candidate:
    spot: Spot
    node: str
    drive: Decimal
    walk: Decimal

    def score(self, weight):
        return self.drive + weight * self.walk


class ReferenceDistances:
    """Independent Floyd–Warshall reference. A bay may be an endpoint only."""
    def __init__(self, graph):
        self.nodes = {node['id']: node for node in graph['nodes']}
        self.position = {name: i for i, name in enumerate(self.nodes)}
        self.spot_nodes = {n['spot_id']: n['id'] for n in self.nodes.values() if n['kind'] == 'SPOT'}
        self.entrance = next(n['id'] for n in self.nodes.values() if n['kind'] == 'ENTRANCE')
        self.destination = next(n['id'] for n in self.nodes.values() if n['kind'] == 'DESTINATION')
        self.edges = {}
        for edge in graph['edges']:
            if edge.get('blocked'):
                continue
            source, target = edge['source'], edge['target']
            pairs = [(source, target)] if edge.get('directed') else [(source, target), (target, source)]
            for pair in pairs:
                self.edges[pair] = min(Decimal(str(edge['distance'])), self.edges.get(pair, INFINITY))
        size = len(self.nodes)
        costs = [[INFINITY] * size for _ in range(size)]
        for i in range(size):
            costs[i][i] = Decimal(0)
        for (a, b), value in self.edges.items():
            costs[self.position[a]][self.position[b]] = value
        for name, node in self.nodes.items():
            if node['kind'] == 'SPOT':
                continue
            cross = self.position[name]
            onward = [(j, value) for j, value in enumerate(costs[cross]) if value.is_finite()]
            for row in costs:
                step = row[cross]
                if step.is_finite():
                    for j, value in onward:
                        length = step + value
                        if length < row[j]:
                            row[j] = length
        self.costs = costs

    def distance(self, start, end):
        return self.costs[self.position[start]][self.position[end]]

    def candidates(self, spots):
        found = []
        for spot in spots:
            node = self.spot_nodes[spot.id]
            drive = self.distance(self.entrance, node)
            walk = self.distance(node, self.destination)
            if drive.is_finite() and walk.is_finite():
                found.append(Candidate(spot, node, drive, walk))
        return found

    def route_length(self, path, start, end):
        assert path[0] == start and path[-1] == end, path
        assert all(self.nodes[node]['kind'] != 'SPOT' for node in path[1:-1]), path
        return sum(self.edges[pair] for pair in zip(path, path[1:]))

    def verify(self, response, eligible, weight):
        expected = sorted(eligible, key=lambda c: (c.score(weight), c.drive, c.spot.id))[:5]
        actual = response['candidates']
        assert response['entrance'] == self.entrance and response['destination'] == self.destination
        assert [r['spot_id'] for r in actual] == [c.spot.id for c in expected], (actual, expected)
        for row, candidate in zip(actual, expected, strict=True):
            assert row['spot_code'] == candidate.spot.code
            assert row['driving_distance'] == float(round(candidate.drive, 2))
            assert row['walking_distance'] == float(round(candidate.walk, 2))
            assert row['score'] == float(round(candidate.score(weight), 2))
            assert self.route_length(row['route'], self.entrance, candidate.node) == candidate.drive
            assert self.route_length(row['walking_route'], candidate.node, self.destination) == candidate.walk
        return expected


def expect(response, status=200):
    assert response.status_code == status, (response.request.url.path, response.status_code, response.text[:250])
    return response.json()


def auth(http, email, password):
    token = expect(http.post('/auth/login', json={'email':email,'password':password}))['access_token']
    return {'Authorization':'Bearer '+token}


def seed(db, password):
    pass_hash = hash_password(password)
    users = {
        email: User(email=email,full_name=name,role=role,password_hash=pass_hash)
        for email,name,role in (
            ('manager@example.com','Quản lý kiểm thử','MANAGER'),
            ('buyer@example.com','Khách kiểm thử','CUSTOMER'),
            ('other@example.com','Khách đồng thời','CUSTOMER'),
        )
    }
    db.add_all(users.values())
    lot = ParkingLot(name='Parkly 95 ô', address='Mặt bằng mô phỏng')
    db.add(lot)
    db.flush()
    initialize_layout(db, lot.id)
    buyer_id = users['buyer@example.com'].id
    vehicles = {}
    for code,(vehicle_type,energy_type,plate) in GROUPS.items():
        vehicles[code] = Vehicle(user_id=buyer_id,license_plate=plate,vehicle_type=vehicle_type,energy_type=energy_type)
        db.add(vehicles[code])
        db.add(PricingRule(parking_lot_id=lot.id,vehicle_type=vehicle_type,energy_type=energy_type,
                           first_hour_price=10000,additional_hour_price=5000))
    other = Vehicle(user_id=users['other@example.com'].id,license_plate='30F-20265',
                    vehicle_type='CAR',energy_type='GASOLINE')
    db.add(other)
    grouped = {code:[] for code in GROUPS}
    for spot in db.query(ParkingSpot).order_by(ParkingSpot.id):
        if spot.energy_type == 'ELECTRIC':
            spot.charger_status = 'READY'
        grouped[spot.spot_code[:2]].append(Spot(spot.id,spot.spot_code))
    db.commit()
    assert {g:len(spots) for g,spots in grouped.items()} == EXPECTED_SPOTS
    return lot.id, grouped, {code:v.id for code,v in vehicles.items()}, other.id


@contextmanager
def local_api(output):
    schema = 'recommendation_test_' + uuid4().hex
    with engine.begin() as conn:
        conn.execute(text('CREATE SCHEMA '+schema))
    url = engine.url.update_query_dict({'options': '-csearch_path='+schema+' -clock_timeout=5000 -cstatement_timeout=10000'})
    isolated = create_engine(url)
    process = None
    try:
        with isolated.begin() as conn:
            assert conn.exec_driver_sql('SELECT current_schema()').scalar_one() == schema
            conn.exec_driver_sql((BACKEND/'database/schema.sql').read_text(encoding='utf-8'))
            postgres = conn.exec_driver_sql('SHOW server_version').scalar_one().split()[0]
        password = secrets.token_urlsafe(16)
        with Session(isolated) as db:
            fixture = seed(db, password)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0))
            port = listener.getsockname()[1]
        env = {
            **os.environ,'DATABASE_URL':url.render_as_string(hide_password=False),
            'JWT_SECRET_KEY':secrets.token_urlsafe(48),'MQTT_ENABLED':'0','REDIS_URL':'',
            'PARKLY_SIMULATION_WORKER':'0','AI_DETECTOR_MODE':'ocr','PARKLY_API_PORT':str(port),
        }
        with (output/'backend.log').open('w',encoding='utf-8') as log:
            process = subprocess.Popen(
                [sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port',str(port),'--log-level','warning'],
                cwd=BACKEND, env=env, stdout=log, stderr=log, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
            )
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=12,trust_env=False) as http:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError('Backend stopped. See backend.log.')
                    try:
                        if http.get('/health/ready',timeout=1).is_success:
                            break
                    except httpx.HTTPError:
                        pass
                    sleep(.2)
                else:
                    raise RuntimeError('Backend is not ready. See backend.log.')
                yield http, isolated, fixture, password, postgres
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        isolated.dispose()
        with engine.begin() as conn:
            assert schema.startswith('recommendation_test_')
            conn.execute(text('DROP SCHEMA '+schema+' CASCADE'))


def occupancy(database, filled):
    with Session(database) as db:
        for spot in db.query(ParkingSpot):
            spot.status = 'OCCUPIED' if spot.id in filled else 'AVAILABLE'
        db.commit()


def get_recommendation(http, lot_id, vehicle_id, headers, weight=1):
    params = {'vehicle_id':vehicle_id,'walk_weight':weight}
    return expect(http.get(f'/parking-lots/{lot_id}/recommendation',params=params,headers=headers))


def save_graph(http, lot_id, manager, graph, revision):
    payload = {key:graph[key] for key in ('name','units','nodes','edges')}
    saved = expect(http.put(f'/parking-lots/{lot_id}/map',json={**payload,'revision':revision},headers=manager))
    assert saved['revision'] == revision+1
    return saved


def with_closed_aisle(graph):
    copy = deepcopy(graph)
    edge = next(e for e in copy['edges'] if (e['source'],e['target']) == CLOSED_AISLE)
    edge['blocked'] = True
    return copy


def case_rows(http, database, fixture, buyer, graph, map_label):
    lot_id, groups, vehicles, _ = fixture
    reference = ReferenceDistances(graph)
    rng = random.Random(SEED)
    rows = []
    occupancy(database,set())
    for category in groups:
        for weight in MODES.values():
            get_recommendation(http,lot_id,vehicles[category],buyer,weight)
    for target_rate,trials in ((0,1), (50,10), (80,10)):
        for trial in range(1,trials+1):
            filled = {
                spot.id for spots in groups.values()
                for spot in rng.sample(spots, (len(spots)*target_rate+50)//100)
            }
            occupancy(database,filled)
            for category,spots in groups.items():
                eligible = reference.candidates(s for s in spots if s.id not in filled)
                assert eligible
                first = min(eligible,key=lambda c:c.spot.code)
                shared = {'map':map_label,'target_pct':target_rate,'trial':trial,'occupied_spots':len(filled),
                          'group':category,'eligible_spots':len(eligible)}
                picks = [('first',first,None,0)]
                for name,weight in MODES.items():
                    started = perf_counter()
                    response = get_recommendation(http,lot_id,vehicles[category],buyer,weight)
                    elapsed = (perf_counter()-started)*1000
                    assert response['map_revision'] == graph['revision']
                    expected = reference.verify(response,eligible,weight)
                    picks.append((name,expected[0],elapsed,len(expected)))
                for mode,candidate,elapsed,verified in picks:
                    rows.append({**shared,'mode':mode,'spot':candidate.spot.code,'drive':float(candidate.drive),
                                 'walk':float(candidate.walk),'total':float(candidate.score(1)),
                                 'http_ms':None if elapsed is None else round(elapsed,3),'verified_candidates':verified})
    return rows


def scenarios(http, database, fixture, base_graph, manager, buyer, other, revision):
    lot_id,groups,vehicles,other_vehicle_id = fixture
    original = ReferenceDistances(base_graph)

    def save(graph):
        nonlocal revision
        saved = save_graph(http,lot_id,manager,graph,revision)
        revision = saved['revision']
        return saved

    def recommendation(category='CG'):
        return get_recommendation(http,lot_id,vehicles[category],buyer)

    occupancy(database,set())
    first = recommendation()['candidates'][0]
    node = original.spot_nodes[first['spot_id']]
    closed = deepcopy(base_graph)
    next(e for e in closed['edges'] if e['target'] == node)['blocked'] = True
    changed_ref = ReferenceDistances(save(closed))
    replacement = changed_ref.verify(recommendation(),changed_ref.candidates(groups['CG']),1)[0]
    assert replacement.spot.id != first['spot_id']
    blocked_case = {'before':first['spot_code'],'after':replacement.spot.code,'revision':revision}

    directed = deepcopy(base_graph)
    next(e for e in directed['edges'] if e['target'] == node)['directed'] = True
    directed_ref = ReferenceDistances(save(directed))
    assert directed_ref.distance('gate',node).is_finite() and not directed_ref.distance(node,'lift').is_finite()
    directed_result = directed_ref.verify(recommendation(),directed_ref.candidates(groups['CG']),1)
    assert first['spot_id'] not in [item.spot.id for item in directed_result]
    save(base_graph)
    assert recommendation()['candidates'][0]['spot_id'] == first['spot_id']

    same_spot = next(s for s in groups['CG'] if s.code == 'CG-006')
    occupancy(database,{s.id for s in groups['CG'] if s != same_spot})
    before = recommendation()['candidates'][0]
    alternate = ReferenceDistances(save(with_closed_aisle(base_graph)))
    after = alternate.verify(recommendation(),alternate.candidates([same_spot]),1)[0]
    assert after.spot.id == before['spot_id'] and float(after.drive) > before['driving_distance']
    reroute_case = {'spot':after.spot.code,'drive_before':before['driving_distance'],'drive_after':float(after.drive)}
    save(base_graph)
    occupancy(database,set())

    chosen = recommendation()['candidates'][0]
    server_clock = expect(http.get('/reservations/policy',headers=buyer))['server_time']
    start = (datetime.fromisoformat(server_clock)+timedelta(minutes=10)).isoformat()
    payload = {'parking_spot_id':chosen['spot_id'],'start_time':start}
    other_hold = expect(http.post('/reservations',headers=other,json={**payload,'vehicle_id':other_vehicle_id}),201)
    expect(http.post('/reservations',headers=buyer,json={**payload,'vehicle_id':vehicles['CG']}),409)
    available = [s for s in groups['CG'] if s.id != chosen['spot_id']]
    retry = original.verify(recommendation(),original.candidates(available),1)[0]
    retry_hold = expect(http.post('/reservations',headers=buyer,json={
        **payload,'parking_spot_id':retry.spot.id,'vehicle_id':vehicles['CG'],
    }),201)
    for actor,hold in ((buyer,retry_hold),(other,other_hold)):
        expect(http.patch(f"/reservations/{hold['id']}/cancel",headers=actor))

    electric = recommendation('CE')['candidates'][0]
    charger = f"/parking-spots/{electric['spot_id']}/charging-status"
    expect(http.patch(charger,json={'charger_status':'OFFLINE'},headers=manager))
    eligible = original.candidates(s for s in groups['CE'] if s.id != electric['spot_id'])
    electric_replacement = original.verify(recommendation('CE'),eligible,1)[0]
    expect(http.patch(charger,json={'charger_status':'READY'},headers=manager))
    occupancy(database,{s.id for s in groups['CE']})
    assert recommendation('CE')['candidates'] == []
    occupancy(database,set())
    return {
        'blocked_bay_access':blocked_case,'one_way_no_walking_exit':first['spot_code'],'reopened':first['spot_code'],
        'reroute':reroute_case,
        'changed_after_recommendation':{'before':chosen['spot_code'],'rejected_http':409,'new_spot':retry.spot.code,'retry_http':201},
        'charger_offline':{'before':electric['spot_code'],'after':electric_replacement.spot.code},
        'no_compatible_space':{'group':'CE','available':0,'returned':0},
    }


def summarize(rows):
    by_mode = {
        mode: {metric+'_mean':round(mean(r[metric] for r in rows if r['mode'] == mode),3)
               for metric in ('drive','walk','total')}
        for mode in ('first',*MODES)
    }
    comparisons = {}
    for baseline in ('first','drive'):
        a = [r['total'] for r in rows if r['mode'] == baseline]
        b = [r['total'] for r in rows if r['mode'] == 'balanced']
        relation = Counter('better' if y<x else 'worse' if y>x else 'equal' for x,y in zip(a,b,strict=True))
        comparisons[baseline] = {
            'better':relation['better'],'equal':relation['equal'],'worse':relation['worse'],
            'reduction_pct':round((sum(a)-sum(b))/sum(a)*100,3),
        }
    latency = sorted(r['http_ms'] for r in rows if r['http_ms'] is not None)
    return {
        'by_mode':by_mode,'balanced_comparisons':comparisons,
        'observations':len(rows)//4,'http_calls':len(latency),
        'verified_candidates':sum(r['verified_candidates'] for r in rows),
        'mean_ms':round(mean(latency),3),'median_ms':round(median(latency),3),
        'p95_ms':latency[math.ceil(0.95*len(latency))-1],
    }


def main(output):
    output.mkdir(parents=True,exist_ok=False)
    with local_api(output) as (http,database,fixture,password,postgres):
        manager,buyer,other = [
            auth(http,user+'@example.com',password) for user in ('manager','buyer','other')
        ]
        lot_id = fixture[0]
        graph = expect(http.get(f'/parking-lots/{lot_id}/map',headers=buyer))
        assert graph['schematic'] and graph['revision'] == 0 and graph['units'] == 'mét mô phỏng'
        normal = case_rows(http,database,fixture,buyer,graph,'open')
        closed_map = save_graph(http,lot_id,manager,with_closed_aisle(graph),graph['revision'])
        closure = case_rows(http,database,fixture,buyer,closed_map,'blocked')
        restored = save_graph(http,lot_id,manager,graph,closed_map['revision'])
        status = scenarios(http,database,fixture,graph,manager,buyer,other,restored['revision'])
    rows = normal+closure
    result = {
        'database':'PostgreSQL '+postgres,'api':'FastAPI on localhost','seed':SEED,
        'layout':{'spots':EXPECTED_SPOTS,'nodes':len(graph['nodes']),'edges':len(graph['edges']),'unit':graph['units']},
        'blocked_aisle':CLOSED_AISLE,
        'all':summarize(rows),
        'by_map':{
            label:{
                'all':summarize(cases),
                'by_occupancy':{str(rate):summarize([r for r in cases if r['target_pct'] == rate]) for rate in (0,50,80)},
                'by_group':{group:summarize([r for r in cases if r['group'] == group]) for group in GROUPS},
            }
            for label,cases in (('open',normal),('blocked',closure))
        },
        'checks':status,
    }
    with (output/'tung-ca-goi-y.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer = csv.DictWriter(file,fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    (output/'tong-ket.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'layout':result['layout'], 'open':summarize(normal), 'blocked':summarize(closure),
                      'checks':status},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    main(parser.parse_args().output.resolve())
