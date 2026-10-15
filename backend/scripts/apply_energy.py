import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import engine
sql=(Path(__file__).resolve().parents[2]/'database/energy_charging.sql').read_text(encoding='utf-8')
with engine.begin() as conn:conn.exec_driver_sql(sql)
print('Energy and charging migration applied')
