'use strict';
// 作業中の表が開き直しても戻ること、条件が変われば戻らないこと、固定したマスの表示を確認する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const staff=[{id:'a',name:'職員A',type:'full',nightShiftType:'all',monthlyDaysOff:9,canOvertime:true},{id:'b',name:'職員B',type:'full',nightShiftType:'all',monthlyDaysOff:9}];
const raw={staff,schedules:{'2026-10':{assignments:{},requests:{a:[7]},locked:{a:{'8':'early'}}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[4,4,4],maxReducedSundays:3}}};
const table="schedule().assignments={a:{'1':'early','8':'early'},b:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE',boundaryComplete:true,tableSignature:JSON.stringify(schedule().assignments)};render();";
const reopen=(from,extra={})=>harness(null,{current:{...JSON.parse(from.values.get('koukyu_v4_data')),...extra},stored:{koukyu_v4_work:from.values.get('koukyu_v4_work')}});
(async()=>{
 // 作業中の表は入力データとは別のキーに残し、入力データ・書き出しには入れない。
 const h=harness(raw);h.eval(table);
 const work=JSON.parse(h.values.get('koukyu_v4_work'));
 assert.deepEqual(work.schedules['2026-10'].assignments.a,{'1':'early','8':'early'});
 assert.equal(work.schedules['2026-10'].meta.status,'FEASIBLE');
 assert.deepEqual(JSON.parse(h.values.get('koukyu_v4_data')).schedules['2026-10'].assignments,{});
 const exported=JSON.parse(await h.ctx.backupFile().text());
 assert.deepEqual(exported.schedules['2026-10'].assignments,{});
 assert.equal(h.timers.length,0);

 // 開き直すと、表と確認結果がそのまま戻る。
 const reopened=reopen(h);
 assert.equal(reopened.get('hasTable()'),true);
 assert.equal(reopened.get('metadata().status'),'FEASIBLE');
 assert(reopened.nodes.view.text.includes('作業中の公休表'));
 assert(reopened.nodes.view.text.includes('ページを開き直しても残ります'));
 assert.equal(reopened.calls.length,0);

 // 希望休の達成基準が変わるため旧作業表を無効化。入力・固定・保存表は保持する。
 const legacy=JSON.parse(JSON.stringify(work));
 legacy.schedules['2026-10'].workSignature=legacy.schedules['2026-10'].workSignature.replace('rules-3.31:','rules-3.30:');
 legacy.schedules['2026-10'].meta.signature=legacy.schedules['2026-10'].workSignature;
 legacy.schedules['2026-10'].meta.optimizationPolicy='quality-first-4';
 const current=JSON.parse(h.values.get('koukyu_v4_data'));
 const upgraded=harness(null,{current,stored:{koukyu_v4_work:JSON.stringify(legacy)}});
 assert.equal(upgraded.get('hasTable()'),false);
 assert.equal(upgraded.get('metadata()'),null);
 assert.deepEqual(upgraded.get('data.savedTables'),h.get('data.savedTables'));
 assert.deepEqual(upgraded.get('schedule().locked'),h.get('schedule().locked'));
 const changed=harness(null,{current:{...current,staff:staff.map(s=>({...s,monthlyDaysOff:10}))},stored:{koukyu_v4_work:JSON.stringify(legacy)}});
 assert.equal(changed.get('hasTable()'),false);

 // 「新しく作る」の結果も、計算が終わった時点で残る。
 const made=harness(raw,{response:async p=>p.action==='validate'?{status:'VALID',validationErrors:[],boundaryComplete:true}:{status:'FEASIBLE',assignments:{s0:{'1':'early'},s1:{'1':'off'}},boundaryComplete:true,seconds:1}});
 await made.ctx.generate('new');
 assert.deepEqual(JSON.parse(made.values.get('koukyu_v4_work')).schedules['2026-10'].assignments.a,{'1':'early'});
 assert.equal(reopen(made).get('hasTable()'),true);

 // 条件を変えると表は消え、開き直しても戻らない。
 reopened.ctx.toggleRequest('b',3,'off');
 assert.equal(reopened.get('hasTable()'),false);
 assert.deepEqual(JSON.parse(reopened.values.get('koukyu_v4_work')).schedules,{});
 assert.equal(reopen(reopened).get('hasTable()'),false);

 // 残っていた表の後で条件が変わっていた場合も、古い表は出さない。
 const stale=reopen(h,{staff:staff.map(s=>({...s,monthlyDaysOff:10}))});
 assert.equal(stale.get('hasTable()'),false);
 assert.deepEqual(JSON.parse(stale.values.get('koukyu_v4_work')).schedules,{});

 // 壊れた作業データは無視し、入力データは通常どおり読み込む。
 for(const bad of ['not json','{"version":1,"schedules":{"2026-10":{"workSignature":"x","assignments":{"a":{"1":"???"}}}}}','{"version":9,"schedules":{}}']){
  const b=harness(null,{current:JSON.parse(h.values.get('koukyu_v4_data')),stored:{koukyu_v4_work:bad}});
  assert.equal(b.get('state.loadError'),false);assert.equal(b.get('hasTable()'),false);assert.deepEqual(b.get('history()'),{});
 }

 // 容量不足でも動作は止めない（作業中の表が残らないだけ）。
 const quota=harness(raw,{quota:true});quota.eval(table);
 assert.equal(quota.values.has('koukyu_v4_work'),false);assert.equal(quota.get('hasTable()'),true);

 // 固定したマスを開くとチェックが入っていて、そのまま反映しても固定は外れない。
 const lock=harness(raw,{response:async()=>({status:'VALID',validationErrors:[],boundaryComplete:true})});lock.eval(table);
 lock.eval('editShift(data.staff[0],8)');
 assert.equal(lock.nodes['dialog-body'].all('input').find(e=>e.type==='checkbox').checked,true);
 await lock.click('変更を反映');
 assert.deepEqual(lock.get('schedule().locked.a'),{'8':'early'});
 lock.eval('editShift(data.staff[0],1)');
 assert.equal(lock.nodes['dialog-body'].all('input').find(e=>e.type==='checkbox').checked,false);

 // 表の固定マスには印と読み上げ用の「固定」が付き、凡例も出る。
 lock.eval('state.tab="schedule";render();');
 const labels=lock.nodes.view.all('td').map(td=>td.attributes['aria-label']||'');
 assert.equal(labels.filter(t=>t.includes('（固定）')).length,1);
 assert(labels.some(t=>t.startsWith('職員A')&&t.includes('（固定）')));
 assert(lock.nodes.view.text.includes('太枠のマスは固定した勤務'));
 console.log('PASS: 作業中の表を開き直しても復元、条件変更・古いデータ・壊れたデータでは復元しない、容量不足でも継続、固定マスのチェックと印');
})().catch(e=>{console.error(e);process.exitCode=1;});
