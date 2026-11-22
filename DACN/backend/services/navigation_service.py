"""Explicit weighted graph, Dijkstra distances and compatible spot ranking."""
import heapq
import math
from fastapi import HTTPException
from models.parking_spot import ParkingSpot
from models.parking_area import ParkingArea
from models.parking_lot import ParkingLot
from models.extensions import RoutingMap
from models.operations import PricingRule
from services.iot_service import devices_allow_entry, load_devices_for_availability
from services.parking_service import now


def lot_spots(db, lot_id):
    return db.query(ParkingSpot).join(ParkingArea).filter(ParkingArea.parking_lot_id == lot_id).order_by(ParkingSpot.id).all()


def validate_graph(graph, valid_spots):
    nodes, edges = graph['nodes'], graph['edges']
    by_id = {n['id']: n for n in nodes}
    if len(by_id) != len(nodes):
        raise HTTPException(422, 'Mã điểm phải duy nhất')
    attached = [n['spot_id'] for n in nodes if n.get('spot_id') is not None]
    if len(set(attached)) != len(attached) or not set(attached).issubset(valid_spots):
        raise HTTPException(422, 'Ô đỗ bị lặp hoặc không thuộc bãi')
    if not any(n['kind'] == 'ENTRANCE' for n in nodes) or not any(n['kind'] == 'DESTINATION' for n in nodes):
        raise HTTPException(422, 'Sơ đồ cần cổng vào và điểm đến đi bộ')
    for n in nodes:
        if (n['kind'] == 'SPOT') != (n.get('spot_id') is not None):
            raise HTTPException(422, 'Điểm SPOT cần liên kết đúng một ô đỗ')
    for e in edges:
        if e['source'] not in by_id or e['target'] not in by_id or e['source'] == e['target']:
            raise HTTPException(422, 'Liên kết có điểm không hợp lệ')


def schematic(spots):
    nodes = [{'id':'gate','kind':'ENTRANCE','label':'Cổng vào','x':4,'y':0},
             {'id':'lift','kind':'DESTINATION','label':'Lối đi bộ / thang máy','x':64,'y':0}]
    edges = []
    def edge(a, b):
        aa, bb = next(n for n in nodes if n['id']==a), next(n for n in nodes if n['id']==b)
        edges.append({'source':a,'target':b,'distance':round(math.hypot(aa['x']-bb['x'],aa['y']-bb['y']),2),'directed':False,'blocked':False})
    for i, spot in enumerate(spots):
        row, col = divmod(i, 10)
        lane = f'lane-{i}'
        nodes.extend([{'id':lane,'kind':'LANE','label':f'Lối đi {i+1}','x':4+col*6,'y':8+row*12},
                      {'id':f'spot-{spot.id}','kind':'SPOT','spot_id':spot.id,'label':spot.spot_code,'x':4+col*6,'y':12+row*12}])
        edge(lane, f'spot-{spot.id}')
        if col: edge(f'lane-{i-1}', lane)
        elif row: edge(f'lane-{i-10}', lane)
        else: edge('gate', lane)
        if col == 9 and row: edge(f'lane-{i-10}', lane)
    if spots:
        edge(f'lane-{min(9,len(spots)-1)}','lift')
    else:
        edge('gate','lift')
    return {'name':'Mặt bằng mô phỏng Parkly','units':'mét mô phỏng','nodes':nodes,'edges':edges}


def get_map(db, lot_id, *, spots=None):
    if not db.get(ParkingLot, lot_id): raise HTTPException(404, 'Không tìm thấy bãi')
    row = db.get(RoutingMap, lot_id)
    graph = row.graph if row else schematic(lot_spots(db, lot_id) if spots is None else spots)
    return {**graph,'parking_lot_id':lot_id,'revision':row.revision if row else 0,'schematic':row is None}


