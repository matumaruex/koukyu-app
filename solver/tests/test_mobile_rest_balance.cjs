'use strict';
// 連休の回数の差（3.46）：数え方（希望休・固定だけの連休は数えない）、通常版だけの送信、確認欄の表示、例外の一覧、候補の比較、3.45までの作業表の保持。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const rest=require('../../public/consecutive-rest.js'),flow=require('../../public/creation-workflow.js');
const raw={schemaVersion:4,savedTables:[],staff:[{id:'a',name:'職員A',type:'full',monthlyDaysOff:9,nightShiftType:'all',minConsecutiveRest:1},{id:'b',name:'職員B',type:'full',monthlyDaysOff:9,nightShiftType:'all',minConsecutiveRest:1},{id:'c',name:'職員C',type:'full',monthlyDaysOff:9,nightShiftType:'all'}],
 schedules:{'2026-10':{requests:{a:[4,5]},assignments:{},history:{}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
(async()=>{
 // 数え方：希望休・固定の公休だけでできた連休は数えない。計算が決めた公休を含めば数える。
 const fixed=d=>[4,5,10].includes(d);
 assert.deepEqual(rest.counted({'4':'off','5':'off','10':'off','11':'off','20':'off','21':'off'},31,fixed),[{start:10,end:11},{start:20,end:21}]);

 // 送信：連休の設定をした人がいるときだけ。署名の先頭は据え置き。おまかせには送らない。
 const h=harness(null,{current:raw});
 assert.equal(h.get('inputData().p.restCountBalance'),true);assert(h.get('inputData().signature').startsWith('rules-3.45:'));
 h.eval("setTab('auto')");assert.equal(h.eval('inputData().p.restCountBalance'),undefined);
 const none=harness(null,{current:{...raw,staff:raw.staff.map(({minConsecutiveRest,...s})=>s)}});
 assert.equal(none.eval('inputData().p.restCountBalance'),undefined);

 // 確認欄：比べる人の回数の幅と差。希望休だけの連休（4〜5日）は数えない。
 const over=harness(raw);over.eval("schedule().assignments={a:{'4':'off','5':'off','8':'off','9':'off','14':'off','15':'off','20':'off','21':'off'},b:{'3':'off','4':'off'},c:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
 assert(over.nodes.view.text.includes('連休の回数の差：1〜3回（差2回） ・ 1回を超えています'));
 const ok=harness(raw);ok.eval("schedule().assignments={a:{'4':'off','5':'off','8':'off','9':'off'},b:{'3':'off','4':'off'},c:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
 assert(ok.nodes.view.text.includes('連休の回数の差：1〜1回（差0回）（守れています）'));

 // 作成結果の例外：名前と回数、最少を確認済み。
 const err={code:'rest_balance',counts:{s0:3,s1:1},high:3,low:1,count:1};
 const made=harness(raw,{response:async()=>({status:'FEASIBLE',assignments:{s0:{'8':'off','9':'off','14':'off','15':'off','20':'off','21':'off'},s1:{'3':'off','4':'off'},s2:{'1':'off'}},seconds:3,ruleExceptions:[err],exceptionCount:0,restBalanceExceptions:1,restBalance:{counts:{s0:3,s1:1},high:3,low:1,excess:1,proven:true},validationErrors:[err],allocation:{overtimeTotal:0,nightSpread:0},search:{done:true},boundaryComplete:true,optimizationPolicy:'quality-first-10'})});
 await made.ctx.generate();
 assert.equal(made.calls[0].input.restCountBalance,true);
 const text=made.nodes.view.text;
 assert(text.includes('連勤・連休・夜勤の端数・日勤の種類の例外：1件'));assert(text.includes('最少を確認済み'));
 assert(text.includes('連休の回数の差が2回（職員Aさん3回・職員Bさん1回）'));

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
 w.workSignature=w.workSignature.replace(',"restCountBalance":true','');delete w.workSnapshot;
 const reopened=harness(null,{current:raw,stored:{koukyu_v4_work:JSON.stringify(work)}});reopened.eval("setTab('schedule')");
 assert(reopened.get('hasTable()'));assert(reopened.get('workChanged()'));assert(reopened.get('Boolean(schedule().workSnapshot)'));
 assert(reopened.nodes.view.text.includes('最新の条件とは異なる条件で作成した表です。'));
 console.log('PASS: 連休の回数の差の数え方（希望休・固定だけの連休を除く）、連休の設定がある通常版だけの送信、確認欄、例外の一覧と最少表示、手直しの判定、候補の比較、3.45までの作業表の保持');
})().catch(e=>{console.error(e);process.exitCode=1;});
