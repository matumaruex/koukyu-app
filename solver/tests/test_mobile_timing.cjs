'use strict';
// 実画面で新規/改善、自動継続、通信失敗、古い応答を確認する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={staff:[{id:'local',name:'職員',type:'full',nightShiftType:'all'}],schedules:{}};
function result(ot,cont=true){return {status:'FEASIBLE',assignments:{s0:{'1':'off'}},seconds:60,
 allocation:{overtimeTotal:ot,nightSpread:0},search:{continueRecommended:cont},boundaryComplete:true};}
(async()=>{
 for(const existing of [false,true]){
  for(const mode of ['new','improve']){
   let n=0;const h=harness(raw,{response:async()=>result(++n===1?4:3,n===1)});
   if(existing)h.eval("schedule().assignments={local:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE'};");
   const archives=h.get('data.savedTables');await h.ctx.generate(mode);
   assert.equal(h.calls.length,2);assert.equal(h.calls[0].adaptive,false);assert.equal(h.calls[0].qualityFirst,true);
   assert.equal(!!h.calls[0].initialAssignments,existing&&mode==='improve');
   assert.deepEqual(h.calls[1].initialAssignments,{s0:{'1':'off'}});
   assert.equal(h.calls[0].seconds+h.calls[1].seconds,120);
   assert.equal(h.get('schedule().meta.allocation.overtimeTotal'),3);
   assert.equal(h.get('schedule().meta.seconds'),120);
   assert.deepEqual(h.get('data.savedTables'),archives);assert.equal(h.confirmations.length,0);
  }
 }
 const stable=harness(raw,{response:async()=>result(3,false)});await stable.ctx.generate();assert.equal(stable.calls.length,1);
 const impossible=harness(raw,{response:async()=>({status:'INFEASIBLE',seconds:.1})});await impossible.ctx.generate();assert.equal(impossible.calls.length,1);assert.equal(impossible.get('hasTable()'),false);
 const unknown=harness(raw);await unknown.ctx.generate();assert.equal(unknown.calls.length,2);assert(unknown.nodes.notice.textContent.includes('不可能と判定したわけではありません'));
 let n=0;const failure=harness(raw,{response:async()=>{if(n++)throw Error('offline');return result(3);}});await failure.ctx.generate();assert.equal(failure.get('hasTable()'),true);assert.equal(failure.get('schedule().meta.allocation.overtimeTotal'),3);assert(failure.nodes.notice.textContent.includes('確認済み'));
 n=0;const worse=harness(raw,{response:async()=>result(n++?5:3)});await worse.ctx.generate();assert.equal(worse.get('schedule().meta.allocation.overtimeTotal'),3);
 n=0;const proof=harness(raw,{response:async()=>({...result(3),preferencePriorityProven:n++===0})});await proof.ctx.generate();assert.equal(proof.get('schedule().meta.preferencePriorityProven'),true);
 const previous=harness(raw,{response:async()=>{throw Error('offline');}});previous.eval("schedule().assignments={local:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE',allocation:{overtimeTotal:2}};");await previous.ctx.generate('improve');assert.equal(previous.get('hasTable()'),true);assert.equal(previous.get('schedule().meta.allocation.overtimeTotal'),2);
 let finish;const stale=harness(raw,{response:()=>new Promise(r=>{finish=r;})});const pending=stale.ctx.generate();stale.eval("schedule().requests.local=[2]");finish(result(3));await pending;assert.equal(stale.get('hasTable()'),false);assert.equal(stale.calls.length,1);
 console.log('PASS: 1回の操作で60秒＋必要時の自動継続、上限120秒、初回新規、改善保持、失敗/悪化/古い応答の保護');
})().catch(e=>{console.error(e);process.exitCode=1;});
