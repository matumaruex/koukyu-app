'use strict';
// 通常・おまかせの中止、通信の切断、元の表と古い応答の保護を確認する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={schemaVersion:4,savedTables:[],staff:[{id:'a',name:'職員A',type:'full',monthlyDaysOff:9,nightShiftType:'all'}],
 schedules:{'2026-10':{requests:{a:[3]},assignments:{},history:{a:Array(7).fill('off')}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const reply={status:'FEASIBLE',assignments:{s0:{'1':'night'}},seconds:60,allocation:{overtimeTotal:0},search:{done:false,continueRecommended:true},selectedQuota:{s0:9}};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function findRequests(h,count){for(let i=0;i<30&&h.calls.length<count;i++)await tick();assert.equal(h.calls.length,count);}
function cancel(h){const b=h.nodes.view.all('button').find(e=>e.text==='作成を中止する');assert(b,'中止ボタン');assert.notEqual(b.disabled,true);b.click();}
(async()=>{
 for(const mode of ['normal','auto'])for(const existing of [false,true]){
  const pending=[];const h=harness(null,{current:raw,response:async(body,opts)=>new Promise(resolve=>pending.push({body,opts,resolve}))});
  if(mode==='auto')h.eval("setTab('auto')");
  if(existing)h.eval("schedule().assignments={a:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE'};render()");
  const previous=h.get('schedule().assignments'),saved=h.get('data.savedTables'),history=h.get('history()');
  const first=h.ctx.generate('new');await findRequests(h,1);assert(h.get('state.busy'));
  cancel(h);assert(pending[0].opts.signal.aborted);assert.equal(h.get('state.busy'),false);
  assert.deepEqual(h.get('schedule().assignments'),previous);assert.deepEqual(h.get('data.savedTables'),saved);assert.deepEqual(h.get('history()'),history);
  assert(h.nodes.notice.textContent.includes('作成を中止しました'));
  // 中止後すぐに別の計算を開始。古い応答が新しい計算を終了・上書きしない。
  const second=h.ctx.generate('new');await findRequests(h,2);pending[0].resolve(reply);await first;
  assert(h.get('state.busy'));assert.deepEqual(h.get('schedule().assignments'),previous);
  assert.equal(h.eval('state.activeRequest.signal'),pending[1].opts.signal);
  cancel(h);assert(pending[1].opts.signal.aborted);pending[1].resolve(reply);await second;
  assert.equal(h.get('state.busy'),false);assert.deepEqual(h.get('schedule().assignments'),previous);
 }
 // 一回目の候補を受け取った後の続き計算でも中止でき、途中候補は採用しない。
 for(const mode of ['normal','auto']){
  let resolveNext,secondSignal;const h=harness(null,{current:raw,response:async(body,opts)=>{
   if(h.calls.length===1)return reply;secondSignal=opts.signal;return new Promise(resolve=>resolveNext=resolve);
  }});
  if(mode==='auto')h.eval("setTab('auto')");
  const task=h.ctx.generate('new');await findRequests(h,2);cancel(h);assert(secondSignal.aborted);
  resolveNext(reply);await task;assert.equal(h.get('hasTable()'),false);assert.equal(h.calls.length,2);
 }
 // 本物の fetch と同じ AbortError が返っても、時間切れとは表示しない。
 const h=harness(null,{current:raw,response:async(body,opts)=>new Promise((resolve,reject)=>opts.signal.addEventListener('abort',()=>{const e=Error('aborted');e.name='AbortError';reject(e);} ))});
 const task=h.ctx.generate();await findRequests(h,1);cancel(h);await task;
 assert(h.nodes.notice.textContent.includes('中止'));assert(!h.nodes.notice.textContent.includes('時間切れ'));
 // 実際の HTTP 通信でも中断されることを、応答を待たせたローカルサーバーで確認する。
 const http=require('node:http');let arrived,closed;
 const incoming=new Promise(resolve=>arrived=resolve),connectionClosed=new Promise(resolve=>closed=resolve);
 const server=http.createServer((req,res)=>{req.on('close',closed);arrived();});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 try{
  const real=harness(null,{current:raw});real.ctx.fetch=(url,opts)=>fetch(`http://127.0.0.1:${server.address().port}${url}`,opts);
  const realTask=real.ctx.generate();await incoming;cancel(real);await realTask;
  let watchdog;try{await Promise.race([connectionClosed,new Promise((_,reject)=>watchdog=setTimeout(()=>reject(Error('HTTP connection was not closed')),5000))]);}finally{clearTimeout(watchdog);}
  assert(real.nodes.notice.textContent.includes('中止'));assert.equal(real.get('state.busy'),false);
 }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
 console.log('PASS: 通常・おまかせの中止、通信、続き停止、元表・保存・前期、遅延応答と再作成の保護');
})().catch(e=>{console.error(e);process.exitCode=1;});
