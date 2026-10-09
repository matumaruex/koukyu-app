'use strict';
// 実画面の職員設定・送信範囲・結果表示・保存と復元を確認する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const preference=require('../../public/overtime-preference.js'),flow=require('../../public/creation-workflow.js');
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'a',name:'職員A',type:'full',canOvertime:true,nightShiftType:'none',monthlyDaysOff:9,minConsecutiveRest:1},
 {id:'b',name:'職員B',type:'full',canOvertime:true,nightShiftType:'none',monthlyDaysOff:9},
 {id:'c',name:'職員C',type:'full',canOvertime:true,nightShiftType:'none',monthlyDaysOff:9},
 {id:'p',name:'職員P',type:'part',monthlyDaysOff:11,startTime:'09:00',endTime:'17:00'}],
 schedules:{'2026-10':{assignments:{},requests:{},history:{a:Array(7).fill('off')}}},
 preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const row=n=>Object.fromEntries(Array.from({length:31},(_,i)=>[String(i+1),i<n*2&&i%2===0?'overtime':'off']));
(async()=>{
 for(const v of [null,true,'2',-1,3,1.5])assert.throws(()=>preference.check(v));
 assert.equal(preference.check(undefined),0);
 const h=harness(null,{current:raw,response:async()=>({status:'VALID',boundaryComplete:true})});
 const originalSignature=h.get('inputData().signature'),history=h.get('history()');
 assert(originalSignature.startsWith('rules-3.31:'));
 assert(!Object.hasOwn(h.get('inputData().p.staff[0]'),'overtimePreference'));
 h.eval("setTab('auto')");const autoSignature=h.get('inputData().signature');
 h.eval("setTab('staff');editStaff(data.staff[0])");
 const selector=h.nodes['dialog-body'].all('select').find(s=>s.children.some(o=>o.text==='多め（＋2回目安）'));
 assert(selector);assert.equal(selector.value,'0');assert(!selector.disabled);selector.value='2';
 h.nodes['dialog-body'].all('form')[0].onsubmit({preventDefault(){}});
 assert.equal(h.get('data.staff[0].overtimePreference'),2);
 h.eval("setTab('schedule')");assert(h.get('inputData().signature').startsWith('rules-3.31:'));
 assert.equal(h.get('inputData().p.staff[0].overtimePreference'),2);
 h.eval("setTab('auto')");assert.equal(h.get('inputData().signature'),autoSignature);
 assert(h.get('inputData().sourceInput.staff').every(st=>!Object.hasOwn(st,'overtimePreference')));
 // 配分設定だけを変えても既存のおまかせの表を消さない。
 h.ctx.testRows={a:row(5),b:row(3),c:row(3),p:row(0)};
 h.eval("schedule().assignments=clone(testRows);schedule().workSignature=inputData().signature;data.staff[0].overtimePreference=1;render()");
 assert(h.get('hasTable()'));assert(!h.eval('overtimeFairnessSummary()').text.includes('歓迎の目安'));
 h.eval("data.staff[0].overtimePreference=2;setTab('schedule');schedule().assignments=clone(testRows);schedule().workSignature=inputData().signature;render()");
 let text=h.eval('allocationSummary()').text;
 assert(text.includes('職員Aさん：5回 ／ 多め（＋2回目安）'));
 assert(text.includes('職員Bさん：3回 ／ 通常'));assert(text.includes('まだ確認できていません'));
 assert(!text.includes('これ以上均等にできない'));
 h.eval("schedule().meta={status:'FEASIBLE',optimizationPolicy:OvertimePreference.POLICY,overtimeFairness:{total:11,byStaff:{s0:5,s1:3,s2:3},preferenceByStaff:{s0:2,s1:0,s2:0},preferenceApplied:true,minimumSpreadProven:true}};");
 assert(h.eval('allocationSummary()').text.includes('歓迎の目安からの配分差が最少'));
 // 回数や歓迎設定が一致しない証明は表示しない。
 h.eval("schedule().meta.overtimeFairness.preferenceByStaff.s0=1;");
 assert(h.eval('allocationSummary()').text.includes('まだ確認できていません'));
 h.eval("schedule().meta.overtimeFairness.preferenceByStaff.s0=2;schedule().assignments.a['1']='off';");
 assert(h.eval('allocationSummary()').text.includes('まだ確認できていません'));
 h.eval("schedule().assignments=clone(testRows);schedule().meta=null;saveTableDialog()");await h.click('保存する');
 const saved=h.get('data.savedTables.at(-1)'),persisted=h.get('RosterStorage.persisted(data)');
 assert.equal(saved.staff[0].overtimePreference,2);
 const reload=harness(null,{current:persisted});assert.equal(reload.get('state.loadError'),false);
 assert.equal(reload.get('data.staff[0].overtimePreference'),2);
 assert.equal(reload.get('data.savedTables[0].staff[0].overtimePreference'),2);
 h.eval("data.staff[0].overtimePreference=0;render()");assert(h.get('hasTable()'));assert(h.get('workChanged()'));
 assert.equal(h.get('inputData().signature'),originalSignature);assert.deepEqual(h.get('history()'),history);
 h.eval("setTab('saved');state.archiveId=data.savedTables[0].id;render()");
 assert(h.nodes.view.text.includes('職員Aさん：5回 ／ 多め'));
 h.eval('copySavedTableDialog(data.savedTables[0])');await h.click('編集用のコピーを作る');
 assert.equal(h.get('data.staff[0].overtimePreference'),2);
 assert.equal(h.calls.at(-1).input.staff[0].overtimePreference,2);
 assert.deepEqual(h.get('data.savedTables[0]'),saved);assert.deepEqual(h.get('history()'),history);
 // 不正値は保存表のスナップショットでも拒否。パートとA残不可には適用しない。
 const bad=JSON.parse(JSON.stringify(persisted));bad.savedTables[0].staff[0].overtimePreference='2';
 assert.throws(()=>h.ctx.checkBackup(bad));
 h.eval("data.staff[0].canOvertime=false;data.staff[3].overtimePreference=2;");
 assert(h.get('inputData().p.staff').every(st=>!Object.hasOwn(st,'overtimePreference')));
 h.eval("editStaff(data.staff[0])");assert(h.nodes['dialog-body'].all('select').find(s=>s.children.some(o=>o.text==='多め（＋2回目安）')).disabled);
 const quality=(total,balance,rawSpread)=>({status:'FEASIBLE',allocation:{overtimeTotal:total,overtimeBalance:balance,overtimeSpread:rawSpread}});
 assert(flow.compare(quality(22,0,2),quality(22,1,1))<0);
 assert(flow.compare(quality(23,0,2),quality(22,4,4))>0);
 const progress=h.eval("progressText({allocation:{overtimeTotal:22,overtimeSpread:1}},{allocation:{overtimeTotal:22,overtimeSpread:2,overtimePreferred:true},search:{resume:{stage:'overtime_fairness'}}})");
 assert(progress.includes('残業歓迎の目安に合わせた配分'));assert(!progress.includes('残業の差'));
 console.log('PASS: 残業配分の設定・通常だけの送信・おまかせと旧表の維持・目安と証明・編集後の再集計・保存とコピー・前期保持・比率と合計優先');
})().catch(e=>{console.error(e);process.exit(1);});
