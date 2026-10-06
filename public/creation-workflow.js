(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.CreationWorkflow=api;})(globalThis,function(){
'use strict';
const BASE_SECONDS=60,MAX_SECONDS=120;
function rank(r){const m=r.allocation||{};return [r.staffingShortfallTotal||0,r.nightShortfallTotal||0,r.nightRestPreferences?.unmet?.length||0,m.nightSpread||0,m.overtimeTotal||0,m.surplusTotal||0,m.overtimeSpread||0,-(m.commonExtraDaysOff||0),m.minor||0];}
function compare(a,b){const x=rank(a),y=rank(b);for(let i=0;i<x.length;i++)if(x[i]!==y[i])return x[i]-y[i];
 // 同じ品質なら、既に確認できた最少証明を時間切れの応答で失わない。
 const proof=r=>[r.status==='OPTIMAL',!!r.preferencePriorityProven,!!r.allocation?.minimumOvertimeProven,!!r.shortfallProvenMinimum,!!r.nightFairness?.minimumSpreadProven];
 const u=proof(a),v=proof(b);for(let i=0;i<u.length;i++)if(u[i]!==v[i])return Number(v[i])-Number(u[i]);return 0;}
function candidate(r){return r&&r.assignments&&['OPTIMAL','FEASIBLE','DRAFT'].includes(r.status);}
async function run({input,initialAssignments,request,nextSeed,isCurrent=()=>true,onExtend=()=>{}}){
 let best=null,last=null,seconds=0,error=null;const rounds=[];
 for(let i=0;i<2&&MAX_SECONDS-seconds>0.1;i++){
  if(!isCurrent())return {stale:true};
  const budget=Math.min(BASE_SECONDS,MAX_SECONDS-seconds),baseline=best?.assignments||initialAssignments;
  try{
   const r=await request({input,seconds:budget,adaptive:false,qualityFirst:true,seed:nextSeed(),...(baseline?{initialAssignments:baseline}:{})});
   if(!isCurrent())return {stale:true};
   last=r;
   const elapsed=Number.isFinite(r.seconds)&&r.seconds>=0?r.seconds:budget;
   seconds+=elapsed;rounds.push({seconds:elapsed,status:r.status,reason:r.search?.reason||null});
   if(candidate(r)&&(!best||compare(r,best)<=0))best=r;
   if(i===1||['OPTIMAL','INFEASIBLE','INVALID_INPUT','VALIDATION_FAILED'].includes(r.status))break;
   if(!(r.search?.continueRecommended===true||r.status==='UNKNOWN'))break;
   if(MAX_SECONDS-seconds<=0.1)break;
   onExtend();
  }catch(e){if(!isCurrent())return {stale:true};error=e;break;}
 }
 return {best,last,seconds,rounds,error,stale:false};
}
return {BASE_SECONDS,MAX_SECONDS,rank,compare,run};
});
