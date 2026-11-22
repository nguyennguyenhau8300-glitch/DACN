"""Temporary HTTPS access for the Android demo; keep the computer online.

Uses an official, checksum-verified cloudflared binary. No router port forwarding,
Cloudflare account, changes to database credentials, or Android rebuild required.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent / 'work' / 'internet-demo'
STATE = WORK / 'state.json'
VERSION = '2026.10.7'
SHA256 = '2493dbc168923bb3e59e5e7716f71deced92992eea9acd6e9d74f84ac7751343'
DOWNLOAD = f'https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/cloudflared-windows-amd64.exe'
BINARY = ROOT.parent / 'cong_cu_phat_trien/tools/bin/cloudflared/cloudflared.exe'
ORIGIN = 'http://127.0.0.1:8002'


def write_state(value):
    WORK.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(STATE)


def read_state():
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def owns_process(state):
    pid = state.get('pid')
    if type(pid) is not int or pid <= 0 or state.get('status') == 'STOPPED':
        return False
    # Verify the executable and unique log argument before reusing/stopping a PID.
    command = (f'Get-CimInstance Win32_Process -Filter "ProcessId = {pid}" | '
               'Select-Object ExecutablePath,CommandLine | ConvertTo-Json -Compress')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                            capture_output=True, text=True, timeout=15,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        info = json.loads(result.stdout)
        return (str(info.get('ExecutablePath', '')).casefold() == str(BINARY).casefold()
                and str(state.get('log', '')) in info.get('CommandLine', '')
                and bool(state.get('log')))
    except (ValueError, TypeError, AttributeError):
        return False


def ready(url):
    try:
        with urllib.request.urlopen(url + '/health/ready', timeout=5) as response:
            return response.status == 200 and json.load(response).get('status') == 'ready'
    except (OSError, ValueError, urllib.error.URLError):
        return False


def install():
    if BINARY.is_file() and hashlib.sha256(BINARY.read_bytes()).hexdigest() == SHA256:
        return
    BINARY.parent.mkdir(parents=True, exist_ok=True)
    temporary = BINARY.with_suffix('.download')
    print('Dang tai Cloudflare Tunnel tu nguon chinh thuc (khoang 55 MB)...', flush=True)
    try:
        request = urllib.request.Request(DOWNLOAD, headers={'User-Agent': 'Parkly-DACN-demo'})
        digest = hashlib.sha256()
        with urllib.request.urlopen(request, timeout=30) as response, temporary.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != SHA256:
            raise RuntimeError('Cloudflared checksum mismatch; khong chay file vua tai.')
        temporary.replace(BINARY)
        (BINARY.parent / 'provenance.json').write_text(json.dumps({
            'version': VERSION, 'url': DOWNLOAD, 'sha256': SHA256,
            'documentation': 'https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/'
        }, indent=2), encoding='utf-8')
    finally:
        temporary.unlink(missing_ok=True)


def show(url):
    instructions = ('PARKLY ANDROID - DEMO KHAC MANG\n\n'
                    f'Tai APK tren dien thoai: {url}/mobile.apk\n'
                    f'Dia chi backend nhap trong app: {url}\n'
                    f'Web neu can: {url}/dashboard/\n\n'
                    'App: Cau hinh may chu > Dia chi backend > Kiem tra ket noi > Luu dia chi.\n'
                    'Khong them /dashboard vao dia chi backend. Dang nhap lai sau khi doi may chu.\n'
                    'Dien thoai co the dung Wi-Fi khac hoac 4G/5G.\n'
                    'May tinh phai bat, co Internet va backend dang chay.\n'
                    'URL tam co the doi sau khi dong/chay lai tunnel.\n'
                    'Dung ket noi: tools/DUNG_APP_KHAC_MANG.bat\n')
    (WORK / 'KET_NOI_DIEN_THOAI.txt').write_text(instructions, encoding='utf-8')
    print(instructions, flush=True)
    print('Da luu huong dan tai:', WORK / 'KET_NOI_DIEN_THOAI.txt')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--stop', action='store_true')
    mode.add_argument('--status', action='store_true')
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    state = read_state()
    owned = owns_process(state)
    if args.stop:
        if owned:
            os.kill(state['pid'], signal.SIGTERM)
        state.update(status='STOPPED', stopped_at=datetime.now(timezone.utc).isoformat())
        write_state(state)
        print('Da tat tunnel demo. Backend tren may tinh van duoc giu nguyen.')
        return
    if args.status:
        print(json.dumps({'running': owned, 'url': state.get('url') if owned else None,
                          'origin': ORIGIN, 'backend_ready': ready(ORIGIN)}))
        return
    subprocess.run([sys.executable, str(ROOT / 'tools/start_proposal.py')], cwd=ROOT, check=True)
    if owned and state.get('url') and ready(state['url']):
        show(state['url'])
        return
    if owned:
        raise RuntimeError('Tunnel dang khoi dong/ket noi lai. Cho mot chut va chay lai; hoac dung DUNG_APP_KHAC_MANG.bat truoc.')
    install()
    log = WORK / ('cloudflared-' + uuid4().hex + '.log')
    console = log.with_suffix('.console.log')
    with console.open('w', encoding='utf-8') as output:
        process = subprocess.Popen([
            str(BINARY), 'tunnel', '--no-autoupdate', '--url', ORIGIN,
            '--protocol', 'http2', '--logfile', str(log), '--loglevel', 'info'
        ], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    state = {'pid': process.pid, 'log': str(log), 'status': 'STARTING',
             'started_at': datetime.now(timezone.utc).isoformat(), 'origin': ORIGIN}
    write_state(state)
    print('Dang mo duong dan HTTPS cho app Android...', flush=True)
    deadline = time.monotonic() + 100
    url = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'Tunnel dung khi khoi dong. Xem {log} va {console}')
        contents = '\n'.join(p.read_text(encoding='utf-8', errors='replace')
                             for p in [log, console] if p.exists())
        found = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', contents)
        if found:
            url = found.group()
            if state.get('url') != url:
                state['url'] = url
                write_state(state)
            if ready(url):
                state['status'] = 'READY'
                write_state(state)
                show(url)
                return
        time.sleep(1)
    raise RuntimeError(f'Chua xac minh duoc HTTPS. URL: {url or "chua co"}. Xem {log}; thu chay lai.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
