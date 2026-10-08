(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.AutoCreationWorkflow=api;})(globalThis,function(){
'use strict';
const MAX_SECONDS=480,BASE_SECONDS=300,ADJUST_SECONDS=120,FINISH_SECONDS=60;
const candidate=r=>r?.assignments&&['OPTIMAL','FEASIBLE','DRAFT'].includes(r.status);
const quality=r=>{const m=r.allocation||{};return [r.exceptionCount||0,r.staffingShortfallTotal||0,r.nightRestPreferences?.unmet?.length||0,m.nightSpread||0,m.overtimeTotal||0,(m.overtimeBalance||0)*(m.overtimeProportional?1:100),m.surplusTotal||0,-(m.commonExtraDaysOff||0),m.minor||0];};
function compare(a,b){const x=quality(a),y=quality(b);for(let i=0;i<x.length;i++)if(x[i]!==y[i])return x[i]-y[i];return 0;}
async function run({input,holidayPolicy,request,nextSeed,isCurrent=()=>true,onExtend=()=>{}}){
 let spent=0,error=null,rounds=[],best=null,last=null,resume=null,baseDone=false,adjustDone=false,necessity=false,details=null,pending=null;
 const target=Object.fromEntries(Object.entries(holidayPolicy).map(([sid,q])=>[sid,q.target]));
 let quota={...target},phaseSpent=0;
 async function call(phase,budget,extra={}){if(!isCurrent())return null;const r=await request({mode:'auto',autoPhase:phase,input,holidayPolicy,seconds:Math.min(60,budget,MAX_SECONDS-spent),seed:nextSeed(),...extra});if(!isCurrent())return null;const elapsed=Number.isFinite(r.seconds)&&r.seconds>=0?Math.max(.01,r.seconds):Math.min(60,budget);spent+=elapsed;phaseSpent+=elapsed;rounds.push({phase,seconds:elapsed,status:r.status});last=r;return r;}
 try{
  // 基準の品質確保は通常版と同じ300秒。公休の検討にこの時間を流用しない。
  while(phaseSpent<BASE_SECONDS-.1){
   onExtend('表の品質を整えています。',best);
   const r=await call('base',BASE_SECONDS-phaseSpent,{...(best?{initialAssignments:best.assignments}:{}),...(resume?{resume}:{})});if(!r)return {stale:true};
   const take=candidate(r)&&(!best||compare(r,best)<=0);if(take)best=r;
   if(r.status==='INFEASIBLE'){necessity=true;break;}
   if(['INVALID_INPUT','VALIDATION_FAILED'].includes(r.status))break;
   if(r.status==='OPTIMAL'||r.search?.done){baseDone=true;break;}
   if(!(r.status==='UNKNOWN'||r.search?.continueRecommended))break;
   resume=take||!best?r.search?.resume||null:null;
  }
  // 公平化が未確認なら、日数を増やす検討より先に残った検討予算を公平化へ使う。
  let fairnessSpent=0;
  while(best&&best.allocation.minimumOvertimeProven!==true&&Number.isInteger(best.autoBounds?.overtime)&&best.allocation.overtimeTotal>best.autoBounds.overtime&&fairnessSpent<ADJUST_SECONDS-.1&&spent<MAX_SECONDS-.1){
   onExtend('残業を減らせる余地を確認しています。',best);
   const before=spent,r=await call('polish',ADJUST_SECONDS-fairnessSpent,{referenceAssignments:best.assignments});if(!r)return {stale:true};fairnessSpent+=spent-before;
   if(candidate(r)&&compare(r,best)<=0)best=r;
   if(candidate(r)&&r.allocation?.minimumOvertimeProven)break;
  }
  while(best?.overtimeFairness?.minimumSpreadProven===false&&fairnessSpent<ADJUST_SECONDS-.1&&spent<MAX_SECONDS-.1){
   onExtend('残業回数の公平さを整えています。',best);
   const before=spent,r=await call('base',ADJUST_SECONDS-fairnessSpent,{initialAssignments:best.assignments,resume:{stage:'overtime_fairness',idle:0,proven:{}}});if(!r)return {stale:true};fairnessSpent+=spent-before;
   if(candidate(r)&&compare(r,best)<=0)best=r;
   if(!candidate(r)||r.overtimeFairness?.minimumSpreadProven)break;
  }
  const reference=best;
  if(best?.autoBounds?.holidayChangeRuledOut){adjustDone=true;best={...best,autoReason:'quality_preserved',autoDetails:{daysProven:true,shortageLowerBound:best.autoBounds.shortage,overtimeLowerBound:best.autoBounds.overtime}};}
  if(best||necessity){
   phaseSpent=fairnessSpent;
   while(!adjustDone&&phaseSpent<ADJUST_SECONDS-.1&&spent<MAX_SECONDS-.1){
    onExtend('休みを調整できるか確認しています。',best);
    const r=await call('adjust',ADJUST_SECONDS-phaseSpent,{...(reference?{referenceAssignments:reference.assignments}:{}),...(pending?{autoCandidate:pending}:{} )});if(!r)return {stale:true};
    if(candidate(r)){
     const reduction=Object.entries(r.selectedQuota||{}).some(([sid,q])=>q<target[sid]);
     const upperImproved=!reference||quality(r)[0]<quality(reference)[0]||quality(r)[0]===quality(reference)[0]&&quality(r)[1]<quality(reference)[1];
     const allProtected=!reference||(r.comparisonQuality||quality(r)).every((v,i)=>v<=quality(reference)[i]);
     const moreHolidays=Object.values(r.selectedQuota||{}).reduce((a,b)=>a+b,0)>Object.values(quota).reduce((a,b)=>a+b,0);
     const firstReduction=reduction&&Object.entries(quota).every(([sid,q])=>q>=target[sid]);
     if((reduction&&r.autoDetails?.necessityProven&&upperImproved||!reduction&&allProtected)&&(!best||firstReduction||moreHolidays&&!reduction||compare(r,best)<=0)){
      // 日数も勤務も不変なら、基準の証明と完成表をそのまま保持する。
      if(r.autoChanged===false&&reference)best={...reference,autoDetails:r.autoDetails,autoReason:r.autoReason,allocation:{...reference.allocation,...(r.allocation?.minimumOvertimeProven?{minimumOvertimeProven:true,minimumOvertimeScope:r.allocation.minimumOvertimeScope}:{})}};else best=r;
      quota={...r.selectedQuota};details=r.autoDetails;pending={assignments:best.assignments,quotas:quota};
     }
    }else if(r.autoCandidate)pending=r.autoCandidate;
    if(r.autoDone){adjustDone=true;break;}
    if(['INVALID_INPUT','VALIDATION_FAILED','INFEASIBLE'].includes(r.status))break;
   }
   const quotaChanged=Object.entries(quota).some(([sid,q])=>q!==target[sid]);
   if(best&&(!reference||quotaChanged||JSON.stringify(best.assignments)!==JSON.stringify(reference.assignments))){
    phaseSpent=0;
    while(phaseSpent<FINISH_SECONDS-.1&&spent<MAX_SECONDS-.1){
     onExtend('選んだ日数で仕上げています。',best);
     const r=await call('finish',FINISH_SECONDS-phaseSpent,{selectedQuota:quota,initialAssignments:best.assignments,...(reference?{referenceAssignments:reference.assignments}:{})});if(!r)return {stale:true};
     if(candidate(r)&&compare(r,best)<=0)best={...r,autoReason:best.autoReason,autoDetails:details};
     if(r.search?.done||r.status==='OPTIMAL'||!candidate(r))break;
    }
   }
  }
 }catch(e){if(!isCurrent())return {stale:true};error=e;}
 if(!isCurrent())return {stale:true};
 if(best)best={...best,selectedQuota:quota,autoDetails:{...(best.autoDetails||details||{}),daysProven:adjustDone},autoReason:best.autoReason||(adjustDone?'quality_preserved':'days_unconfirmed')};
 return {best,last,seconds:spent,rounds,error,done:baseDone&&adjustDone,stale:false};
}
return {MAX_SECONDS,BASE_SECONDS,ADJUST_SECONDS,FINISH_SECONDS,quality,compare,run};
});
