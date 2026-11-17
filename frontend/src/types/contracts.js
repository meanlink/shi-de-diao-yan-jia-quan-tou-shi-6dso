/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean,rule_version_id:number|null}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
/** @typedef {{id:number,version:number,label:string,definition:Object,status:'candidate'|'replaying'|'ready'|'active'|'retired',replay_epoch:number,progress?:{total:number,done:number,pending:number,running:number,failed:number}}} RuleVersion */
/** @typedef {{id:number,rule_id:number,job_id:number,job_name:string,epoch:number,status:'pending'|'running'|'done'|'failed',attempts:number,error:string,result:Object}} ReplayItem */
export {};
