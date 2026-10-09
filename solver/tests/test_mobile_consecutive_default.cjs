'use strict';
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const staff=[{id:'n',name:'夜勤職員',type:'full',nightShiftType:'all',maxConsecutive:0,monthlyDaysOff:9},{id:'d',name:'日勤職員',type:'full',nightShiftType:'none',maxConsecutive:0,monthlyDaysOff:9},{id:'p',name:'パート職員',type:'part',nightShiftType:'none',monthlyDaysOff:11,startTime:'09:00',endTime:'17:00'}];
const current={schemaVersion:4,savedTables:[],staff,schedules:{'2026-10':{assignments:{},requests:{n:[2]},history:{n:Array(7).fill('off')}}},preferences:{staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
(async()=>{
 const h=harness(null,{current});
 h.eval("editStaff(data.staff[0])");const body=h.nodes['dialog-body'];
 assert(!body.text.includes('2日以上続く公休を1回'));
 assert(!body.text.includes('残業合計を増やさず'));
 assert(!body.text.includes('自動：夜勤あり'));
 assert(body.text.includes('連勤上限未指定は3日'));
 const form=body.all('form')[0],cons=form.all('label').find(e=>e.text.startsWith('連勤上限')).all('input')[0];
 assert.equal(cons.value,'');assert.equal(cons.attributes.required,undefined);
 form.onsubmit({preventDefault(){}});assert.equal(h.get('data.staff[0].maxConsecutive'),0);
 h.eval("editStaff(data.staff[0])");const f=body.all('form')[0],c=f.all('label').find(e=>e.text.startsWith('連勤上限')).all('input')[0];c.value='4';f.onsubmit({preventDefault(){}});assert.equal(h.get('inputData().p.staff.find(s=>s.nightShiftType===\"all\").maxConsecutive'),4);
 // 旧版の未指定は2/5日で確定し、新しく作成した表は3日で残す。
 for(const mode of ['normal','auto']){
  const old=harness(null,{current});old.eval(mode==='auto'?"setTab('auto')":"setTab('schedule')");
  old.eval("schedule().assignments={n:{'1':'early'},d:{'1':'off'},p:{'1':'part'}};schedule().workSignature=inputData().signature;"+(mode==='auto'?"schedule().selectedQuota={n:10,d:10,p:11};":"")+"render()");
  const key=mode==='normal'?'koukyu_v4_work':'koukyu_v4_auto_work';
  const actualKey=mode==='normal'?key:old.get('AutoHolidayPolicy.WORK_STORAGE');
  const work=JSON.parse(old.values.get(actualKey));assert.deepEqual(work.schedules['2026-10'].workSnapshot.staff.map(s=>s.maxConsecutive),[3,3,3]);
  const oldWork=JSON.parse(JSON.stringify(work)),w=oldWork.schedules['2026-10'];
  w.workSignature=w.workSignature.replace('rules-3.35:','rules-3.31:').replace('auto-rules-4:','auto-rules-3:');w.workSnapshot.staff.forEach(s=>s.maxConsecutive=0);
  const reopened=harness(null,{current,stored:{[actualKey]:JSON.stringify(oldWork)}});reopened.eval(mode==='auto'?"setTab('auto')":"setTab('schedule')");
  assert(reopened.get('hasTable()'));assert(reopened.get('workChanged()'));assert.deepEqual(reopened.get('schedule().workSnapshot.staff.map(s=>s.maxConsecutive)'),[2,5,5]);
  assert.deepEqual(reopened.get('schedule().assignments'),w.assignments);assert.equal(reopened.calls.length,0);
  reopened.eval('saveTableDialog()');await reopened.click('保存する');assert.deepEqual(reopened.get('data.savedTables.at(-1).staff.map(s=>s.maxConsecutive)'),[2,5,5]);
  // version=1の同一入力も、当時の条件を記録して保持する。
  oldWork.version=1;delete w.workSnapshot;
  const v1=harness(null,{current,stored:{[actualKey]:JSON.stringify(oldWork)}});v1.eval(mode==='auto'?"setTab('auto')":"setTab('schedule')");
  assert(v1.get('hasTable()'));assert.deepEqual(v1.get('schedule().workSnapshot.staff.map(s=>s.maxConsecutive)'),[2,5,5]);
 }
 console.log('PASS: 未指定と明示上限、編集画面の短文、旧通常・おまかせ表と当時の2/5日、新表3日、再読込と名前付き保存、旧version=1の保持');
})().catch(e=>{console.error(e);process.exitCode=1});
