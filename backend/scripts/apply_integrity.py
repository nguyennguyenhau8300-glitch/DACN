import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import engine
from sqlalchemy import text
sql=(Path(__file__).resolve().parents[2]/'database'/'backend_integrity.sql').read_text(encoding='utf-8')
with engine.begin() as conn:
    for statement in sql.split(';'):
        if statement.strip(): conn.execute(text(statement))
print('Integrity indexes applied')
