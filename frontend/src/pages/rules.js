import {jobs,rules} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {esc,date,notify} from '../utils/dom.js';
import {RuleStatus,ReplayStatus} from '../constants/enums.js';
import {submit} from '../hooks/forms.js';
const pct=v=>v==null?'—':(v*100).toFixed(2)+'%';
const pp=v=>(v>=0?'+':'')+(v*100).toFixed(2)+'pp';
const chip=s=>'<span class="status rule-'+esc(s)+'">'+esc(RuleStatus[s]||s)+'</span>';
const itemChip=s=>'<span class="status item-'+esc(s)+'">'+esc(ReplayStatus[s]||s)+'</span>';
const fpcLabel=d=>d&&d.fpc?'有限总体修正 · 方差×(1−n/N) · 超框拒算':'无限总体近似';
function diffCell(item){
 const d=item.result&&item.result.diff;
 if(!d)return '—';
 return Object.entries(d).map(([team,v])=>'<div class="diff-line"><strong>'+esc(team)+'</strong> '+pct(v.width_before)+' → '+pct(v.width_after)+' <span class="'+(v.width_delta<=0?'delta-down':'delta-up')+'">'+pp(v.width_delta)+'</span></div>').join('');
}
export async function rulesPage(){
 const [list,allJobs]=await Promise.all([rules.list(),jobs.list()]);workspace.rules=list;
 const admin=session.user.role==='admin';
 const active=list.find(r=>r.status==='active');
 const pipeline=list.find(r=>['candidate','replaying','ready'].includes(r.status));
 const predecessor=list.filter(r=>r.status==='retired'&&r.activated_at).sort((a,b)=>(b.retired_at||0)-(a.retired_at||0))[0];
 const selected=list.find(r=>r.id===workspace.selectedRule)||pipeline||active||list[0];
 workspace.selectedRule=selected?selected.id:null;
 const detail=selected?await rules.get(selected.id):null;
 const completed=allJobs.filter(j=>j.status==='completed');
 const actions=r=>{
  if(!admin)return '<span class="hint-inline">仅负责人操作</span>';
  const b=[];
  if(r.status==='candidate')b.push('<button class="button small" data-action="replay" data-id="'+r.id+'">开始回放</button>');
  if(r.status==='replaying')b.push('<button class="button small" data-action="resume" data-id="'+r.id+'">恢复待算项</button>');
  if(r.status==='ready')b.push('<button class="button small primary" data-action="activate" data-id="'+r.id+'">启用为现行规则</button>','<button class="button small" data-action="replay" data-id="'+r.id+'">重新回放</button>');
  if(r.status==='active'&&predecessor)b.push('<button class="button small" data-action="rollback" data-id="'+r.id+'">回退到 v'+predecessor.version+'</button>');
  if(['candidate','replaying','ready'].includes(r.status))b.push('<button class="button small" data-action="discard" data-id="'+r.id+'">停用</button>');
  return b.join('')||'—';
 };
 const rows=list.map(r=>'<tr class="'+(selected&&r.id===selected.id?'selected-row':'')+'" data-select="'+r.id+'"><td>v'+r.version+'</td><td>'+esc(r.label)+'</td><td>'+chip(r.status)+'</td><td>'+esc(fpcLabel(r.definition))+'</td><td>'+(r.progress&&r.progress.total?r.progress.done+'/'+r.progress.total+(r.progress.failed?' · 失败'+r.progress.failed:''):'—')+'</td><td>'+date(r.created_at)+'</td><td class="rule-actions">'+actions(r)+'</td></tr>').join('');
 const items=detail?(detail.items||[]):[];
 const itemRows=items.map(i=>'<tr><td>'+esc(i.job_name||'#'+i.job_id)+'</td><td>'+itemChip(i.status)+'</td><td>'+diffCell(i)+'</td><td>'+(i.error?'<span class="error-text">'+esc(i.error)+'</span>'+(admin&&i.status==='failed'?' <button class="text-button" data-retry="'+i.id+'">重试</button>':''):(i.attempts>1?'重试 '+i.attempts+' 次':'—'))+'</td></tr>').join('');
 return heading('05 / RULES','计算规则发布','候选规则须按指定历史分析逐份回放：冻结样本与参数、对照区间变化。全部回放完成后负责人才能启用，也可回退；回放结果不供批准，历史简报沿用原结论。')
 +'<section class="rule-current"><div><p class="eyebrow">ACTIVE RULE</p><h2>'+(active?'v'+active.version+' · '+esc(active.label):'尚无现行规则')+'</h2><p>'+(active?esc(fpcLabel(active.definition))+(active.activated_at?' · 启用于 '+date(active.activated_at):''):'迁移或种子流程会建立内置基线。')+'</p></div>'+(admin&&active&&predecessor?'<button class="button" data-action="rollback" data-id="'+active.id+'">回退到 v'+predecessor.version+' ↩</button>':'')+'</section>'
 +'<div class="rules-grid"><section class="panel"><div class="section-title"><h2>发起候选规则</h2><span>发布流水线</span></div><form id="rule-form"><label>规则名称<input name="label" required minlength="2" value="有限总体修正（按各层框规模）"></label><label>计算口径<select name="definition"><option value="fpc">有限总体修正：层方差×(1−n_h/N_h)，观察量超框拒算</option></select></label><div class="job-checks">'+(completed.length?completed.map(j=>'<label><input type="checkbox" name="job" value="'+j.id+'" checked><span>'+esc(j.name)+'</span></label>').join(''):'<p class="hint">尚无已完成的历史分析可回放。</p>')+'</div><button type="submit" class="primary" '+(admin&&completed.length&&!pipeline?'':'disabled')+'>创建候选并冻结回放清单</button></form><p class="hint">'+(pipeline?'已有进行中的候选规则 v'+pipeline.version+'，完成发布或停用后才能新建。':'候选创建后即冻结各历史分析的样本指纹与参数；回放不改动原分析结论。')+'</p></section>'
 +'<section class="panel"><div class="section-title"><h2>规则版本</h2><span>候选 → 回放中 → 可启用 → 现行</span></div><div class="table-wrap"><table><thead><tr><th>版本</th><th>名称</th><th>状态</th><th>口径</th><th>回放进度</th><th>创建时间</th><th>操作</th></tr></thead><tbody>'+rows+'</tbody></table></div><p class="hint">切换与排队并发时，每项分析固定受理时的规则版本；已排队和恢复任务不换版。</p></section></div>'
 +(detail?'<section class="panel"><div class="section-title"><h2>回放对照 · v'+detail.version+' '+esc(detail.label)+'</h2><span>'+(detail.progress?detail.progress.done+'/'+detail.progress.total+' 已对照':'')+'</span></div><div class="table-wrap"><table><thead><tr><th>历史分析</th><th>状态</th><th>区间宽度对照（现行 → 候选）</th><th>备注</th></tr></thead><tbody>'+itemRows+'</tbody></table></div><p class="hint">回放结果仅供对照，不供批准；正式启用后仅新受理的分析使用新规则，历史简报沿用原结论。</p></section>':'');
}
export function bindRules(refresh){
 submit(document.querySelector('#rule-form'),async f=>{const ids=f.getAll('job').map(Number);const r=await rules.create({label:f.get('label'),definition:{fpc:true},job_ids:ids.length?ids:null});workspace.selectedRule=r.id;notify('候选规则已创建，回放清单已冻结');await refresh();});
 document.querySelectorAll('[data-select]').forEach(row=>row.addEventListener('click',e=>{if(e.target.closest('button'))return;workspace.selectedRule=Number(row.dataset.select);refresh();}));
 document.querySelectorAll('[data-action]').forEach(b=>b.onclick=async()=>{const id=Number(b.dataset.id);const action=b.dataset.action;try{await rules[action](id);workspace.selectedRule=id;notify({replay:'回放已启动，worker 逐份计算',resume:'已重新投递待算项',activate:'已启用为现行规则',rollback:'已回退到上一现行规则',discard:'候选已停用'}[action]||'已完成');await refresh();}catch(e){notify(e.message,true);}});
 document.querySelectorAll('[data-retry]').forEach(b=>b.onclick=async()=>{try{await rules.retry(workspace.selectedRule,Number(b.dataset.retry));notify('失败项已重试，不新增成果');await refresh();}catch(e){notify(e.message,true);}});
}
