'use strict';
// 連休なし（3.38）：職員設定→送信、数え方（希望休・前期の境目）、例外の表示と表の印、手直しの判定、候補の比較。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const rest=require('../../public/consecutive-rest.js'),flow=require('../../public/creation-workflow.js');
const raw={schemaVersion:4,savedTables:[],staff:[{id:'a',name:'職員A',type:'full',monthlyDaysOff:9,nightShiftType:'all',canOvertime:true},{id:'b',name:'職員B',type:'full',monthlyDaysOff:9,nightShiftType:'all'}],
 schedules:{'2026-10':{requests:{a:[10,11]},assignments:{},history:{}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const select=h=>h.nodes['dialog-body'].all('select').find(s=>s.children.some(o=>o.text==='連休なし'));
(async()=>{
 // 数え方：計算が作った連続公休だけ。希望休どうし・前期の実績は数えない。明けは休みに数えない。
 const fixed=d=>[10,11].includes(d);
 assert.deepEqual(rest.forbidden({'1':'off','2':'off','3':'early','10':'off','11':'off','12':'off','20':'nightOff','21':'off'},31,fixed,false),[{start:1,end:2,count:1},{start:11,end:12,count:1}]);
 assert.deepEqual(rest.forbidden({'1':'off','2':'early'},31,()=>false,true),[{start:0,end:1,count:1}]);
 assert.deepEqual(rest.forbidden({'1':'off','2':'early'},31,d=>d===1,true),[]);
 assert.deepEqual(rest.forbidden({'1':'off','2':'off','3':'off'},31,()=>false,false),[{start:1,end:3,count:2}]);
 for(const [value,min] of [['yes',0],[1,0],[true,1]])assert.throws(()=>rest.checkNone(value,min));
 assert.equal(rest.checkNone(undefined,0),false);

 // 職員設定：「連休」に連休なしを追加。指定がなければ送信内容も署名も今までどおり。
 const h=harness(null,{current:raw});
 const before=h.get('inputData().signature');assert(before.startsWith('rules-3.45:'));
 assert(!Object.hasOwn(h.get('inputData().p.staff[0]'),'noConsecutiveRest'));
 h.eval("setTab('staff');editStaff(data.staff[0])");
 const s=select(h);assert(s);assert.equal(s.value,'0');assert.deepEqual(s.children.map(o=>o.text),['指定なし','連休なし','月1回以上','月2回以上']);
 s.value='none';h.nodes['dialog-body'].all('form')[0].onsubmit({preventDefault(){}});
 assert.equal(h.get('data.staff[0].noConsecutiveRest'),true);assert.equal(h.get('data.staff[0].minConsecutiveRest'),0);
 h.eval("setTab('schedule')");
 assert.equal(h.get('inputData().p.staff[0].noConsecutiveRest'),true);assert(!Object.hasOwn(h.get('inputData().p.staff[0]'),'minConsecutiveRest'));
 assert.notEqual(h.get('inputData().signature'),before);assert(h.get('inputData().signature').startsWith('rules-3.45:'));
 h.eval("editStaff(data.staff[0])");assert.equal(select(h).value,'none');
 select(h).value='0';h.nodes['dialog-body'].all('form')[0].onsubmit({preventDefault(){}});
 assert.equal(h.get('data.staff[0].noConsecutiveRest'),false);assert.equal(h.get('inputData().signature'),before);
 assert.throws(()=>h.ctx.checkBackup({staff:[{...raw.staff[0],noConsecutiveRest:true,minConsecutiveRest:1}],schedules:{}}));
 assert.throws(()=>h.ctx.checkBackup({staff:[{...raw.staff[0],noConsecutiveRest:'yes'}],schedules:{}}));

 // 作成結果の例外：一覧・最少確認済み・表の印（連休の両日）。
 const none={...raw,staff:[{...raw.staff[0],noConsecutiveRest:true},raw.staff[1]]};
 const restError={code:'no_consecutive_rest',staff:'s0',day:5,start:4,end:5,count:1};
 const made=harness(none,{response:async()=>({status:'FEASIBLE',assignments:{s0:{'4':'off','5':'off','10':'off','11':'off'},s1:{'1':'off'}},seconds:3,ruleExceptions:[restError],exceptionCount:0,exceptionsProvenMinimum:true,restExceptionCount:1,restExceptionsProvenMinimum:true,noConsecutiveRest:{minimum:1,proven:true},validationErrors:[restError],allocation:{overtimeTotal:0,nightSpread:0},search:{done:true},boundaryComplete:true,optimizationPolicy:'quality-first-10'})});
 await made.ctx.generate();
 assert.equal(made.calls[0].input.staff[0].noConsecutiveRest,true);
 const text=made.nodes.view.text;
 assert(text.includes('連勤・連休・夜勤の端数・日勤の種類の例外：1件'));assert(text.includes('最少を確認済み'));
 assert(text.includes('職員Aさん 10月19日（月）〜10月20日（火）：連休（連休なしの設定）'));
 assert(text.includes('職員A：連休なし ・ 例外1件（10/19〜10/20）'));
 const marked=made.nodes.view.all('td').filter(td=>(td.attributes['aria-label']||'').includes('（例外）')).map(td=>td.attributes['aria-label'].split(' ').slice(0,2).join(' '));
 assert.deepEqual(marked,['職員A 10月19日（月）','職員A 10月20日（火）']);

 // 希望休だけの連休は例外にせず「守れています」。
 const ok=harness(none);ok.eval("schedule().assignments={a:{'10':'off','11':'off','12':'early'},b:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
 assert(ok.nodes.view.text.includes('職員A：連休なし（守れています）'));

 // 手直しで連休を作った場合は、条件違反ではなく例外として表を保つ。
 const edit=harness(none,{response:async()=>({status:'INVALID',validationErrors:[restError],boundaryComplete:true})});
 edit.eval("schedule().assignments={a:{'4':'off','5':'off'},b:{'1':'off'}};schedule().workSignature=inputData().signature;");await edit.ctx.validateCurrent();
 assert.equal(edit.get('schedule().meta.status'),'VALID');assert.equal(edit.get('schedule().meta.ruleExceptions.length'),1);

 // 候補の比較：連休なしの例外が少ない表を最優先。
 const base={status:'FEASIBLE',assignments:{},allocation:{overtimeTotal:9}};
 assert(flow.compare({...base,restExceptionCount:0,exceptionCount:2},{...base,restExceptionCount:1,exceptionCount:0})<0);
 console.log('PASS: 連休なしの数え方（希望休・前期の境目・明け）、設定と送信・署名の互換、例外の一覧と最少表示・表の印、守れている表示、手直しの判定、候補の比較');
})().catch(e=>{console.error(e);process.exitCode=1;});
