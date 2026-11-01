'use strict';
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'a',name:'職員A',type:'full',nightShiftType:'all',canOvertime:true,monthlyDaysOff:9,overtimePreference:1},
 {id:'b',name:'職員B',type:'full',nightShiftType:'none',canOvertime:true,monthlyDaysOff:9}],
 schedules:{'2026-10':{assignments:{},requests:{a:[7]},history:{a:Array(7).fill('off')}}},
 preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[4,4,4],maxReducedSundays:0}}};
(async()=>{
 const h=harness(null,{current:raw});
 assert.equal(h.get('inputData().p.overtimeDistribution'),true);
 assert.equal(h.get('inputData().p.nightDistribution'),true);
 assert.equal(h.get('inputData().p.staff[0].overtimePreference'),1);
 assert.equal(h.get('OPTIMIZATION_POLICY'),'quality-first-15');
 assert.equal(h.get('OvertimePreference.POLICY'),h.get('OPTIMIZATION_POLICY'));
 h.eval("schedule().assignments={a:{'1':'overtime','2':'off','7':'off'},b:{'1':'early'}};schedule().workSignature=inputData().signature;render()");
 const values=Object.fromEntries(h.values),work=JSON.parse(values.koukyu_v4_work),table=work.schedules['2026-10'];
 delete table.workSnapshot;
 table.workSignature=table.workSignature.replace('rules-3.59:','rules-3.58:').replace(',"overtimeDistribution":true','');
 table.meta={status:'OPTIMAL',optimizationPolicy:'quality-first-14',signature:table.workSignature,allocation:{minimumOvertimeProven:true}};
 const reopened=harness(null,{current:JSON.parse(values.koukyu_v4_data),stored:{...values,koukyu_v4_work:JSON.stringify(work)}});
 assert(reopened.get('hasTable()'));assert(reopened.get('workChanged()'));assert.equal(reopened.get('metadata()'),null);
 assert.deepEqual(reopened.get('schedule().assignments'),table.assignments);
 assert.deepEqual(reopened.get('schedule().workSnapshot.schedule.requests.a'),[7]);
 assert.deepEqual(reopened.get('schedule().workSnapshot.schedule.history.a'),Array(7).fill('off'));
 assert.equal(reopened.get('schedule().workSnapshot.staff[0].overtimePreference'),1);
 let sent;
 const remote=harness(null,{current:raw,backgroundActual:true,response:async p=>{
  if(p.action==='start'){sent=p.input;return {runId:'wrun_OT'};}
  return {status:'completed',result:{best:{status:'FEASIBLE',assignments:{s0:{'1':'off'},s1:{'1':'off'}},seconds:1,allocation:{overtimeTotal:0}},seconds:1,rounds:[],done:true}};
 }});
 await remote.ctx.generate('new');
 assert.equal(sent.overtimeDistribution,true);assert.equal(sent.nightDistribution,true);assert(remote.get('hasTable()'));
 console.log('PASS: 残業と夜勤の分散を自動適用し、歓迎配分・旧表・希望・前期を保持');
})().catch(e=>{console.error(e);process.exit(1);});
