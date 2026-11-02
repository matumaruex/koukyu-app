'use strict';
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'a',name:'職員A',type:'full',monthlyDaysOff:9,nightShiftType:'all',excludeNightFromConsecutive:false},
 {id:'b',name:'職員B',type:'full',monthlyDaysOff:9,nightShiftType:'all',excludeNightFromConsecutive:true},
 {id:'c',name:'職員C',type:'part',monthlyDaysOff:11,nightShiftType:'none',startTime:'09:00',endTime:'17:00'}],
 schedules:{'2026-10':{requests:{a:[7]},assignments:{},history:{a:Array(7).fill('off')}}}};
(async()=>{
 const h=harness(null,{current:raw});
 assert.equal(h.get('inputData().p.excludeNightFromConsecutive'),true);
 assert(h.get('inputData().signature').startsWith('rules-3.65:'));
 const before=h.get('inputData().signature');
 for(const index of [0,1,2]){
  h.eval(`editStaff(data.staff[${index}])`);
  const body=h.nodes['dialog-body'];
  assert(!body.all('label').some(l=>l.text.includes('夜勤は連続出勤日数に含めない')));
  assert(body.text.includes('夜勤は数えない'));
  body.all('form')[0].onsubmit({preventDefault(){}});
 }
 // 旧個人設定は書き換えず、いずれの値でも共通ルールを送る。
 assert.equal(h.get('data.staff[0].excludeNightFromConsecutive'),false);
 assert.equal(h.get('data.staff[1].excludeNightFromConsecutive'),true);
 assert.equal(h.get('inputData().signature'),before);
 h.eval("schedule().assignments={a:{'1':'early','7':'off'},b:{'1':'night'},c:{'1':'part'}};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE',signature:inputData().signature,optimizationPolicy:OPTIMIZATION_POLICY};render()");
 const values=Object.fromEntries(h.values);
 // 実際の旧署名には共通指定がない。スナップショットの有無にかかわらず、旧表を保持する。
 for(const prefix of ['rules-3.59:','rules-3.56:'])for(const keepSnapshot of [true,false]){
  const work=JSON.parse(values.koukyu_v4_work),w=work.schedules['2026-10'];
  w.workSignature=w.workSignature.replace(/,"partWeeklyLimit":false}(?=\|staff:|$)/,'}').replace(/,"excludeNightFromConsecutive":true}(?=\|staff:|$)/,'}').replace('rules-3.65:',prefix);
  if(prefix==='rules-3.56:')w.workSignature=w.workSignature.replace(',"nightDistribution":true','').replace(',"overtimeDistribution":true','');
  w.meta={...w.meta,signature:w.workSignature,optimizationPolicy:'quality-first-15',allocation:{minimumOvertimeProven:true}};
  if(keepSnapshot)w.workSnapshot.schedule.meta=w.meta;else delete w.workSnapshot;
  const re=harness(null,{current:JSON.parse(values.koukyu_v4_data),stored:{koukyu_v4_work:JSON.stringify(work)}});
  assert(re.get('hasTable()'));assert(re.get('workChanged()'));assert.equal(re.get('metadata()'),null);
  assert.deepEqual(re.get('schedule().assignments'),w.assignments);
  assert.equal(re.get('schedule().workSnapshot.staff[0].excludeNightFromConsecutive'),false);
  assert.equal(re.get('schedule().workSnapshot.staff[1].excludeNightFromConsecutive'),true);
  assert.deepEqual(re.get('schedule().workSnapshot.schedule.requests.a'),[7]);
  assert.deepEqual(re.get('schedule().workSnapshot.schedule.history.a'),Array(7).fill('off'));
  assert.equal(re.calls.length,0);
  re.eval('saveTableDialog()');await re.click('保存する');
  const saved=re.get('data.savedTables.at(-1)');
  assert.deepEqual(saved.schedule.assignments,w.assignments);
  assert.equal(saved.staff[0].excludeNightFromConsecutive,false);
  assert.equal(saved.schedule.meta.signature,w.workSignature);
 }
 let sent;
 const remote=harness(null,{current:raw,backgroundActual:true,response:async p=>{
  if(p.action==='start'){sent=p;return {runId:'wrun_CONSECUTIVE'};}
  return {status:'completed',result:{best:{status:'FEASIBLE',assignments:{s0:{'1':'off'},s1:{'1':'off'},s2:{'1':'off'}},seconds:1},seconds:1,rounds:[],done:true}};
 }});
 await remote.ctx.generate('new');
 assert.equal(sent.input.excludeNightFromConsecutive,true);
 assert.equal(sent.input.nightDistribution,true);assert.equal(sent.input.overtimeDistribution,true);
 assert.equal(sent.initialAssignments,undefined);assert.equal(sent.resume,undefined);
 assert(remote.get('hasTable()'));
 for(const v of [1,null,'true'])assert.throws(()=>h.ctx.checkBackup({...raw,staff:[{...raw.staff[0],excludeNightFromConsecutive:v}]}));
 console.log('PASS: 夜勤の連勤除外を共通化し、個人チェックを撤去・旧表と希望と前期を保持・背景計算に適用');
})().catch(e=>{console.error(e);process.exitCode=1;});
