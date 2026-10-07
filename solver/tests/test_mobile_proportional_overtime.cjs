'use strict';
// 出勤できる日数が少ない人：上限と比率での比較を表示し、普通の人どうしの差とは分けて示す（3.26）。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const row=(ot)=>Object.fromEntries(Array.from({length:31},(_,i)=>[String(i+1),ot.includes(i+1)?'overtime':'off']));
const leave=Array.from({length:18},(_,i)=>i+1);
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'a',name:'職員A',type:'full',canOvertime:true,nightShiftType:'none',monthlyDaysOff:9},
 {id:'b',name:'職員B',type:'full',canOvertime:true,nightShiftType:'none',monthlyDaysOff:9},
 {id:'c',name:'職員C',type:'full',canOvertime:true,nightShiftType:'none',monthlyDaysOff:9}],
 schedules:{'2026-10':{assignments:{},requests:{c:leave},history:{}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const h=harness(null,{current:raw});
// 計算側と同じ式：31日の期間、最低9日、希望休18日 → 出勤できる日数13日、上限4回。
assert.deepEqual(h.get("overtimeProfile(data.staff[2])"),{available:13,normal:22,proportional:true,cap:4});
assert.deepEqual(h.get("overtimeProfile(data.staff[0])"),{available:22,normal:22,proportional:false,cap:6});
h.eval('schedule().assignments='+JSON.stringify({a:row([1,3,5,7,9]),b:row([1,3,5,7]),c:row([20,22])})+';schedule().workSignature=inputData().signature;');
let text=h.eval('allocationSummary()').text;
assert(text.includes('残業（A残できる人）：4〜5回 ／ 差1回（出勤できる日数が少ない人を除く）'));
assert(text.includes('職員Cさん：A残2回（出勤できる日数13日・上限4回。比率で比べています）'));
assert(text.includes('まだ確認できていません'));assert(!text.includes('これ以上均等にできない'));
// 同じ表についての証明だけを使う（職員ごとの回数を照合）。
h.eval("schedule().meta={status:'FEASIBLE',optimizationPolicy:OPTIMIZATION_POLICY,overtimeFairness:{total:11,spread:1,minimumSpreadProven:true,byStaff:{s0:5,s1:4,s2:2}}};");
assert(h.eval('allocationSummary()').text.includes('出勤できる日数の比率で比べて'));
h.eval("schedule().meta.overtimeFairness.byStaff={s0:4,s1:5,s2:2};");
assert(h.eval('allocationSummary()').text.includes('まだ確認できていません'));
// 希望入力で、出勤できる日数と上限を案内する。普通の人には出さない。
h.eval("state.tab='requests';state.reqStaff='c';render();");
assert(h.nodes.view.text.includes('今期の出勤できる日数は13日です。A残は月4回まで'));
h.eval("state.reqStaff='a';render();");assert(!h.nodes.view.text.includes('出勤できる日数は'));
// 上限を超えた手直しは、上限の回数を示す。
assert.equal(h.ctx.errorsText([{code:'overtime_limit',staff:'s2',actual:5,limit:4}],{s2:'c'}),'職員Cさん：A残が5回（今期の上限4回）');
// 希望休を減らすと普通の人に戻る。
h.eval("schedule().requests.c=[1,2,3];");
assert.equal(h.get("overtimeProfile(data.staff[2]).proportional"),false);
console.log('PASS: 出勤できる日数と上限の計算（計算側と同じ式）、普通の人どうしの差と比率の人の分け方、証明の照合、希望入力の案内、上限超えの表示');
