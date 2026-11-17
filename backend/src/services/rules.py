"""计算规则版本治理：候选、逐份回放、启用、回退与停用。"""
import time
from fastapi import HTTPException
from redis import Redis
from sqlalchemy import select, func, update
from src.config.settings import REDIS_URL
from src.models import RuleVersion, ReplayItem, Job, Dataset
from src.services.business import analyze
from src.services.audit import record

BASELINE_DEFINITION = {"fpc": False}
BASELINE_LABEL = "无限总体近似（内置基线）"
CANDIDATE_DEFINITION = {"fpc": True}
PIPELINE_STATES = ("candidate", "replaying", "ready")

def ensure_baseline(db):
    """保证存在一条现行规则；空库时建立无限总体近似基线。"""
    active = db.scalar(select(RuleVersion).where(RuleVersion.status == "active").limit(1))
    if active:
        return active
    version = (db.scalar(select(func.max(RuleVersion.version))) or 0) + 1
    rule = RuleVersion(version=version, label=BASELINE_LABEL, definition=dict(BASELINE_DEFINITION), status="active", replay_epoch=1, created_by=None, created_at=time.time(), activated_at=time.time())
    db.add(rule)
    db.flush()
    return rule

def progress(db, rule_id):
    rows = db.execute(select(ReplayItem.status, func.count()).where(ReplayItem.rule_id == rule_id).group_by(ReplayItem.status)).all()
    counts = {status: count for status, count in rows}
    return {"total": sum(counts.values()), "done": counts.get("done", 0), "pending": counts.get("pending", 0), "running": counts.get("running", 0), "failed": counts.get("failed", 0)}

def create_candidate(db, data, user):
    if data.definition != CANDIDATE_DEFINITION:
        raise HTTPException(422, '候选规则仅支持 {"fpc": true} 有限总体修正模板')
    blocking = db.scalar(select(RuleVersion).where(RuleVersion.status.in_(PIPELINE_STATES)).limit(1))
    if blocking:
        raise HTTPException(409, f"已存在进行中的候选规则 v{blocking.version}，请先完成发布或停用")
    if data.job_ids:
        jobs = [db.get(Job, job_id) for job_id in dict.fromkeys(data.job_ids)]
        if any(job is None for job in jobs):
            raise HTTPException(404, "指定的历史分析不存在")
        if any(job.status != "completed" for job in jobs):
            raise HTTPException(409, "仅已完成的历史分析可指定回放")
    else:
        jobs = list(db.scalars(select(Job).where(Job.status == "completed").order_by(Job.id)))
    if not jobs:
        raise HTTPException(422, "没有可回放的已完成历史分析")
    label = (data.label or "").strip()
    if len(label) < 2:
        raise HTTPException(422, "规则名称去除空格后至少需要两个字符")
    version = (db.scalar(select(func.max(RuleVersion.version))) or 0) + 1
    rule = RuleVersion(version=version, label=label, definition=dict(CANDIDATE_DEFINITION), status="candidate", replay_epoch=1, created_by=user.id, created_at=time.time())
    db.add(rule)
    db.flush()
    for job in jobs:
        dataset = db.get(Dataset, job.dataset_id)
        db.add(ReplayItem(rule_id=rule.id, job_id=job.id, epoch=rule.replay_epoch, frozen_params=dict(job.params or {}), frozen_checksum=dataset.checksum if dataset else ""))
    db.flush()
    return rule

def pending_item_ids(db, rule):
    return list(db.scalars(select(ReplayItem.id).where(ReplayItem.rule_id == rule.id, ReplayItem.status == "pending").order_by(ReplayItem.id)))

def start_replay(db, rule):
    if rule.status == "ready":
        # 重新回放：提升代次并重置条目，上一代的过期执行返回不得覆盖新一轮
        rule.replay_epoch += 1
        for item in db.scalars(select(ReplayItem).where(ReplayItem.rule_id == rule.id)):
            item.epoch, item.status, item.result, item.error, item.finished_at = rule.replay_epoch, "pending", {}, "", None
    elif rule.status != "candidate":
        raise HTTPException(409, "当前状态不能发起回放")
    rule.status = "replaying"
    db.flush()
    return pending_item_ids(db, rule)

def resume_replay(db, rule):
    if rule.status != "replaying":
        raise HTTPException(409, "仅回放中的规则可恢复待算项")
    return pending_item_ids(db, rule)

def retry_item(db, rule, item_id):
    item = db.get(ReplayItem, item_id)
    if not item or item.rule_id != rule.id:
        raise HTTPException(404, "回放项不存在")
    if rule.status != "replaying" or item.status != "failed":
        raise HTTPException(409, "仅回放中的失败项可重试")
    if item.epoch != rule.replay_epoch:
        raise HTTPException(409, "回放已换代，请重新发起回放")
    item.status, item.error = "pending", ""
    db.flush()
    return item.id