def shortest_paths(graph, start, reverse=False):
    adjacency = {n['id']:[] for n in graph['nodes']}
    terminal={n['id'] for n in graph['nodes'] if n.get('kind')=='SPOT'}
    if start not in adjacency: raise HTTPException(422, 'Điểm bắt đầu không thuộc sơ đồ')
    for e in graph['edges']:
        if e.get('blocked'): continue
        a,b = (e['target'],e['source']) if reverse else (e['source'],e['target'])
        adjacency[a].append((b,e['distance']))
        if not e.get('directed'): adjacency[b].append((a,e['distance']))
    distance, previous, queue = {start:0}, {}, [(0,start)]
    while queue:
        cost, node = heapq.heappop(queue)
        if cost != distance[node]: continue
        if node in terminal and node!=start: continue  # Never route through another parking bay.
        for target, weight in adjacency[node]:
            candidate = cost+weight
            if candidate < distance.get(target,math.inf):
                distance[target],previous[target] = candidate,node
                heapq.heappush(queue,(candidate,target))
    return distance, previous


def path(previous, start, end):
    result=[end]
    while result[-1] != start:
        if result[-1] not in previous: return []
        result.append(previous[result[-1]])
    return list(reversed(result))


def recommend(db, lot_id, vehicle, entrance=None, destination=None, walk_weight=1):
    lot=db.get(ParkingLot,lot_id)
    if not lot or not lot.is_active: raise HTTPException(409,'Bãi không hoạt động')
    spots = lot_spots(db, lot_id)
    graph=get_map(db,lot_id,spots=spots)
    by_id={n['id']:n for n in graph['nodes']}
    entrance=entrance or next(n['id'] for n in graph['nodes'] if n['kind']=='ENTRANCE')
    destination=destination or next(n['id'] for n in graph['nodes'] if n['kind']=='DESTINATION')
    if entrance not in by_id or by_id[entrance]['kind']!='ENTRANCE' or destination not in by_id or by_id[destination]['kind']!='DESTINATION':
        raise HTTPException(422,'Chọn đúng cổng vào và điểm đến')
    if not db.query(PricingRule.id).filter_by(parking_lot_id=lot_id,vehicle_type=vehicle.vehicle_type,energy_type=vehicle.energy_type,is_active=True).first():
        raise HTTPException(409,'Chưa có bảng giá cho loại xe')
    driving,prev=shortest_paths(graph,entrance)
    walking,walk_prev=shortest_paths(graph,destination,reverse=True)
    mapping={n['spot_id']:n['id'] for n in graph['nodes'] if n.get('spot_id') is not None}
    eligible = []
    for s in spots:
        node=mapping.get(s.id)
        if s.status!='AVAILABLE' or ('CAR' if s.spot_type=='DISABLED' else s.spot_type)!=vehicle.vehicle_type or s.energy_type!=vehicle.energy_type: continue
        if s.energy_type=='ELECTRIC' and s.charger_status!='READY': continue
        if node in driving and node in walking:
            eligible.append((s, node))
    devices, overheated = load_devices_for_availability(db, [spot.id for spot, _ in eligible])
    at = now()
    ranked = [
        (driving[node] + walk_weight * walking[node], driving[node], spot.id, spot.spot_code, node)
        for spot, node in eligible
        if devices_allow_entry(devices.get(spot.id, ()), at=at, overheated_ids=overheated)
    ]
    # Round only the response values, after selecting the five best candidates.
    ranked.sort()
    results=[
        {'spot_id':spot_id,'spot_code':code,'driving_distance':round(drive,2),
         'walking_distance':round(walking[node],2),'score':round(score,2),
         'route':path(prev,entrance,node),'walking_route':list(reversed(path(walk_prev,destination,node)))}
        for score,drive,spot_id,code,node in ranked[:5]
    ]
    return {'algorithm':'Dijkstra + weighted walking distance','vehicle_id':vehicle.id,'entrance':entrance,'destination':destination,
            'walk_weight':walk_weight,'units':graph['units'],'map_revision':graph['revision'],'candidates':results,
            'notice':'Gợi ý chưa giữ ô. Trạng thái sẽ được kiểm tra lại khi xác nhận đặt chỗ.'}
