'use strict';
// 編集・閉じる・再作成・保存の一連の操作で、表と作成時の条件を守る。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const notice='最新の条件とは異なる条件で作成した表です。';
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'a',name:'以前の職員A',type:'full',nightShiftType:'none',canOvertime:true,monthlyDaysOff:9},
 {id:'b',name:'以前の職員B',type:'full',nightShiftType:'none',canOvertime:true,monthlyDaysOff:9}],
 schedules:{'2026-10':{assignments:{},requests:{a:[7]},history:{a:Array(7).fill('off'),b:Array(7).fill('off')}}},
 preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[4,4,4],maxReducedSundays:0}}};
const rows={a:{'1':'early','2':'overtime','7':'off'},b:{'1':'late','7':'off'}};
function table(h,mode='normal'){
 if(mode==='auto')h.eval("setTab('auto');schedule().selectedQuota={a:9,b:9};schedule().creationMode='auto'");
 h.ctx.rows=rows;h.eval("schedule().assignments=clone(rows);schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE',boundaryComplete:true,tableSignature:JSON.stringify(rows),allocation:{overtimeTotal:1}};render()");
}
const reopen=h=>harness(null,{current:JSON.parse(h.values.get('koukyu_v4_data')),stored:{
 koukyu_v4_work:h.values.get('koukyu_v4_work'),koukyu_v4_auto_work:h.values.get('koukyu_v4_auto_work')}});
function response(p){return {status:'FEASIBLE',seconds:.1,boundaryComplete:true,
 assignments:Object.fromEntries(p.input.staff.map(st=>[st.id,{'1':'off','7':'off'}])),
 selectedQuota:Object.fromEntries(Object.entries(p.holidayPolicy||{}).map(([sid,q])=>[sid,q.target])),
 allocation:{overtimeTotal:0},overtimeFairness:{minimumSpreadProven:true},
 autoDone:true,autoReason:'quality_preserved',search:{done:true}};}
