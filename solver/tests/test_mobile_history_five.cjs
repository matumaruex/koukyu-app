'use strict';
// 5日入力と旧7日の保持、取り込み、週上限の撤去、確認範囲の表示。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const oldHistory=['late','overtime','off','early','night','nightOff','off'];
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'a',name:'職員A',type:'full',monthlyDaysOff:9,nightShiftType:'all',maxConsecutive:3},
 {id:'b',name:'職員B',type:'part',monthlyDaysOff:11,nightShiftType:'none',startTime:'09:00',endTime:'17:00',maxDaysPerWeek:1}],
 schedules:{'2026-10':{requests:{a:[7]},assignments:{},history:{a:oldHistory}}}};
const rows=h=>h.nodes['dialog-body'].all('div').find(e=>e.className==='history-rows');
const staffSelector=h=>h.nodes['dialog-body'].all('select')[0];
function fill(h,values){rows(h).all('select').forEach((s,i)=>{s.value=values[i];s.onchange();});}
(async()=>{
 const h=harness(null,{current:raw});h.ctx.editHistory();
 assert.equal(rows(h).all('select').length,5);
 assert.deepEqual(rows(h).all('select').map(s=>s.value),oldHistory.slice(-5));
 assert(rows(h).text.includes('10月11日'));assert(rows(h).text.includes('10月15日'));assert(!rows(h).text.includes('10月10日'));
 const first=rows(h).all('select')[0];first.value='late';first.onchange();
 staffSelector(h).value='b';staffSelector(h).onchange();
 fill(h,['off','part','off','part','off']);await h.click('入力した勤務を保存');
 assert.equal(h.nodes.dialog.open,false);
 assert.deepEqual(h.get('schedule().history.a'),['late','overtime','late','early','night','nightOff','off']);
 assert.deepEqual(h.get('schedule().history.b'),['off','part','off','part','off']);
 assert.equal(h.get('inputData().p.history.s0.length'),7);assert.equal(h.get('inputData().p.history.s1.length'),5);
 assert.equal(h.get('inputData().p.partWeeklyLimit'),false);
 h.eval('editStaff(data.staff[1])');assert(!h.nodes['dialog-body'].text.includes('週の出勤上限'));
 h.nodes['dialog-body'].all('form')[0].onsubmit({preventDefault(){}});assert.equal(h.get('data.staff[1].maxDaysPerWeek'),1);
 const re=harness(null,{current:JSON.parse(h.values.get('koukyu_v4_data'))});re.ctx.editHistory();
 staffSelector(re).value='b';staffSelector(re).onchange();assert.deepEqual(rows(re).all('select').map(s=>s.value),['off','part','off','part','off']);

 // 途中入力は保存しない。保存失敗では元の前期実績を保ち、やり直せる。
 const partial=harness(null,{current:raw});partial.ctx.editHistory();staffSelector(partial).value='b';staffSelector(partial).onchange();fill(partial,['off','part','off','part','']);
 await partial.click('入力した勤務を保存');assert(partial.nodes['dialog-body'].text.includes('5日分をすべて選んでください'));assert.equal(partial.get('schedule().history.b??null'),null);
 const q=harness(null,{current:raw,quota:true}),before=q.get('schedule().history');q.ctx.editHistory();staffSelector(q).value='b';staffSelector(q).onchange();fill(q,['off','part','off','part','off']);
 await q.click('入力した勤務を保存');assert.deepEqual(q.get('schedule().history'),before);assert(q.nodes.dialog.open);assert(q.nodes['dialog-body'].text.includes('この端末に保存できませんでした'));

 // 旧7日の表は当時の条件を残す。新規作成へ旧週上限の証明を流用しない。
 const old=harness(null,{current:raw});old.eval("schedule().assignments={a:{'1':'early'},b:{'1':'part'}};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE',signature:inputData().signature};render()");
 const work=JSON.parse(old.values.get('koukyu_v4_work')),w=work.schedules['2026-10'];delete w.workSnapshot;
 w.workSignature=w.workSignature.replace(/,"partWeeklyLimit":false}(?=\|staff:|$)/,'}').replace('rules-3.72:','rules-3.61:');w.meta.signature=w.workSignature;w.meta.optimizationPolicy='quality-first-16';
 const restored=harness(null,{current:JSON.parse(old.values.get('koukyu_v4_data')),stored:{koukyu_v4_work:JSON.stringify(work)}});
 assert(restored.get('hasTable()'));assert(restored.get('workChanged()'));assert.equal(restored.get('metadata()'),null);
 assert.deepEqual(restored.get('schedule().workSnapshot.schedule.history.a'),oldHistory);assert.deepEqual(restored.get('schedule().workSnapshot.schedule.requests.a'),[7]);

 // 保存済みの前期の実績は7日分保持し、手入力済みの5日分は上書きしない。
 h.ctx.record={period:'2026-09',staff:raw.staff,schedule:{assignments:{a:Object.fromEntries(Array.from({length:30},(_,i)=>[String(i+1),'off']))}}};
 const imported=h.get("RosterStorage.takeHistory(record,'2026-10',data.staff,{b:['off','part','off','part','off']},SHIFT)");
 assert.equal(imported.history.a.length,7);assert.deepEqual(imported.history.b,['off','part','off','part','off']);

 // 5日で判定できない長い持ち越しを、確認済みと表示しない。
 h.eval("schedule().assignments={a:{'1':'off'},b:{'1':'part'}};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE',signature:inputData().signature,optimizationPolicy:OPTIMIZATION_POLICY,boundaryComplete:false,historyVerification:{issues:[{staff:'s0',provided:5,required:6,reasons:['consecutive']}]},allocation:{minimumOvertimeProven:true}};render()");
 assert(h.nodes.view.text.includes('前期をまたぐ条件の確認が未完了'));assert(h.nodes.view.text.includes('長い連勤の持ち越し'));
 assert(h.nodes.view.text.includes('入力5日／確認に必要6日'));assert(h.eval('allocationSummary()').text.includes('公休と仮定した範囲で'));
 // 背景作成へ5日分と週上限なしの指定を渡す。
 let sent;
 const remote=harness(null,{current:{...raw,schedules:{'2026-10':{requests:{},assignments:{},history:{a:Array(5).fill('off'),b:Array(5).fill('off')}}}},backgroundActual:true,response:async p=>{
  if(p.action==='start'){sent=p.input;return {runId:'wrun_HISTORY'};}
  return {status:'completed',result:{best:{status:'FEASIBLE',assignments:{s0:{'1':'off'},s1:{'1':'part'}},seconds:1},seconds:1,rounds:[],done:true}};
 }});
 await remote.ctx.generate('new');assert.equal(sent.partWeeklyLimit,false);assert.equal(sent.history.s0.length,5);assert.equal(sent.history.s1.length,5);assert(remote.get('hasTable()'));
 // 手直し後の検査でも、確認不足の情報を画面へ引き継ぐ。
 for(const status of ['VALID','INVALID']){
  const verification={providedDays:{s0:5,s1:5},issues:[{staff:'s0',provided:5,required:6,reasons:['consecutive']}]};
  const checked=harness(null,{current:raw,response:async()=>({status,boundaryComplete:false,historyVerification:verification,...(status==='INVALID'?{validationErrors:[{code:'consecutive',staff:'s0',day:2,actual:7,limit:6,plusOne:false}]}:{})})});
  checked.eval("schedule().assignments={a:{'1':'off'},b:{'1':'part'}};schedule().workSignature=inputData().signature");await checked.ctx.validateCurrent();
  assert.deepEqual(checked.get('schedule().meta.historyVerification'),verification);assert(checked.nodes.view.text.includes('前期をまたぐ条件の確認が未完了'));
 }
 console.log('PASS: 前期5日入力・旧7日と保存表と希望の保持・週上限撤去・取り込み・保存失敗・確認不足の表示');
})().catch(e=>{console.error(e);process.exitCode=1;});