def activate(db, rule):
    if rule.status != "ready":
        raise HTTPException(409, "全部回放完成前不能启用")
    state = progress(db, rule.id)
    if not state["total"] or state["done"] != state["total"]:
        raise HTTPException(409, "全部回放完成后才能启用")
    for other in db.scalars(select(RuleVersion).where(RuleVersion.status == "active", RuleVersion.id != rule.id)):
        other.status, other.retired_at = "retired", time.time()
    rule.status, rule.activated_at = "active", time.time()
    db.flush()
    return rule

def rollback(db, rule):
    if rule.status != "active":
        raise HTTPException(409, "仅现行规则可回退")
    predecessor = db.scalar(select(RuleVersion).where(RuleVersion.status == "retired", RuleVersion.activated_at.isnot(None)).order_by(RuleVersion.retired_at.desc(), RuleVersion.version.desc()).limit(1))
    if not predecessor:
        raise HTTPException(409, "没有可回退的历史规则")
    rule.status, rule.retired_at = "retired", time.time()
    predecessor.status, predecessor.activated_at = "active", time.time()
    db.flush()
    return predecessor

def discard(db, rule):
    if rule.status not in PIPELINE_STATES:
        raise HTTPException(409, "仅候选、回放中或可启用的规则可停用")
    rule.status, rule.retired_at = "retired", time.time()
    db.flush()
    return rule

def enqueue(item_ids):
    try:
        r = Redis.from_url(REDIS_URL)
        for item_id in item_ids:
            r.rpush("replay:queue", item_id)
        r.close()
    except Exception:
        pass  # SQL 中待算状态是持久兜底，worker 周期扫描会接管

def interval_diff(before, after):
    diff = {}
    for team, new in (after or {}).items():
        old = (before or {}).get(team) or {}
        diff[team] = {"low_before": old.get("low"), "high_before": old.get("high"), "low_after": new.get("low"), "high_after": new.get("high"), "width_before": old.get("width"), "width_after": new.get("width"), "width_delta": round(new.get("width", 0) - (old.get("width") or 0), 6)}
    return diff

def diff_summary(diff):
    parts = []
    for team, d in diff.items():
        before = "—" if d["width_before"] is None else f"{d['width_before'] * 100:.2f}%"
        parts.append(f"{team}区间宽{before}→{d['width_after'] * 100:.2f}%（{'+' if d['width_delta'] >= 0 else ''}{d['width_delta'] * 100:.2f}个百分点）")
    return "；".join(parts)

def execute_item(db, item_id):
    """逐份执行回放项。结果写回原行：同项重试不新增成果；带代次与状态的条件更新保证过期执行返回不覆盖新版。"""
    item = db.get(ReplayItem, item_id)
    if not item or item.status != "pending":
        return None
    rule = db.get(RuleVersion, item.rule_id)
    if not rule or rule.status != "replaying" or item.epoch != rule.replay_epoch:
        return None
    item.status = "running"
    item.attempts += 1
    db.commit()
    try:
        job = db.get(Job, item.job_id)
        dataset = db.get(Dataset, job.dataset_id) if job else None
        if not job or not dataset:
            raise ValueError("历史分析或数据批次已不存在")
        if dataset.checksum != item.frozen_checksum:
            raise ValueError("数据批次指纹与回放冻结时不一致，拒绝回放")
        after = analyze(dataset.records, item.frozen_params, rule.definition)
        before = job.result.get("intervals") if isinstance(job.result, dict) else None
        if not before:
            base = db.get(RuleVersion, job.rule_version_id) if job.rule_version_id else None
            before = analyze(dataset.records, item.frozen_params, (base.definition if base else BASELINE_DEFINITION))["intervals"]
        diff = interval_diff(before, after["intervals"])
        payload = {"job_name": job.name, "params": item.frozen_params, "dataset_checksum": item.frozen_checksum, "intervals_before": before, "intervals_after": after["intervals"], "diff": diff, "summary": diff_summary(diff)}
        db.execute(update(ReplayItem).where(ReplayItem.id == item.id, ReplayItem.status == "running", ReplayItem.epoch == rule.replay_epoch).values(status="done", result=payload, error="", finished_at=time.time()))
        outcome = "done"
    except Exception as error:
        db.execute(update(ReplayItem).where(ReplayItem.id == item.id, ReplayItem.status == "running", ReplayItem.epoch == rule.replay_epoch).values(status="failed", error=str(error)[:990], finished_at=time.time()))
        outcome = "failed"
    db.commit()
    db.refresh(rule)
    if rule.status == "replaying":
        state = progress(db, rule.id)
        if state["total"] and not state["pending"] and not state["running"] and not state["failed"]:
            rule.status = "ready"
            record(db, "worker", "rule.ready", {"id": rule.id, "version": rule.version})
            db.commit()
    return outcome
