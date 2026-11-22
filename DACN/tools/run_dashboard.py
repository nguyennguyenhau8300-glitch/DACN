"""Start the API and built dashboard together on localhost."""
import argparse
import os
from pathlib import Path
import sys
import uvicorn

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description='Khởi động backend và giao diện Parkly')
parser.add_argument('--port',type=int,default=8001)
parser.add_argument('--lan',action='store_true',help='Cho phép điện thoại cùng mạng kết nối bằng IP của máy tính')
args=parser.parse_args()
if not 1<=args.port<=65535:parser.error('Cổng phải nằm trong 1–65535')
if not (root/'web_dashboard/dist/index.html').is_file():
    parser.error('Chưa build frontend. Chạy npm install và npm run build trong web_dashboard trước.')
os.chdir(root/'backend')
sys.path.insert(0,str(root/'backend'))
print(f'Mở giao diện tại http://127.0.0.1:{args.port}/dashboard/',flush=True)
if args.lan:
    print(f'Cho phép kết nối mạng nội bộ ở cổng {args.port}; điện thoại dùng IP của máy tính.',flush=True)
uvicorn.run('main:app',host='0.0.0.0' if args.lan else '127.0.0.1',port=args.port)