(async()=>{
 for(const mode of ['normal','auto']){
  const h=harness(null,{current:raw});table(h,mode);
  const original=h.get('schedule().workSnapshot'),sig=h.get('inputData().signature');
  assert(original);assert.equal(h.get('workChanged()'),false);
  h.ctx.toggleRequest('b',3,'off');h.eval("data.staff[0].monthlyDaysOff=10;data.staff[0].name='変更後の職員A';data.staff=data.staff.filter(st=>st.id!=='b');data.staff.push({id:'c',name:'追加した職員C',type:'full',nightShiftType:'none',monthlyDaysOff:9});data.preferences.staffing.requiredStaff=[2,2,2];schedule().history.a[6]='night';save(true);setTab(state.mode==='auto'?'auto':'schedule')");
  assert(h.get('hasTable()'));assert(h.get('workChanged()'));assert.equal(h.get('metadata()'),null);
  assert.deepEqual(h.get('schedule().assignments'),rows);assert.deepEqual(h.get('schedule().workSnapshot'),original);
  assert(h.nodes.view.text.includes(notice));assert(h.nodes.view.text.includes('以前の職員B'));
  assert(h.nodes.view.text.includes('以前の職員A'));assert(h.nodes.view.text.includes('必要人数：朝4人'));
  assert(h.nodes.view.text.includes('この表の残業：合計1回'));assert(!h.nodes.view.text.includes('さらに改善する'));
  assert.deepEqual(h.get('inputData().p.staff.map(st=>st.id)'),['s0','s1']);assert.equal(h.get('inputData().map.s1'),'c');
  const callCount=h.calls.length;await h.ctx.validateCurrent();assert.equal(h.calls.length,callCount);
  // 条件を変えた表を保存する場合も、元の職員・希望・前期・採用日数で保存する。
  h.eval('saveTableDialog()');await h.click('保存する');const saved=h.get('data.savedTables.at(-1)');
  assert.deepEqual(saved.staff.map(st=>st.id),['a','b']);assert.deepEqual(saved.schedule.requests,{a:[7]});
  assert.equal(saved.staff[0].monthlyDaysOff,9);assert.equal(saved.schedule.history.a[6],'off');
  assert.equal(h.get('history().a[6]'),'night');assert(!saved.schedule.workSnapshot);
  assert(!h.get('Object.hasOwn(RosterStorage.persisted(data).schedules["2026-10"],"workSnapshot")'));
  const restored=reopen(h);if(mode==='auto')restored.eval("setTab('auto')");
  assert(restored.get('hasTable()'));assert(restored.get('workChanged()'));
  assert.deepEqual(restored.get('schedule().assignments'),rows);assert(restored.nodes.view.text.includes('以前の職員B'));
  assert(restored.nodes.view.text.includes(notice));
  // 登録を全員オフにしても、直前の表は引き続き表示できる。
  restored.eval("schedule().excludedStaff=data.staff.map(st=>st.id);render()");
  assert(restored.get('hasTable()'));assert(restored.nodes.view.text.includes('以前の職員B'));
  restored.eval("data.staff=[];save(true);setTab('requests');setTab(state.mode==='auto'?'auto':'schedule')");
  assert(restored.get('hasTable()'));assert(restored.nodes.view.text.includes('以前の職員B'));
  const emptyRegistry=reopen(restored);if(mode==='auto')emptyRegistry.eval("setTab('auto')");
  assert(emptyRegistry.get('hasTable()'));assert(emptyRegistry.nodes.view.text.includes('以前の職員B'));
  // 成立しない・時間切れ・通信失敗のどの場合も直前の表を消さない。
  for(const outcome of ['INFEASIBLE','UNKNOWN','INVALID_INPUT','offline']){
   const f=harness(null,{current:raw,response:async()=>{if(outcome==='offline')throw Error('offline');return {status:outcome,seconds:.1,errors:['入力を確認'],autoDone:true};}});
   table(f,mode);f.ctx.toggleRequest('a',5,'off');const before=f.get('schedule().workSnapshot');
   await f.ctx.generate('new');assert(f.get('hasTable()'),outcome);assert.deepEqual(f.get('schedule().assignments'),rows);
   assert.deepEqual(f.get('schedule().workSnapshot'),before);assert(f.get('workChanged()'));
   assert(f.nodes.view.text.includes(notice));assert.equal(f.calls[0].initialAssignments,undefined);
  }
  // 古い応答は採用しない。計算の途中で離れても、端末には前の表が残る。
  let finish;const pending=harness(null,{current:raw,response:async()=>new Promise(resolve=>finish=resolve)});
  table(pending,mode);const task=pending.ctx.generate('new');
  const during=reopen(pending);if(mode==='auto')during.eval("setTab('auto')");
  assert.deepEqual(during.get('schedule().assignments'),rows);
  pending.eval("schedule().requests.a.push(5)");finish(response(pending.calls[0]));await task;
  assert.deepEqual(pending.get('schedule().assignments'),rows);assert(pending.get('workChanged()'));
  // 新しく作れた時だけ置換し、以後は新しい条件で一時保存する。
  const success=harness(null,{current:raw,response:async p=>response(p)});table(success,mode);
  success.ctx.toggleRequest('a',5,'off');await success.ctx.generate('improve');
  assert(success.get('hasTable()'));assert.equal(success.get('workChanged()'),false);
  assert(!success.nodes.view.text.includes(notice));assert.equal(success.calls[0].initialAssignments,undefined);
  assert.deepEqual(success.get('schedule().workSnapshot.schedule.requests.a'),[5,7]);
  assert.equal(success.get('schedule().assignments.a["1"]'),'off');
 }
 // 元の条件に戻せば案内を消し、その表を追加改善できる。
 const undo=harness(null,{current:raw});table(undo);const initial=undo.get('inputData().signature');
 undo.ctx.toggleRequest('a',3,'off');assert(undo.get('workChanged()'));undo.ctx.toggleRequest('a',3,'off');
 assert.equal(undo.get('inputData().signature'),initial);assert(!undo.get('workChanged()'));
 assert(!undo.nodes.view.text.includes(notice));assert.equal(undo.get('metadata().status'),'FEASIBLE');
 // 前の月にも作成時の条件を残し、共通の職員条件を編集しても保持する。
 undo.eval("state.month=9;render();schedule().assignments=clone(rows);schedule().workSignature=inputData().signature;render();state.month=10;data.staff[0].monthlyDaysOff=10;save(true);render()");
 const both=reopen(undo);both.eval('state.month=9;render()');assert(both.get('workChanged()'));assert.deepEqual(both.get('schedule().assignments'),rows);
 // 判定方式の更新後も旧署名の表を保持し、旧証明を新しい計算へ流用しない。
 for(const mode of ['normal','auto'])for(const snapshot of [true,false]){
  const old=harness(null,{current:raw});table(old,mode);
  const storage=mode==='normal'?'koukyu_v4_work':'koukyu_v4_auto_work',work=JSON.parse(old.values.get(storage)),w=work.schedules['2026-10'];
  w.workSignature=w.workSignature.replace('rules-3.44:','rules-3.35:').replace('auto-rules-5:','auto-rules-4:');
  w.meta={...w.meta,status:'OPTIMAL',optimizationPolicy:mode==='normal'?'quality-first-8':'auto-holidays-2',overtimeFairness:{minimumSpreadProven:true}};
  if(!snapshot)delete w.workSnapshot;
  const updated=harness(null,{current:JSON.parse(old.values.get('koukyu_v4_data')),stored:{[storage]:JSON.stringify(work)}});
  if(mode==='auto')updated.eval("setTab('auto')");
  assert(updated.get('hasTable()'));assert(updated.get('workChanged()'));assert.equal(updated.get('metadata()'),null);
  assert.deepEqual(updated.get('schedule().assignments'),rows);assert(updated.get('schedule().workSnapshot'));
  assert(updated.nodes.view.text.includes(notice));assert.equal(updated.calls.length,0);
  assert.deepEqual(updated.get('history().a'),Array(7).fill('off'));
 }
 // 壊れた条件スナップショットは表示せず、正常な入力データを保護する。
 const corrupt=JSON.parse(undo.values.get('koukyu_v4_work'));corrupt.schedules['2026-10'].workSnapshot.staff[0].type='wrong';
 const bad=harness(null,{current:JSON.parse(undo.values.get('koukyu_v4_data')),stored:{koukyu_v4_work:JSON.stringify(corrupt)}});
 assert.equal(bad.get('state.loadError'),false);assert(!bad.get('hasTable()'));assert.equal(bad.get('data.staff[0].type'),'full');
 // 作業用キーだけの保存が失敗したら、表を保持しながら知らせる。
 const quota=harness(null,{current:raw}),write=quota.ctx.localStorage.setItem;
 quota.ctx.localStorage.setItem=(key,value)=>{if(key==='koukyu_v4_work')throw Error('Quota');write(key,value);};table(quota);
 assert(quota.get('hasTable()'));assert(quota.nodes.notice.text.includes('一時保存できませんでした'));
 console.log('PASS: 両方式の条件変更・職員追加削除・全員オフ・元の条件で保存印刷・再読込・前期保持・失敗と古い応答・計算中に離れる・成功時だけ置換・条件を戻す・月切替・壊れた記録と容量不足');
})().catch(e=>{console.error(e);process.exit(1);});
