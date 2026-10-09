'use strict';
// 新しい達成範囲の案内と、保存した旧表の評価・証明を混同しないことを確認する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={staff:[{id:'a',name:'職員A',type:'full',nightShiftType:'all',monthlyDaysOff:9}],
 schedules:{'2026-10':{requests:{a:[6]},assignments:{},history:{a:Array(7).fill('off')}}},
 preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const h=harness(raw);
h.eval("schedule().assignments={a:{'3':'night','4':'nightOff','5':'off','6':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE',nightRestPreferences:{rule:'night-request-gap-1',requestedCount:1,metCount:1,unmet:[]}};render()");
assert(h.nodes.view.text.includes('どちらも同じ達成'));
assert(h.eval('monthTable(false)').text.includes('夜勤→明け→公休→希望休'));
assert(!h.eval('nightPreferencePanel()').text.includes('できなかった'));
h.eval("schedule().meta.nightRestPreferences={requestedCount:1,metCount:0,unmet:[{staff:'s0',day:6}],minimumUnmetProven:true};state.archiveView=true;");
assert(h.eval('nightPreferenceExplanation()').includes('保存時は'));
assert(!h.eval('nightPreferencePanel()').text.includes('この件数が最少'));
h.eval("state.archiveView=false;schedule().meta.nightRestPreferences.rule='night-request-gap-1'");
assert(h.eval('nightPreferencePanel()').text.includes('この件数が最少'));
console.log('PASS: 直結と公休1日を同列に案内・印刷、旧保存表の評価と新ルールの最少証明を区別');
