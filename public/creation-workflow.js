(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.CreationWorkflow=api;})(globalThis,function(){
'use strict';
// 1回の通信は60秒以内。サーバーが「まだ良くなっている段階がある」と返す間は、続きから自動で呼び直す。
// 各段階は、最少と証明できたか一定時間良くならなかったときに次へ進み、すべて終われば完了。全体の上限は5分。
const BASE_SECONDS=60,MAX_SECONDS=300;
function rank(r){const m=r.allocation||{};return [r.restExceptionCount||0,r.exceptionCount||0,r.staffingShortfallTotal||0,r.nightShortfallTotal||0,r.nightRestPreferences?.unmet?.length||0,m.nightSpread||0,m.overtimeTotal||0,m.overtimeBalance??m.overtimeSpread??0,m.surplusTotal||0,-(m.commonExtraDaysOff||0),m.minor||0];}
function compare(a,b){const x=rank(a),y=rank(b);for(let i=0;i<x.length;i++)if(x[i]!==y[i])return x[i]-y[i];
 // 同じ品質なら、既に確認できた最少証明を時間切れの応答で失わない。
 const proof=r=>[r.status==='OPTIMAL',!!r.preferencePriorityProven,!!r.allocation?.minimumOvertimeProven,!!r.overtimeFairness?.minimumSpreadProven,!!r.shortfallProvenMinimum,!!r.nightFairness?.minimumSpreadProven];
 const u=proof(a),v=proof(b);for(let i=0;i<u.length;i++)if(u[i]!==v[i])return Number(v[i])-Number(u[i]);return 0;}
function candidate(r){return r&&r.assignments&&['OPTIMAL','FEASIBLE','DRAFT'].includes(r.status);}
async function run({input,initialAssignments,request,nextSeed,isCurrent=()=>true,onExtend=()=>{}}){
 let best=null,last=null,seconds=0,error=null,resume=null,done=false,shortfallBound=null;const rounds=[];
 while(MAX_SECONDS-seconds>0.1){
  if(!isCurrent())return {stale:true};
  const budget=Math.min(BASE_SECONDS,MAX_SECONDS-seconds),baseline=best?.assignments||initialAssignments;
  try{
   const r=await request({input,seconds:budget,adaptive:false,qualityFirst:true,seed:nextSeed(),...(baseline?{initialAssignments:baseline}:{}),...(resume?{resume}:{})});
   if(!isCurrent())return {stale:true};
   last=r;
   const elapsed=Number.isFinite(r.seconds)&&r.seconds>=0?r.seconds:budget;
   seconds+=elapsed;rounds.push({seconds:elapsed,status:r.status,reason:r.search?.reason||null,stage:r.search?.resume?.stage||null});
   // 理論上の下限は回を重ねても有効なので、いちばん高い値を使う。
   if(Number.isInteger(r.shortfallLowerBound))shortfallBound=Math.max(shortfallBound??0,r.shortfallLowerBound);
   const improved=candidate(r)&&(!best||compare(r,best)<=0);
   if(improved)best=r;
   if(['OPTIMAL','INFEASIBLE','INVALID_INPUT','VALIDATION_FAILED'].includes(r.status)){done=r.status==='OPTIMAL';break;}
   if(r.search?.done===true){done=true;break;}
   if(!(r.search?.continueRecommended===true||r.status==='UNKNOWN'))break;
   // 続きは、今いちばん良い表から再開する（悪化した応答の段階情報は使わない）。
   resume=improved||!best?(r.search?.resume||null):null;
   if(MAX_SECONDS-seconds<=0.1)break;
   onExtend(r);
  }catch(e){if(!isCurrent())return {stale:true};error=e;break;}
 }
 if(best&&shortfallBound!==null&&Number.isInteger(best.staffingShortfallTotal))best={...best,shortfallLowerBound:Math.min(shortfallBound,best.staffingShortfallTotal)};
 return {best,last,seconds,rounds,error,done,stale:false};
}
return {BASE_SECONDS,MAX_SECONDS,rank,compare,run};
});
