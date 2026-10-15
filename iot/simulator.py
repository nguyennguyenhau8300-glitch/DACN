"""HTTP IoT simulator. Run with backend/venv/Scripts/python.exe. No hardware required."""
import argparse
from contextlib import contextmanager
from getpass import getpass
import json
import os
from pathlib import Path
import sys
import time
import httpx

DEFAULT_CONFIG = Path(__file__).with_name('devices.local.json')


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


@contextmanager
def exclusive(config_path):
    lock = Path(str(config_path)+'.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError(f'Đã có tiến trình dùng cấu hình này. Nếu tiến trình đã dừng, xóa {lock}') from None
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def request_json(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.status_code >= 400:
        # Never print request headers, credentials, tokens, or full request objects.
        raise RuntimeError(f'{method} {path}: HTTP {response.status_code}: {response.text[:300]}')
    return response.json()


def configure(client, token, lot_id, config_path):
    headers = {'Authorization':'Bearer '+token}
    spots = request_json(client, 'GET', '/parking-spots', params={'parking_lot_id':lot_id}, headers=headers)
    if not spots:
        raise RuntimeError('Bãi chưa có ô đỗ; tạo sơ đồ bãi trước')
    existing = request_json(client, 'GET', '/iot/devices', params={'parking_lot_id':lot_id}, headers=headers)
    bindings = {(d['parking_spot_id'],d['kind']):d for d in existing}
    path = Path(config_path)
    config = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
        'base_url':str(client.base_url).rstrip('/'), 'parking_lot_id':lot_id, 'devices':[]}
    if config['parking_lot_id'] != lot_id or config['base_url'].rstrip('/') != str(client.base_url).rstrip('/'):
        raise RuntimeError('File cấu hình thuộc bãi hoặc server khác; dùng file mới')
    local = {d['device_code']:d for d in config['devices']}
    missing = []
    for spot in spots:
        for kind in (['SENSOR','CHARGER'] if spot['energy_type']=='ELECTRIC' else ['SENSOR']):
            binding = bindings.get((spot['id'],kind))
            if binding:
                if binding['device_code'] not in local:
                    missing.append(binding['device_code'])
                continue
            code = f"SIM-{kind}-{spot['id']}"
            device = request_json(client, 'POST', '/iot/devices', headers=headers,
                                  json={'device_code':code,'parking_spot_id':spot['id'],'kind':kind})
            config['devices'].append({'device_code':code,'api_key':device['api_key'],
                                      'parking_spot_id':spot['id'],'kind':kind,
                                      'vehicle_type':spot['spot_type'],'energy_type':spot['energy_type'],
                                      'sequence':0,'energy_kwh':0.0,'pending':None})
            save_json(path, config)  # Keys are issued once; checkpoint after every registration.
    if missing:
        raise RuntimeError(f'{len(missing)} thiết bị đã tồn tại nhưng thiếu khóa trong file. Khôi phục file hoặc dùng rotate-key để cấp lại khóa.')
    save_json(path, config)
    return config


def make_payload(device, scenario, round_index):
    sequence = device['sequence'] + 1
    if device['kind'] == 'SENSOR':
        occupied = scenario == 'cycle' and round_index % 3 == 1
        return {'sequence':sequence,'sensor_status':'OCCUPIED' if occupied else 'AVAILABLE'}
    status = 'FAULT' if scenario == 'charger-fault' else 'CHARGING' if scenario == 'cycle' and round_index % 3 == 1 else 'READY'
    power = (0.5 if device['vehicle_type']=='MOTORBIKE' else 7.0) if status == 'CHARGING' else 0.0
    # Artificial meter values, not measurements or billable energy.
    energy = round(device.get('energy_kwh',0.0) + (0.01 if power else 0), 3)
    return {'sequence':sequence,'charger_status':status,'power_kw':power,'energy_kwh':energy}


def send_telemetry(client, code, key, payload, retries=3):
    for attempt in range(retries):
        try:
            response = client.post(f'/iot/devices/{code}/telemetry', headers={'X-API-Key':key}, json=payload)
            if response.status_code not in (500,502,503,504):
                if response.status_code >= 400:
                    raise RuntimeError(f'{code}: HTTP {response.status_code}: {response.text[:200]}')
                return response.json()
        except httpx.TransportError:
            pass
        if attempt+1 < retries:
            time.sleep(min(2**attempt, 4))
    raise RuntimeError(f'{code}: server không phản hồi; giữ nguyên bản tin để gửi lại')


def run_round(client, config, config_path, scenario, round_index):
    accepted = duplicates = 0
    for device in config['devices']:
        payload = device.get('pending') or make_payload(device, scenario, round_index)
        device['pending'] = payload
        save_json(config_path, config)  # Persist BEFORE sending, including across process restarts.
        result = send_telemetry(client, device['device_code'], device['api_key'], payload)
        device['sequence'] = payload['sequence']
        device['energy_kwh'] = payload.get('energy_kwh',0.0)
        device['pending'] = None
        save_json(config_path, config)
        accepted += 1; duplicates += int(result['duplicate'])
    return {'sent':accepted,'duplicates':duplicates}


def main():
    parser = argparse.ArgumentParser(description='Mô phỏng cảm biến ô đỗ và điểm sạc qua HTTP')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    sub = parser.add_subparsers(dest='command', required=True)
    setup = sub.add_parser('configure', help='Đăng nhập quản lý, đăng ký một cảm biến/ô và một thiết bị/điểm sạc')
    setup.add_argument('--url', default='http://127.0.0.1:8001')
    setup.add_argument('--lot-id', type=int, default=1)
    run = sub.add_parser('run', help='Gửi dữ liệu mô phỏng; thay đổi trạng thái trên bãi đã chọn')
    run.add_argument('--rounds', type=int, default=3)
    run.add_argument('--interval', type=float, default=10)
    run.add_argument('--scenario', choices=['idle','cycle','charger-fault'], default='idle')
    sub.add_parser('heartbeat', help='Chỉ gửi nhịp sống; không làm mới số đo')
    args = parser.parse_args()
    if args.command=='run' and (args.rounds<1 or args.interval<0):
        parser.error('rounds >= 1 và interval >= 0')
    with exclusive(args.config):
        if args.command=='configure':
            with httpx.Client(base_url=args.url, timeout=15, follow_redirects=False) as client:
                email = input('Email ADMIN/MANAGER: ').strip()
                token = request_json(client,'POST','/auth/login',json={'email':email,'password':getpass('Mật khẩu: ')})['access_token']
                config = configure(client, token, args.lot_id, args.config)
                print(f"Đã lưu {len(config['devices'])} thiết bị vào {args.config}. File chứa khóa riêng; không chia sẻ.")
        else:
            config = json.loads(args.config.read_text(encoding='utf-8'))
            with httpx.Client(base_url=config['base_url'], timeout=15, follow_redirects=False) as client:
                if args.command=='heartbeat':
                    for d in config['devices']:
                        request_json(client,'POST',f"/iot/devices/{d['device_code']}/heartbeat",headers={'X-API-Key':d['api_key']})
                    print(f"Đã gửi heartbeat: {len(config['devices'])} thiết bị")
                else:
                    for index in range(args.rounds):
                        print(f'Vòng {index+1}: {run_round(client,config,args.config,args.scenario,index)}', flush=True)
                        if index+1 < args.rounds: time.sleep(args.interval)

if __name__=='__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Đã dừng; bản tin chưa xác nhận được lưu để gửi lại.')
    except (RuntimeError, OSError, ValueError, httpx.TransportError) as exc:
        print(f'Lỗi mô phỏng: {exc}', file=sys.stderr)
        sys.exit(1)
