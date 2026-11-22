import sys,json,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import SessionLocal
from services.layout_service import initialize_layout

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--lot-id',type=int,required=True);args=parser.parse_args()
    with SessionLocal() as db:result=initialize_layout(db,args.lot_id)
    print(json.dumps(result,ensure_ascii=True,indent=2))
if __name__=='__main__':main()
