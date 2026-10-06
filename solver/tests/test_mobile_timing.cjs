'use strict';
// 通常は新規作成、追加計算は作業中の結果を改善し、保存一覧に触れない。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
async function sent(seconds,existing){
 const h=harness({staff:[{id:'local',name:'職員',type:'full',nightShiftType:'all'}],schedules:{}});
 if(existing)h.eval("schedule().assignments={local:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE'};");
 await h.ctx.generate(seconds);
 assert.deepEqual(h.get('schedule().assignments'),{});
 assert.deepEqual(h.get('data.savedTables'),[]);
 assert.equal(h.confirmations.length,0);
 return h.calls[0];
}
(async()=>{
 for(const existing of [false,true]){
  const normal=await sent(15,existing),extended=await sent(60,existing);
  assert.equal(normal.adaptive,true);assert.equal(extended.adaptive,false);
  assert.equal(normal.seconds,60);assert.equal(extended.seconds,60);
  assert.equal(normal.initialAssignments,undefined);
  assert.equal(!!extended.initialAssignments,existing);
  for(const p of [normal,extended]){assert.equal(p.allowStaffingShortfall,true);assert.equal(p.allowNightShortfall,true);}
 }
 console.log('PASS: 通常は前の表を参照せず、追加だけ比較。15/60秒・失敗時の表示・保存一覧を確認');
})().catch(e=>{console.error(e);process.exitCode=1;});
