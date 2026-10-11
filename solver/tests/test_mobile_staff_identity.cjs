'use strict';
// 条件が同じ別人を入れ替えても、古い勤務と証明を現在の条件に流用しない。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={schemaVersion:4,savedTables:[],staff:['a','b'].map(id=>({id,name:'職員'+id,type:'full',nightShiftType:'none',monthlyDaysOff:9})),schedules:{'2026-10':{assignments:{},requests:{},excludedStaff:['b']}}};
function table(h,mode){
 if(mode==='auto')h.eval("setTab('auto');schedule().selectedQuota={a:9};schedule().creationMode='auto'");
 h.eval("schedule().assignments={a:{'1':'early'}};schedule().workSignature=inputData().signature;schedule().meta={status:'OPTIMAL',optimizationPolicy:OPTIMIZATION_POLICY,tableSignature:JSON.stringify(schedule().assignments)};render()");
}
const reopen=h=>harness(null,{current:JSON.parse(h.values.get('koukyu_v4_data')),stored:{koukyu_v4_work:h.values.get('koukyu_v4_work'),koukyu_v4_auto_work:h.values.get('koukyu_v4_auto_work')}});
for(const mode of ['normal','auto']){
 const h=harness(null,{current:raw});table(h,mode);
 const signature=h.get('inputData().signature'),snapshot=h.get('schedule().workSnapshot');
 h.ctx.setStaffIncluded('a',false);h.ctx.setStaffIncluded('b',true);
 assert.notEqual(h.get('inputData().signature'),signature);
 assert(h.get('workChanged()'));assert.equal(h.get('metadata()'),null);
 assert.deepEqual(h.get('schedule().workSnapshot'),snapshot);
 assert.deepEqual(h.get('schedule().assignments'),{a:{'1':'early'}});
 assert(h.nodes.view.text.includes('最新の条件とは異なる条件で作成した表です。'));
 const restored=reopen(h);if(mode==='auto')restored.eval("setTab('auto')");
 assert(restored.get('workChanged()'));assert.equal(restored.get('metadata()'),null);
 assert.deepEqual(restored.get('schedule().workSnapshot'),snapshot);
 h.ctx.setStaffIncluded('b',false);h.ctx.setStaffIncluded('a',true);
 assert.equal(h.get('inputData().signature'),signature);assert(!h.get('workChanged()'));
 // 並び順だけの変更では計算条件を変えない。
 h.eval('data.staff.reverse();render()');assert.equal(h.get('inputData().signature'),signature);
 // 3.44までの識別情報なしの一時保存は、勤務の職員IDも一致するときだけ移行する。
 for(const withSnapshot of [true,false]){
  const old=harness(null,{current:raw});table(old,mode);
  const storage=mode==='auto'?'koukyu_v4_auto_work':'koukyu_v4_work',work=JSON.parse(old.values.get(storage)),w=work.schedules['2026-10'];
  w.workSignature=w.workSignature.split('|staff:')[0].replace('rules-3.45:','rules-3.44:').replace('auto-rules-6:','auto-rules-5:');w.meta.signature=w.workSignature;w.meta.optimizationPolicy=mode==='auto'?'auto-holidays-3':'quality-first-9';
  if(!withSnapshot)delete w.workSnapshot;
  const updated=harness(null,{current:JSON.parse(old.values.get('koukyu_v4_data')),stored:{[storage]:JSON.stringify(work)}});
  if(mode==='auto')updated.eval("setTab('auto')");
  assert(updated.get('hasTable()'));assert(updated.get('workChanged()'));
  assert.equal(updated.get('metadata()'),null);
  if(withSnapshot){
   const changed=JSON.parse(old.values.get('koukyu_v4_data'));changed.schedules['2026-10'].excludedStaff=['a'];
   const swapped=harness(null,{current:changed,stored:{[storage]:JSON.stringify(work)}});
   if(mode==='auto')swapped.eval("setTab('auto')");
   assert(swapped.get('hasTable()'));assert(swapped.get('workChanged()'));assert.equal(swapped.get('metadata()'),null);
  }
 }
}
(async()=>{
 // 計算中に同じ設定の別人へ入力が変わった場合も、旧応答を採用しない。
 for(const mode of ['normal','auto']){
  let finish;const h=harness(null,{current:raw,response:()=>new Promise(resolve=>finish=resolve)});
  table(h,mode);const original=h.get('schedule().assignments'),task=h.ctx.generate();
  h.eval("data.schedules['2026-10'].excludedStaff=['a']");
  finish({status:'OPTIMAL',seconds:1,assignments:{s0:{'1':'off'}},selectedQuota:{s0:9},search:{done:true}});
  await task;assert.deepEqual(h.get('schedule().assignments'),original);
  assert(h.get('workChanged()'));assert.equal(h.get('metadata()'),null);assert.equal(h.calls.length,1);
 }
 console.log('PASS: 同じ設定の別人の入替・復元・元に戻す操作・並べ替え・旧一時保存の職員照合・古い応答の保護');
})().catch(e=>{console.error(e);process.exitCode=1;});
