'use strict';
// 希望休・固定も含めた連休の回数、通常版の送信、例外表示、旧表の保持。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const rest=require('../../public/consecutive-rest.js'),flow=require('../../public/creation-workflow.js');
const raw={schemaVersion:4,savedTables:[],staff:[{id:'a',name:'職員A',type:'full',monthlyDaysOff:9,nightShiftType:'all',minConsecutiveRest:1},{id:'b',name:'職員B',type:'full',monthlyDaysOff:9,nightShiftType:'all',minConsecutiveRest:1},{id:'c',name:'職員C',type:'full',monthlyDaysOff:9,nightShiftType:'all'}],
 schedules:{'2026-10':{requests:{a:[4,5]},assignments:{},history:{}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
(async()=>{
 // 希望休・固定・通常の公休による連休をすべて同じように数える。
 const fixed=d=>[4,5,10].includes(d);
 assert.deepEqual(rest.counted({'4':'off','5':'off','10':'off','11':'off','20':'off','21':'off'},31,fixed),[{start:4,end:5},{start:10,end:11},{start:20,end:21}]);

 // 送信：連休の設定をした人がいるときだけ。署名の先頭は据え置き。おまかせには送らない。
 const h=harness(null,{current:raw});
 assert.equal(h.get('inputData().p.restCountBalance'),true);assert(h.get('inputData().signature').startsWith('rules-3.73:'));
 const none=harness(null,{current:{...raw,staff:raw.staff.map(({minConsecutiveRest,...s})=>s)}});
 assert.equal(none.eval('inputData().p.restCountBalance'),undefined);

 // 確認欄：希望休だけの連休も数え、実際の回数の差を示す。
 const over=harness(raw);over.eval("schedule().assignments={a:{'4':'off','5':'off','8':'off','9':'off','14':'off','15':'off','20':'off','21':'off'},b:{'3':'off','4':'off'},c:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
 assert(over.nodes.view.text.includes('連休の回数の差：1〜4回（差3回） ・ 1回を超えています'));
 const ok=harness(raw);ok.eval("schedule().assignments={a:{'4':'off','5':'off','8':'off','9':'off'},b:{'3':'off','4':'off'},c:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
 assert(ok.nodes.view.text.includes('連休の回数の差：1〜2回（差1回）（守れています）'));

 // 旧方式の作業表は残し、古い公平性の例外を現行の違反として見せない。
 const legacy=harness(null,{current:raw});legacy.eval("schedule().assignments={a:{'4':'off','5':'off','8':'off','9':'off'},b:{'3':'off','4':'off'},c:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE',optimizationPolicy:'quality-first-11',ruleExceptions:[{code:'rest_balance',counts:{s0:1,s1:0},high:2,low:0,count:1}]};render()");
 const legacyWork=JSON.parse(legacy.values.get('koukyu_v4_work'));legacyWork.schedules['2026-10'].workSignature=legacyWork.schedules['2026-10'].workSignature.replace(/,"maxConsecutiveOff":3}(?=\|staff:|$)/,'}').replace(/,"partWeeklyLimit":false}(?=\|staff:|$)/,'}').replace(/,"excludeNightFromConsecutive":true}(?=\|staff:|$)/,'}').replace('rules-3.73:','rules-3.49:');
 const legacyReload=harness(null,{current:raw,stored:{koukyu_v4_work:JSON.stringify(legacyWork)}});
 assert(legacyReload.get('hasTable()'));assert(legacyReload.get('workChanged()'));assert(legacyReload.nodes.view.text.includes('差1回'));
 assert(!legacyReload.nodes.view.text.includes('連休の回数の差が2回'));
 const legacyWithoutSnapshot=JSON.parse(JSON.stringify(legacyWork));delete legacyWithoutSnapshot.schedules['2026-10'].workSnapshot;
 const oldWithoutSnapshot=harness(null,{current:raw,stored:{koukyu_v4_work:JSON.stringify(legacyWithoutSnapshot)}});
 assert(oldWithoutSnapshot.get('hasTable()'));assert(oldWithoutSnapshot.get('workChanged()'));assert(oldWithoutSnapshot.get('Boolean(schedule().workSnapshot)'));
 legacyReload.eval("const record=RosterStorage.capture(data,key(),'旧表','saved-rest-test');record.schedule.meta={status:'FEASIBLE',optimizationPolicy:'quality-first-11',ruleExceptions:[{code:'rest_balance',high:2,low:0,count:1}]};data.savedTables.push(record);testSavedSnapshot(record)");
 assert(legacyReload.nodes.view.text.includes('差1回'));assert(!legacyReload.nodes.view.text.includes('連休の回数の差が2回'));
 assert.equal(legacyReload.get('data.savedTables[0].schedule.meta.ruleExceptions.length'),1);
 legacyReload.eval("data.savedTables[0].schedule.meta={status:'VALID',signature:'rules-3.73:edited',ruleExceptions:[{code:'rest_balance',counts:{s0:3,s1:1},high:3,low:1,count:1}]};testSavedSnapshot(data.savedTables[0])");
 assert(legacyReload.nodes.view.text.includes('連休の回数の差が2回'));

 // 作成結果の例外：名前と回数、最少を確認済み。
 const err={code:'rest_balance',counts:{s0:3,s1:1},high:3,low:1,count:1};
 const made=harness(raw,{response:async()=>({status:'FEASIBLE',assignments:{s0:{'8':'off','9':'off','14':'off','15':'off','20':'off','21':'off'},s1:{'3':'off','4':'off'},s2:{'1':'off'}},seconds:3,ruleExceptions:[err],exceptionCount:0,restBalanceExceptions:1,restBalance:{counts:{s0:3,s1:1},high:3,low:1,excess:1,proven:true},validationErrors:[err],allocation:{overtimeTotal:0,nightSpread:0},search:{done:true},boundaryComplete:true,optimizationPolicy:'quality-first-19'})});
 await made.ctx.generate();
 assert.equal(made.calls[0].input.restCountBalance,true);
 const text=made.nodes.view.text;
 assert(text.includes('連勤・連休・夜勤の端数・日勤の種類の例外：1件'));assert(text.includes('最少を確認済み'));
 assert(text.includes('連休の回数の差が2回（職員A 3回・職員B 1回）'));

 // 手直しで差が開いた場合は、条件違反ではなく例外として表を保つ。
 const edit=harness(raw,{response:async()=>({status:'INVALID',validationErrors:[err],boundaryComplete:true})});
 edit.eval("schedule().assignments={a:{'8':'off'},b:{'1':'off'},c:{'1':'off'}};schedule().workSignature=inputData().signature;");await edit.ctx.validateCurrent();
 assert.equal(edit.get('schedule().meta.status'),'VALID');

 // 候補の比較：夜勤の端数の次、人数不足より上。
 const base={status:'FEASIBLE',assignments:{},allocation:{overtimeTotal:9}};
 assert(flow.compare({...base,restBalanceExceptions:0,staffingShortfallTotal:3},{...base,restBalanceExceptions:1,staffingShortfallTotal:0})<0);
 assert(flow.compare({...base,nightRemainderExceptions:0,restBalanceExceptions:2},{...base,nightRemainderExceptions:1,restBalanceExceptions:0})<0);

 // 3.43までに作った作業表（一時保存に作成時の条件がないもの）も、当時の条件を記録して保持する。
 const old=harness(null,{current:raw});old.eval("setTab('schedule');schedule().assignments={a:{'1':'early'},b:{'1':'off'},c:{'1':'off'}};schedule().workSignature=inputData().signature;render()");
 const work=JSON.parse(old.values.get('koukyu_v4_work')),w=work.schedules['2026-10'];
 w.workSignature=w.workSignature.replace(/,"maxConsecutiveOff":3}(?=\|staff:|$)/,'}').replace(/,"partWeeklyLimit":false}(?=\|staff:|$)/,'}').replace(/,"excludeNightFromConsecutive":true}(?=\|staff:|$)/,'}').replace('rules-3.73:','rules-3.44:').replace(',"nightDistribution":true','').replace(',"overtimeDistribution":true','').replace(',"restCountBalance":true','');delete w.workSnapshot;
 const reopened=harness(null,{current:raw,stored:{koukyu_v4_work:JSON.stringify(work)}});reopened.eval("setTab('schedule')");
 assert(reopened.get('hasTable()'));assert(reopened.get('workChanged()'));assert(reopened.get('Boolean(schedule().workSnapshot)'));
 assert(reopened.nodes.view.text.includes('最新の条件とは異なる条件で作成した表です。'));
 console.log('PASS: 希望休・固定を含む連休の差、通常版の送信、確認欄、例外、手直し、旧表の保持');
})().catch(e=>{console.error(e);process.exitCode=1;});
