from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import RuleVersion, ReplayItem, Job
from src.schemas.rule import RuleInput
from src.middlewares.auth import current_user, admin_only
from src.services import rules as service
from src.services.audit import record
from src.utils.serialization import rule_dict, replay_item_dict
router=APIRouter(prefix='/rules')
def _get(db,id):
    r=db.get(RuleVersion,id)
    if not r:raise HTTPException(404,'计算规则不存在')
    return r
@router.get('')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return [rule_dict(r,service.progress(db,r.id)) for r in db.scalars(select(RuleVersion).order_by(RuleVersion.version.desc()))]
@router.post('',status_code=201)
def create(data:RuleInput,db=Depends(get_db),u=Depends(admin_only)):
    r=service.create_candidate(db,data,u)
    record(db,u.email,'rule.create',{'id':r.id,'version':r.version,'items':service.progress(db,r.id)['total']})
    db.commit();return rule_dict(r,service.progress(db,r.id))
@router.get('/{id}')
def detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    r=_get(db,id);items=[]
    for item in db.scalars(select(ReplayItem).where(ReplayItem.rule_id==r.id).order_by(ReplayItem.id)):
        j=db.get(Job,item.job_id)
        items.append(replay_item_dict(item,j.name if j else None))
    return {**rule_dict(r,service.progress(db,r.id)),'items':items}
@router.post('/{id}/replay')
def replay(id:int,db=Depends(get_db),u=Depends(admin_only)):
    r=_get(db,id);ids=service.start_replay(db,r)
    record(db,u.email,'rule.replay.start',{'id':id,'epoch':r.replay_epoch,'items':len(ids)})
    db.commit();service.enqueue(ids);return rule_dict(r,service.progress(db,r.id))
@router.post('/{id}/replay/resume')
def resume(id:int,db=Depends(get_db),u=Depends(admin_only)):
    r=_get(db,id);ids=service.resume_replay(db,r)
    record(db,u.email,'rule.replay.resume',{'id':id,'items':len(ids)})
    db.commit();service.enqueue(ids);return rule_dict(r,service.progress(db,r.id))
@router.post('/{id}/items/{item_id}/retry')
def retry(id:int,item_id:int,db=Depends(get_db),u=Depends(admin_only)):
    r=_get(db,id);service.retry_item(db,r,item_id)
    record(db,u.email,'rule.replay.retry',{'id':id,'item':item_id})
    db.commit();service.enqueue([item_id]);return rule_dict(r,service.progress(db,r.id))
@router.post('/{id}/activate')
def activate(id:int,db=Depends(get_db),u=Depends(admin_only)):
    r=_get(db,id);service.activate(db,r)
    record(db,u.email,'rule.activate',{'id':id,'version':r.version})
    db.commit();return rule_dict(r,service.progress(db,r.id))
@router.post('/{id}/rollback')
def rollback(id:int,db=Depends(get_db),u=Depends(admin_only)):
    r=_get(db,id);predecessor=service.rollback(db,r)
    record(db,u.email,'rule.rollback',{'from':r.version,'to':predecessor.version})
    db.commit();return rule_dict(predecessor,service.progress(db,predecessor.id))
@router.post('/{id}/discard')
def discard(id:int,db=Depends(get_db),u=Depends(admin_only)):
    r=_get(db,id);service.discard(db,r)
    record(db,u.email,'rule.discard',{'id':id,'version':r.version})
    db.commit();return rule_dict(r,service.progress(db,r.id))
