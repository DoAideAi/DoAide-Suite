"""Isolated 1,200-record reporting fixture; no live records or providers are touched."""
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.catalog import CATALOG
from backend.db import database
from backend.operations import now


def check():
    with tempfile.TemporaryDirectory(prefix='doaide-report-check-') as folder:
        path=Path(folder)/'fixture.db'
        with TestClient(create_app(path)) as client:
            client.post('/api/auth/register',json={'email':'fixture@example.test','password':'synthetic-report-check-password'})
            owner=client.get('/api/auth/me').json();timestamp=now()
            with database(path) as db:
                for slug,product in CATALOG.items():
                    for index in range(100):
                        identifier=str(uuid4())
                        db.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?)',(identifier,owner['id'],slug,f'{product["name"]} fixture {index}',json.dumps(product['sample']),'draft',1,timestamp,timestamp))
                        db.execute('INSERT INTO record_workspaces VALUES (?,?)',(identifier,owner['workspace_id']))
            timings=[]
            for _ in range(3):
                start=time.perf_counter();response=client.get('/api/reports/portfolio');timings.append(round(time.perf_counter()-start,4))
                assert response.status_code==200,response.text
                result=response.json();assert result['total_records']==1200 and result['truncated']
                assert all(total['records']==100 for total in result['totals'].values())
            csv=client.get('/api/reports/portfolio.csv');assert csv.status_code==200
            import csv as csv_module,io
            assert len(list(csv_module.reader(io.StringIO(csv.text))))==1201
            with database(path) as db:
                assert db.execute('SELECT count(*) FROM operations').fetchone()[0]==0
                assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            return {'fixture_records':1200,'products':12,'requests':3,'seconds':timings,'median_seconds':statistics.median(timings),'csv_rows':1200,'report_reads_created_no_workflows':True,'integrity':'ok','scope':'Local isolated single-process benchmark, not production load acceptance'}


if __name__=='__main__':print(json.dumps(check(),indent=2))
