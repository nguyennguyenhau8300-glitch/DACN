"""Add the incident journal without changing parking or charging configuration."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import engine

if __name__ == '__main__':
    sql = (Path(__file__).resolve().parents[1] / 'database/alerts.sql').read_text(encoding='utf-8')
    with engine.begin() as conn:
        conn.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
        conn.exec_driver_sql(sql)
    print('Incident journal migration applied.')
