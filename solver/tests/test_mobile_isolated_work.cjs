'use strict';
// 職員ごとの1日出勤回避、端末保存・旧表の保持、例外の意味と比較順を確認する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs'),flow=require('../../public/creation-workflow.js');
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'a',name:'職員A',type:'full',monthlyDaysOff:9,fixedDaysOff:true,nightShiftType:'all',maxConsecutive:3},
 {id:'b',name:'職員B',type:'part',monthlyDaysOff:11,nightShiftType:'none',startTime:'09:00',endTime:'17:00'}],
 schedules:{'2026-10':{requests:{a:[6,8]},assignments:{},history:{a:Array(5).fill('off')}}}};
function checkbox(h){const label=h.nodes['dialog-body'].all('label').find(e=>e.text.includes('1日だけの出勤を避ける（休→出勤→休）'));assert(label);return label.all('input')[0];}
const submit=h=>h.nodes['dialog-body'].all('form')[0].onsubmit({preventDefault(){}});
(async()=>{
 const h=harness(null,{current:raw});assert.equal(h.get('data.staff[0].avoidIsolatedWork'),false);assert(!Object.hasOwn(h.get('inputData().p.staff[0]'),'avoidIsolatedWork'));
 h.eval('editStaff(data.staff[0])');assert.equal(checkbox(h).checked,false);checkbox(h).checked=true;submit(h);
 assert.equal(h.get('data.staff[0].avoidIsolatedWork'),true);assert.equal(h.get('inputData().p.staff[0].avoidIsolatedWork'),true);assert(!Object.hasOwn(h.get('inputData().p.staff[1]'),'avoidIsolatedWork'));
 const re=harness(null,{current:JSON.parse(h.values.get('koukyu_v4_data'))});re.eval('editStaff(data.staff[0])');assert.equal(checkbox(re).checked,true);
 re.eval('editStaff(data.staff[1])');checkbox(re).checked=true;submit(re);assert.equal(re.get('inputData().p.staff[1].avoidIsolatedWork'),true);
 for(const bad of [null,'yes',1])assert.throws(()=>h.ctx.checkBackup({...raw,staff:[{...raw.staff[0],avoidIsolatedWork:bad}]}));
 // 設定を変えても当時の条件・希望・前期・勤務は残す。保存表と書き出しにも設定を含める。
 h.eval("schedule().assignments={a:{'6':'off','7':'early','8':'off'},b:{'1':'part'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render();data.savedTables.push(RosterStorage.capture(data,key(),'保存表','saved'));editStaff(data.staff[0])");const before=h.get('schedule().assignments'),history=h.get('schedule().history');checkbox(h).checked=false;submit(h);
 assert(h.get('workChanged()'));assert.deepEqual(h.get('schedule().assignments'),before);assert.deepEqual(h.get('schedule().history'),history);assert.equal(h.get('schedule().workSnapshot.staff[0].avoidIsolatedWork'),true);assert.equal(h.get('data.savedTables[0].staff[0].avoidIsolatedWork'),true);
 // 3.71までの入力署名を持つ作業表も保持する。
 const old=harness(null,{current:raw});old.eval("schedule().assignments={a:{'1':'early'},b:{'1':'part'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");const work=JSON.parse(old.values.get('koukyu_v4_work')),w=work.schedules['2026-10'];delete w.workSnapshot;w.workSignature=w.workSignature.replace('rules-3.72:','rules-3.65:');w.meta.signature=w.workSignature;
 const recovered=harness(null,{current:JSON.parse(old.values.get('koukyu_v4_data')),stored:{koukyu_v4_work:JSON.stringify(work)}});assert(recovered.get('hasTable()'));assert(recovered.get('workChanged()'));assert.deepEqual(recovered.get('schedule().workSnapshot.schedule.assignments'),{a:{'1':'early'},b:{'1':'part'}});
 const enabled={...raw,staff:[{...raw.staff[0],avoidIsolatedWork:true},raw.staff[1]]},error={code:'isolated_work',staff:'s0',day:7,workDay:7};
 const made=harness(null,{current:enabled,response:async()=>({status:'FEASIBLE',seconds:3,assignments:{s0:{'6':'off','7':'early','8':'off'},s1:{'1':'part'}},ruleExceptions:[error],validationErrors:[error],exceptionCount:0,exceptionsProvenMinimum:true,isolatedWorkExceptions:1,isolatedWork:{count:1,minimum:1,proven:true,policy:'off-work-off-1'},search:{done:true},optimizationPolicy:'quality-first-18',boundaryComplete:true})});
 await made.ctx.generate();assert.equal(made.calls[0].input.staff[0].avoidIsolatedWork,true);assert(made.nodes.view.text.includes('勤務条件の例外：1件'));assert(made.nodes.view.text.includes('職員A 10月22日（木）：1日だけの出勤'));assert(made.nodes.view.text.includes('最少を確認済み'));assert(made.nodes.view.all('td').some(e=>(e.attributes['aria-label']||'').includes('職員A 10月22日（木）')&&(e.attributes['aria-label']||'').includes('（例外）')));
 const saved=made.get('data');made.ctx.openLandscapeTable();assert(made.nodes['dialog-body'].text.includes('勤務条件の例外：1件'));await made.click('閉じる');assert.deepEqual(made.get('data'),saved);
 // 手直しの例外は「数学的に避けられない」と断定しない。
 const edit=harness(null,{current:enabled,response:async()=>({status:'INVALID',validationErrors:[error],isolatedWork:{count:1,proven:false,policy:'off-work-off-1'},boundaryComplete:true})});edit.eval("schedule().assignments={a:{'6':'off','7':'early','8':'off'},b:{'1':'part'}};schedule().workSignature=inputData().signature;");await edit.ctx.validateCurrent();assert.equal(edit.get('schedule().meta.status'),'VALID');assert(edit.nodes.view.text.includes('避けられないかは未確認です'));assert(!edit.nodes.view.text.includes('最少を確認済み'));assert.equal(edit.get('schedule().meta.isolatedWorkExceptions'),1);
 assert(made.ctx.exceptionText({...error,day:1,workDay:0},made.get('inputData().map')).includes('10月15日（木）：1日だけの出勤（休→出勤→休、翌日は今期の初日）'));
 assert(made.ctx.progressText({},{search:{reason:'isolated_work_unconfirmed'}}).includes('まだ不可能とは判定していません'));
 const base={status:'FEASIBLE',assignments:{},allocation:{overtimeTotal:0}};
 assert(flow.compare({...base,isolatedWorkExceptions:0,staffingShortfallTotal:9},{...base,isolatedWorkExceptions:1,staffingShortfallTotal:0})<0);
 assert(flow.compare({...base,exceptionCount:0,isolatedWorkExceptions:2},{...base,exceptionCount:1,isolatedWorkExceptions:0})<0);
 console.log('PASS: 個人設定・パート・保存と旧表・単独出勤の例外/印・手直しの未確認表示・人数不足より優先');
})().catch(e=>{console.error(e);process.exitCode=1;});
