import hashlib, json
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records), 'checksum':d.checksum, 'created_at':d.created_at}
def job_dict(j):
    return {k:getattr(j,k) for k in ['id','name','dataset_id','params','status','result','error','approved','rule_version_id','created_at','finished_at']}
def rule_dict(r,progress=None):
    d={k:getattr(r,k) for k in ['id','version','label','definition','status','replay_epoch','created_at','activated_at','retired_at']}
    if progress is not None:d['progress']=progress
    return d
def replay_item_dict(i,job_name=None):
    return {'id':i.id,'rule_id':i.rule_id,'job_id':i.job_id,'job_name':job_name,'epoch':i.epoch,'status':i.status,'attempts':i.attempts,'error':i.error,'result':i.result,'finished_at':i.finished_at}
def report_dict(r):
    return {k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled']}
def delivery_dict(d):
    return {k:getattr(d,k) for k in ['id','report_id','created_at','checksum','filename','destination']}
