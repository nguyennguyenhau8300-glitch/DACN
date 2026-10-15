import argparse
import json
from pathlib import Path
from .recognizer import recognize

def main():
    parser=argparse.ArgumentParser(description='Nhận diện biển số trên máy local')
    parser.add_argument('image',type=Path)
    parser.add_argument('--roi',type=int,nargs=4,metavar=('X','Y','WIDTH','HEIGHT'))
    args=parser.parse_args()
    print(json.dumps(recognize(args.image.read_bytes(),args.roi),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
