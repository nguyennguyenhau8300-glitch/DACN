"""Add proposal features; no existing business data is changed."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import prepare_schema

if __name__=='__main__':
    prepare_schema()
    print('Proposal extension migration applied.')
