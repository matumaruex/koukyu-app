'use strict';
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const row=n=>Object.fromEntries(Array.from({length:31},(_,i)=>[String(i+1),i<n?'night':'off']));
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'a',name:'A',type:'full',nightShiftType:'all',monthlyDaysOff:9},
 {id:'b',name:'B',type:'full',nightShiftType:'all',monthlyDaysOff:9},
 {id:'c',name:'C',type:'full',nightShiftType:'none',monthlyDaysOff:9},
 {id:'d',name:'D',type:'part',nightShiftType:'none',monthlyDaysOff:9}],
 schedules:{'2026-10':{assignments:{},requests:{},history:{}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const h=harness(null,{current:raw});
h.eval('schedule().assignments='+JSON.stringify({a:row(5),b:row(6),c:row(0),d:row(0)})+';schedule().workSignature=inputData().signature;');
assert(h.eval('allocationSummary()').text.includes('夜勤：5〜6回 ／ 差1回'));
h.eval("schedule().assignments.a['1']='off'");
assert(h.eval('allocationSummary()').text.includes('夜勤：4〜6回 ／ 差2回'));
h.eval("schedule().excludedStaff=['b']");
assert(h.eval('allocationSummary()').text.includes('夜勤：4〜4回 ／ 差0回'));
assert.equal(h.get('inputData().signature').startsWith('rules-3.35:'),true);
assert.equal(h.get('OPTIMIZATION_POLICY'),'quality-first-8');
console.log('PASS: 夜勤の回数差を実際の表から集計し、編集と対象職員に追従');
