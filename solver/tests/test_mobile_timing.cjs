'use strict';
// 実際の画面の作成処理を使い、通常と追加の設定・元の表の保持を確認する。
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../../public/mobile.js'), 'utf8');
const start = source.indexOf('async function generate(');
const end = source.indexOf('// 条件と表の両方', start);
assert(start >= 0 && end > start);
async function sent(seconds, existing) {
  let payload;
  const assignments = existing ? {local:{'1':'off'}} : {};
  const schedule = {assignments, requestReviewed:{local:true}};
  const ctx = {state:{loadError:false}, activeStaff:()=>[{id:'local'}], schedule:()=>schedule,
    showCreationSection:()=>{}, inputData:()=>({p:{year:2026,month:3},map:{remote:'local'},signature:'same'}),
    confirm:()=>true, precheck:()=>[], hasTable:()=>existing, ready:()=>existing,
    metadata:()=>existing?{status:'DRAFT'}:undefined, toRemote:()=>({remote:{'1':'off'}}),
    tableCheckIdentity:()=> 'same', notify:()=>{}, busy:()=>{}, render:()=>{},
    api:async p=>{payload=JSON.parse(JSON.stringify(p));return {status:'UNKNOWN'};}};
  vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
  await ctx.generate(seconds);
  assert.deepEqual(schedule.assignments,assignments);
  return payload;
}
(async()=>{
  for(const existing of [false,true]){
    const normal=await sent(15,existing),extended=await sent(60,existing);
    assert.equal(normal.adaptive,true);assert.equal(extended.adaptive,false);
    assert.equal(normal.seconds,60);assert.equal(extended.seconds,60);
    for(const payload of [normal,extended]){
      assert.equal(payload.allowStaffingShortfall,true);
      assert.equal(payload.allowNightShortfall,true);
      assert.equal(!!payload.initialAssignments,existing);
    }
    console.log(`PASS: ${existing?'保存済み':'新規'}の通常・追加計算を区別し、時間切れでも表を保持`);
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
