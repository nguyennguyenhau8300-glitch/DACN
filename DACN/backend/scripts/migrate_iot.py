"""Apply additive IoT migration to the configured database."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import engine

if __name__ == '__main__':
    sql = (Path(__file__).resolve().parents[1]/'database'/'iot.sql').read_text(encoding='utf-8')
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)
    print('IoT migration applied; parking data unchanged.')
