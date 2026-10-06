'use strict';
// 残業可能者の集計、必要な差と未証明の差の表示、継続中の候補と証明の保護。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const flow=require('../../public/creation-workflow.js');
const row=n=>Object.fromEntries(Array.from({length:31},(_,i)=>[String(i+1),i<n?'overtime':'off']));
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'a',name:'A',type:'full',canOvertime:true,nightShiftType:'none'},
 {id:'b',name:'B',type:'full',canOvertime:true,nightShiftType:'none'},
 {id:'c',name:'C',type:'full',canOvertime:true,nightShiftType:'none'},
 {id:'d',name:'D',type:'full',canOvertime:false,nightShiftType:'none'},
 {id:'p',name:'P',type:'part',canOvertime:true,nightShiftType:'none'}],
 schedules:{'2026-10':{assignments:{},requests:{},history:{}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const h=harness(null,{current:raw});
h.eval('schedule().assignments='+JSON.stringify({a:row(6),b:row(4),c:row(3),d:row(0),p:row(0)})+';schedule().workSignature=inputData().signature;');
let text=h.eval('allocationSummary()').text;
assert(text.includes('残業（A残できる人）：3〜6回 ／ 差3回'));
assert(text.includes('避けられないかは、まだ確認できていません'));
h.eval("schedule().meta={status:'FEASIBLE',optimizationPolicy:OPTIMIZATION_POLICY,overtimeFairness:{total:13,spread:3,minimumSpreadProven:true}};");
assert(h.eval('allocationSummary()').text.includes('上位条件と残業合計を維持する範囲で、この回数差が最少'));
h.eval("schedule().meta.optimizationPolicy='quality-first-2'");
assert(h.eval('allocationSummary()').text.includes('まだ確認できていません'));
h.eval("schedule().assignments.a['1']='off';schedule().assignments.c['4']='overtime';schedule().meta=null;");
assert(h.eval('allocationSummary()').text.includes('4〜5回 ／ 差1回'));
assert(h.eval('allocationSummary()').text.includes('同じ残業合計では、これ以上均等にできない配分'));
h.eval("schedule().excludedStaff=['a'];");
assert(h.eval('allocationSummary()').text.includes('4〜4回 ／ 差0回'));
assert(h.eval("progressText({allocation:{overtimeSpread:3}}, {allocation:{overtimeSpread:1},search:{resume:{stage:'overtime_fairness'}}})").includes('残業回数の公平さを調整中（残業の差 3→1回）'));

function candidate(spread,surplus,proof=false){return {status:'FEASIBLE',assignments:{s0:{'1':'off'}},seconds:60,
 allocation:{overtimeTotal:13,overtimeSpread:spread,surplusTotal:surplus},
 overtimeFairness:{minimumSpreadProven:proof},search:{continueRecommended:true,resume:{stage:'overtime_fairness',idle:0,proven:{}}}};}
assert(flow.compare(candidate(1,10),candidate(3,0))<0);
assert(flow.compare({...candidate(0,0),allocation:{overtimeTotal:14,overtimeSpread:0,surplusTotal:0}},candidate(3,0))>0);
(async()=>{
 let n=0;const responses=[candidate(3,0),candidate(1,10),{...candidate(2,0),search:{done:true}}];
 const r=await flow.run({input:{},request:async()=>responses[n++],nextSeed:()=>1});
 assert.equal(r.best.allocation.overtimeSpread,1);assert.equal(r.best.allocation.overtimeTotal,13);
 n=0;const proof=await flow.run({input:{},request:async()=>{n++;return {...candidate(3,0,n===1),search:n===2?{done:true}:{continueRecommended:true}};},nextSeed:()=>1});
 assert.equal(proof.best.overtimeFairness.minimumSpreadProven,true);
 n=0;const failure=await flow.run({input:{},request:async()=>{if(n++)throw Error('offline');return candidate(1,10,true);},nextSeed:()=>1});
 assert.equal(failure.best.allocation.overtimeSpread,1);assert.equal(failure.best.overtimeFairness.minimumSpreadProven,true);
 console.log('PASS: 残業合計を増やさず回数差を余剰より優先、証明・通信失敗時の候補保護、対象者と編集後の集計');
})().catch(e=>{console.error(e);process.exitCode=1;});
