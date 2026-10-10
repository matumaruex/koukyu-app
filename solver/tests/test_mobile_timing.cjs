'use strict';
// 実画面で、続きの自動計算（段階が終わるまで・上限5分）、送信する条件、失敗・悪化・古い応答の保護を確認する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={staff:[{id:'local',name:'職員',type:'full',nightShiftType:'all'}],schedules:{}};
function result(ot,{done=false,stage='overtime',short}={}){return {status:short===undefined?'FEASIBLE':'DRAFT',assignments:{s0:{'1':'off'}},seconds:60,
 ...(short===undefined?{}:{staffingShortfallTotal:short}),
 allocation:{overtimeTotal:ot,nightSpread:0},search:{done,continueRecommended:!done,resume:done?null:{stage,idle:3,proven:{}}},boundaryComplete:true,optimizationPolicy:'quality-first-8'};}
const buttons=h=>h.nodes.view.all('button').map(b=>b.textContent);
(async()=>{
 // 段階が終わるまで続きを呼び、前回の表と再開位置を渡す。新規と改善、既存の表あり・なし。
 for(const existing of [false,true]){
  for(const mode of ['new','improve']){
   let n=0,progress=null;const h=harness(raw,{response:async()=>{n++;if(n===3)progress=h.get('state.progressStage');return result(5-n,{done:n===3,stage:n===1?'conditions':'overtime'});}});
   if(existing)h.eval("schedule().assignments={local:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE'};");
   const archives=h.get('data.savedTables');await h.ctx.generate(mode);
   assert.equal(h.calls.length,3);assert.equal(h.calls[0].adaptive,false);assert.equal(h.calls[0].qualityFirst,true);
   assert.equal(h.calls[0].allowStaffingShortfall,true);assert.equal(h.calls[0].allowNightShortfall,false);assert.equal(h.calls[0].allowRuleExceptions,true);
   assert.equal(!!h.calls[0].initialAssignments,existing&&mode==='improve');assert.equal(h.calls[0].resume,undefined);
   assert.deepEqual(h.calls[1].initialAssignments,{s0:{'1':'off'}});
   assert.deepEqual(h.calls[1].resume,{stage:'conditions',idle:3,proven:{}});assert.deepEqual(h.calls[2].resume,{stage:'overtime',idle:3,proven:{}});
   assert(progress.includes('残業の合計を調整中'));assert(progress.includes('A残 4→3回'));
   assert.equal(h.calls.reduce((t,c)=>t+c.seconds,0),180);
   assert.equal(h.get('schedule().meta.allocation.overtimeTotal'),2);assert.equal(h.get('schedule().meta.seconds'),180);
   assert.equal(h.get('schedule().meta.workflow.done'),true);assert(!buttons(h).includes('さらに改善する'));
   assert.deepEqual(h.get('data.savedTables'),archives);assert.equal(h.confirmations.length,0);
  }
 }
 // 良くなり続ける場合も合計5分で止め、「さらに改善する」を残す。
 const capped=harness(raw,{response:async()=>result(3)});await capped.ctx.generate();
 assert.equal(capped.calls.length,5);assert.equal(capped.calls.reduce((t,c)=>t+c.seconds,0),300);
 assert.equal(capped.get('schedule().meta.workflow.done'),false);assert(buttons(capped).includes('さらに改善する'));
 // 人数不足の理論上の下限は回をまたいで高い方を使う。
 let k=0;const bound=harness(raw,{response:async()=>({...result(3,{done:++k===2,short:5}),shortfallLowerBound:k===1?2:undefined})});await bound.ctx.generate();
 assert.equal(bound.get('schedule().meta.shortfallLowerBound'),2);assert(bound.nodes.view.text.includes('あと最大3か所減る可能性'));
 const stable=harness(raw,{response:async()=>result(3,{done:true})});await stable.ctx.generate();assert.equal(stable.calls.length,1);
 // 全段階を終えた応答でも、未確認の残業差が残れば手動の改善を隠さない。
 const unconfirmed=harness(raw,{response:async()=>({...result(3,{done:true}),overtimeFairness:{minimumSpreadProven:false}})});
 await unconfirmed.ctx.generate();assert.equal(unconfirmed.calls.length,1);assert(buttons(unconfirmed).includes('さらに改善する'));
 // 作れないときは、理由調べの結果（外す希望）を名前と日付で出す。
 const impossible=harness(raw,{response:async()=>({status:'INFEASIBLE',seconds:.1,diagnosis:{status:'EXPLAINED',proven:true,missingNights:[],droppedWishes:[{kind:'request',staff:'s0',day:3,shift:'off'}]}})});
 await impossible.ctx.generate();assert.equal(impossible.calls.length,1);assert.equal(impossible.get('hasTable()'),false);
 assert(impossible.nodes.view.text.includes('次の1件を外すと作れます'));assert(impossible.nodes.view.text.includes('職員さん 10月18日（日）の希望休'));
 const nights=harness(raw,{response:async()=>({status:'INFEASIBLE',seconds:.1,diagnosis:{status:'EXPLAINED',proven:true,missingNights:[3,4,5,10],droppedWishes:[]}})});
 await nights.ctx.generate();assert(nights.nodes.view.text.includes('夜勤に入れる人がいない日：10月18日（日）〜10月20日（火）、10月25日（日）'));
 const unknown=harness(raw);await unknown.ctx.generate();assert.equal(unknown.calls.length,5);assert(unknown.nodes.notice.textContent.includes('不可能と判定したわけではありません'));
 let n=0;const failure=harness(raw,{response:async()=>{if(n++)throw Error('offline');return result(3);}});await failure.ctx.generate();assert.equal(failure.get('hasTable()'),true);assert.equal(failure.get('schedule().meta.allocation.overtimeTotal'),3);assert(failure.nodes.notice.textContent.includes('確認済み'));
 // 悪化した応答は採用せず、その段階情報も使わない（いちばん良い表から最初の段階をやり直す）。
 n=0;const worse=harness(raw,{response:async()=>result(n++?5:3,{done:n>2})});await worse.ctx.generate();
 assert.equal(worse.get('schedule().meta.allocation.overtimeTotal'),3);assert.equal(worse.calls[2].resume,undefined);
 n=0;const proof=harness(raw,{response:async()=>({...result(3,{done:n>0}),preferencePriorityProven:n++===0})});await proof.ctx.generate();assert.equal(proof.get('schedule().meta.preferencePriorityProven'),true);
 const previous=harness(raw,{response:async()=>{throw Error('offline');}});previous.eval("schedule().assignments={local:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE',allocation:{overtimeTotal:2}};");await previous.ctx.generate('improve');assert.equal(previous.get('hasTable()'),true);assert.equal(previous.get('schedule().meta.allocation.overtimeTotal'),2);
 let finish;const stale=harness(raw,{response:()=>new Promise(r=>{finish=r;})});const pending=stale.ctx.generate();stale.eval("schedule().requests.local=[2]");finish(result(3));await pending;assert.equal(stale.get('hasTable()'),false);assert.equal(stale.calls.length,1);
 console.log('PASS: 段階が終わるまで続きを自動計算（再開位置・最良の表を渡す）、上限5分、途中経過、下限の表示、作れない理由、失敗/悪化/古い応答の保護');
})().catch(e=>{console.error(e);process.exitCode=1;});
