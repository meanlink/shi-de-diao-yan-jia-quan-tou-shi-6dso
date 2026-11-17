import time, json, logging
from pathlib import Path
from sqlalchemy import select
from redis import Redis
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models import Job, Dataset, Report, RuleVersion, ReplayItem
from src.services.business import analyze
from src.services.reports import deliver
from src.services.rules import execute_item, ensure_baseline
from src.services.audit import record
logging.basicConfig(level=logging.INFO)
def execute(job_id):
    with Session() as db:
        j=db.get(Job,job_id)
        if not j or j.status!='queued':return
        j.status='running'; db.commit()
        try:
            d=db.get(Dataset,j.dataset_id)
            rule=db.get(RuleVersion,j.rule_version_id) if j.rule_version_id else ensure_baseline(db)
            result=analyze(d.records,j.params,rule.definition)
            result['rule']={'id':rule.id,'version':rule.version,'label':rule.label,'fpc':bool(rule.definition.get('fpc'))}
            json.dumps(result,allow_nan=False)
            j.result=result;j.status='completed';j.finished_at=time.time()
            record(db,'worker','job.completed',{'id':j.id,'rule_version':rule.version})
        except Exception as e:
            logging.exception('Analysis failed')
            j.status='failed';j.error=str(e)[:990];j.finished_at=time.time()
            record(db,'worker','job.failed',{'id':j.id,'error':j.error})
        db.commit()
def replay(item_id):
    with Session() as db:
        try:
            outcome=execute_item(db,item_id)
            if outcome:record(db,'worker','replay.item.'+outcome,{'item':item_id});db.commit()
        except Exception:
            logging.exception('Replay item failed')
def tick():
    with Session() as db:
        queued=list(db.scalars(select(Job.id).where(Job.status=='queued').limit(3)))
    for job_id in queued:execute(job_id)
    with Session() as db:
        pending=list(db.scalars(select(ReplayItem.id).where(ReplayItem.status=='pending').limit(3)))
    for item_id in pending:replay(item_id)
    with Session() as db:
        for r in db.scalars(select(Report).where(Report.enabled==True,Report.next_run<=time.time())):
            d=deliver(db,r)
            if d:record(db,'worker','report.delivered',{'id':r.id,'delivery':d.id})
        db.commit()
def main():
    r=Redis.from_url(REDIS_URL,socket_timeout=3)
    # This Compose stack has a single worker. A crash must not strand its jobs or replay items.
    with Session() as db:
        for j in db.scalars(select(Job).where(Job.status=='running')):
            j.status='queued';record(db,'worker','job.recovered',{'id':j.id})
        for item in db.scalars(select(ReplayItem).where(ReplayItem.status=='running')):
            item.status='pending';record(db,'worker','replay.recovered',{'id':item.id})
        db.commit()
    while True:
        Path('/tmp/heartbeat').touch()
        try:
            message=r.blpop(['analysis:queue','replay:queue'],timeout=1)
            if message:
                queue,value=message[0].decode(),int(message[1])
                if queue=='analysis:queue':execute(value)
                else:replay(value)
            tick()
        except Exception:
            logging.exception('Worker retry');time.sleep(2)
if __name__=='__main__':main()
