'use strict';
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={staff:[{id:'local',name:'職員',type:'full',nightShiftType:'all'}],schedules:{}};
const tick=()=>new Promise(setImmediate);
const answer=mode=>({best:{status:'FEASIBLE',assignments:{s0:{'1':'off'}},seconds:5,allocation:{overtimeTotal:0},...(mode==='auto'?{selectedQuota:{s0:9},autoDetails:{}}:{})},last:null,seconds:5,rounds:[{seconds:5,status:'FEASIBLE'}],done:true,stale:false});
(async()=>{for(const mode of ['normal']){
 let statusCalled=false;
 const first=harness(null,{current:raw,backgroundActual:true,response:async p=>{if(p.action==='start')return {runId:'wrun_TEST'};if(p.action==='status'){statusCalled=true;return new Promise(()=>{});}throw Error('unexpected');}});
 if(mode==='auto')first.eval("setTab('auto')");first.ctx.generate();await tick();
 assert(statusCalled,'status request started');assert(first.values.has('koukyu_background_job_v1'));
 const stored=Object.fromEntries(first.values);
 const reopened=harness(null,{current:raw,stored,backgroundActual:true,response:async p=>{assert.equal(p.action,'status');return {status:'completed',result:answer(mode)};}});
 await tick();await tick();
 assert.equal(reopened.get('state.mode'),mode);assert.equal(reopened.get('hasTable()'),true);assert.equal(reopened.get('schedule().assignments.local[1]'),'off');assert(!reopened.values.has('koukyu_background_job_v1'));
 assert(!reopened.nodes.view.text.includes('以前の作成結果は条件や表が変わったため'),'受け取り済みの作成を、未受け取りとして表示しない');
 // 別の端末画面で条件が変わっていたら、自動的に結果を採用しない。
 const changed=JSON.parse(stored.koukyu_v4_data);changed.schedules['2026-10']??={requests:{},assignments:{}};changed.schedules['2026-10'].requests.local=[2];
 const mismatch=harness(null,{current:changed,stored:{...stored,koukyu_v4_data:JSON.stringify(changed)},backgroundActual:true,response:async()=>{throw Error('must not fetch');}});
 await tick();assert.equal(mismatch.get('hasTable()'),false);assert(mismatch.nodes.notice.textContent.includes('自動で上書きしません'),JSON.stringify({mode,notice:mismatch.nodes.notice.textContent,job:mismatch.values.has('koukyu_background_job_v1')}));assert(mismatch.values.has('koukyu_background_job_v1'));
}
const jobKey='koukyu_background_job_v1',workKey='koukyu_v4_work';
const completed={status:'completed',result:answer('normal')};
// 古い開始応答が最後に到着しても、新しい作成IDだけを復元する。
const starts=[],cancelled=[];
const race=harness(null,{current:raw,backgroundActual:true,response:async request=>{
 if(request.action==='start')return new Promise(resolve=>starts.push(resolve));
 if(request.action==='cancel'){cancelled.push(request.runId);return {status:'cancelled'};}
 return new Promise(()=>{});
}});
const old=race.ctx.generate();await tick();race.ctx.cancelGeneration();race.ctx.generate();await tick();
starts[1]({runId:'wrun_NEW'});await tick();starts[0]({runId:'wrun_OLD'});await old;await tick();
assert.deepEqual(cancelled,['wrun_OLD']);assert.equal(JSON.parse(race.values.get(jobKey)).runId,'wrun_NEW');
async function reopen(from,runId){
 const restored=harness(null,{stored:Object.fromEntries(from.values),backgroundActual:true,response:async request=>{
  assert.equal(request.action,'status');assert.equal(request.runId,runId);return completed;
 }});
 await tick();await tick();
 assert.equal(restored.get('schedule().assignments.local[1]'),'off');assert(!restored.values.has(jobKey));
}
await reopen(race,'wrun_NEW');
// 結果だけが容量不足で書けない時は受け取り情報を残し、再読込・保存の再試行の双方で復元する。
const quota=harness(null,{current:raw,backgroundActual:true,response:async request=>request.action==='start'?{runId:'wrun_QUOTA'}:completed});
const write=quota.ctx.localStorage.setItem;quota.ctx.localStorage.setItem=(key,value)=>{
 if(key===workKey&&Object.keys(JSON.parse(value).schedules).length)throw Error('QuotaExceededError');
 write(key,value);
};
await quota.ctx.generate();assert(quota.get('hasTable()'));assert.equal(JSON.parse(quota.values.get(jobKey)).runId,'wrun_QUOTA');
assert(quota.nodes.view.text.includes('作業表の保存を再試行'));assert(!quota.nodes.view.text.includes('以前の作成結果は条件や表が変わったため'));
await reopen(quota,'wrun_QUOTA');
quota.ctx.localStorage.setItem=write;await quota.click('作業表の保存を再試行','view');
assert(!quota.values.has(jobKey));assert.equal(JSON.parse(quota.values.get(workKey)).schedules['2026-10'].assignments.local[1],'off');
assert(quota.nodes.view.text.includes('新しく作る'));
// ローカルPC版は、従来の計算窓口を使い、画面を開いたまま作成する。
const local=harness(null,{current:raw,response:async()=>({status:'OPTIMAL',seconds:1,assignments:{s0:{'1':'off'}},allocation:{overtimeTotal:0},search:{done:true}})});
local.eval("window.location={hostname:'127.0.0.1'}");await local.ctx.generate();
assert.equal(local.get('hasTable()'),true);assert.equal(local.calls[0].qualityFirst,true);
console.log('PASS: 通常の画面再読込・条件変更時の上書き防止・PCローカル版');})().catch(e=>{console.error(e);process.exit(1);});
