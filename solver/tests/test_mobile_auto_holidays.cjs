'use strict';
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={schemaVersion:4,savedTables:[],staff:[{id:'a',name:'職員A',type:'full',monthlyDaysOff:10,nightShiftType:'all',canOvertime:true},{id:'b',name:'職員B',type:'full',monthlyDaysOff:12,nightShiftType:'none'},{id:'p',name:'職員P',type:'part',monthlyDaysOff:11,startTime:'09:00',endTime:'17:00'}],schedules:{'2026-10':{requests:{a:[2]},assignments:{},history:{a:Array(7).fill('off')},locked:{a:{'4':'early'}}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[4,4,4],maxReducedSundays:3}}};
function rows(day='off'){return Object.fromEntries(['s0','s1','s2'].map(sid=>[sid,Object.fromEntries(Array.from({length:31},(_,i)=>[String(i+1),day]))]));}
function candidate(payload){return {status:'DRAFT',assignments:rows(),selectedQuota:Object.fromEntries(Object.entries(payload.holidayPolicy).map(([sid,q])=>[sid,q.target])),seconds:60,allocation:{overtimeTotal:21,overtimeSpread:1,overtimeBalance:1,overtimeProportional:false,nightSpread:1,surplusTotal:0,commonExtraDaysOff:0,minor:0},overtimeFairness:{minimumSpreadProven:true,spread:1},nightRestPreferences:{unmet:[]},staffingShortfallTotal:1,boundaryComplete:true,unmetConditions:[{code:'coverage',day:11,time:600,actual:3,required:4}],optimizationPolicy:'auto-holidays-2',search:{done:true}};}
(async()=>{
 const h=harness(null,{current:raw,response:async p=>p.action==='validate'?{status:'VALID',boundaryComplete:true}:p.autoPhase==='base'?candidate(p):{status:'UNKNOWN',autoDone:true,autoReason:'unchanged',seconds:1}});
 const normalSignature=h.get('inputData().signature'),normalOff=h.get('data.staff.map(st=>st.monthlyDaysOff)'),history=h.get('history()');
 h.eval("schedule().assignments={a:{'1':'early'}};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE'};render();");const normalTable=h.get('schedule().assignments');
 assert.deepEqual(h.ctx.document.querySelectorAll('[data-tab]').map(b=>b.dataset.tab),['schedule','requests','staff','saved']);
 h.ctx.settings();await h.click('公休おまかせを開く');assert.equal(h.nodes.dialog.open,false);
 assert(h.nodes.view.text.includes('公休おまかせ'));assert(h.get('inputData().signature').startsWith('auto-rules-3:'));
 assert.equal(h.calls.length,0);await h.click('通常の公休表に戻る','view');
 assert.equal(h.get('state.mode'),'normal');assert.equal(h.get('inputData().signature'),normalSignature);
 assert.deepEqual(h.get('schedule().assignments'),normalTable);
 h.ctx.settings();await h.click('公休おまかせを開く');
 const policy=h.get('inputData().holidayPolicy');assert.equal(policy.s0.target,10);assert.equal(policy.s1.fixed,true);assert.equal(policy.s1.target,12);assert.equal(policy.s2.target,11);
 await h.ctx.generate();assert.equal(h.calls[0].mode,'auto');assert.equal(h.calls[0].autoPhase,'base');assert.deepEqual(h.calls[0].input.history.s0,history.a);assert.deepEqual(h.calls[0].input.locked.s0,{'4':'early'});
 assert.equal(h.get('hasTable()'),true);assert.deepEqual(h.get('data.staff.map(st=>st.monthlyDaysOff)'),normalOff);assert.deepEqual(h.get('history()'),history);
 const auto=h.get('schedule().assignments');assert.deepEqual(h.get('data.schedules["2026-10"].assignments'),normalTable);
 assert(h.values.has('koukyu_v4_auto_work'));assert(h.values.has('koukyu_v4_work'));
 h.eval("setTab('schedule')");assert.deepEqual(h.get('schedule().assignments'),normalTable);assert.equal(h.get('inputData().signature'),normalSignature);
 h.eval("setTab('auto');saveTableDialog()");await h.click('保存する');const saved=h.get('data.savedTables.at(-1)');assert.equal(saved.creationMode,'auto');assert.deepEqual(saved.schedule.assignments,auto);assert(saved.normalMinimums);assert(saved.autoHolidayPolicy);
 const backup=h.get('RosterStorage.persisted(data)');assert(!backup.autoSchedules);assert.deepEqual(backup.schedules['2026-10'].assignments,{});assert.equal(backup.savedTables.at(-1).creationMode,'auto');assert.deepEqual(backup.autoHolidayPolicy,h.get('data.autoHolidayPolicy'));
 const reload=harness(null,{current:backup,stored:{koukyu_v4_auto_work:h.values.get('koukyu_v4_auto_work'),koukyu_v4_work:h.values.get('koukyu_v4_work')}});assert.equal(reload.get('state.loadError'),false);reload.eval("setTab('auto')");assert.deepEqual(reload.get('schedule().assignments'),auto);reload.eval("setTab('schedule')");assert.deepEqual(reload.get('schedule().assignments'),normalTable);
 // 通常日数だけ変えた場合、おまかせの目標・表は独立して残る。
 h.eval("setTab('schedule');data.staff[0].monthlyDaysOff=9;render();setTab('auto')");assert.deepEqual(h.get('schedule().assignments'),auto);assert.equal(h.get('inputData().holidayPolicy.s0.target'),10);
 // おまかせ日数だけ変えた場合、通常の表・署名は維持する。
 h.eval("setTab('schedule');schedule().assignments={a:{'1':'early'}};schedule().workSignature=inputData().signature;render()");const ordinary=h.get('inputData().signature');h.eval("data.autoHolidayPolicy.staff.a.target=9;setTab('auto')");assert.equal(h.get('hasTable()'),true);assert(h.get('workChanged()'));h.eval("setTab('schedule')");assert.equal(h.get('inputData().signature'),ordinary);assert.equal(h.get('hasTable()'),true);
 // 共通希望の変更は両方式を古い条件にし、明示保存と前期は残す。
 h.eval("setTab('auto');schedule().assignments={a:{'1':'off'}};schedule().workSignature=inputData().signature;setTab('requests');toggleRequest('a',5,'off');setTab('schedule')");assert.equal(h.get('hasTable()'),true);assert(h.get('workChanged()'));h.eval("setTab('auto')");assert.equal(h.get('hasTable()'),true);assert(h.get('workChanged()'));assert.deepEqual(h.get('history()'),history);assert.deepEqual(h.get('data.savedTables.at(-1)'),saved);
 // 採用日数を編集・検査・保存・コピーにも引き継ぎ、通常の日数を勝手に変えない。
 const editing=harness(null,{current:raw,response:async p=>({status:'VALID',boundaryComplete:true})});editing.eval("setTab('auto');schedule().selectedQuota={a:9,b:12,p:10};schedule().assignments={a:{'1':'off'},b:{'1':'off'},p:{'1':'off'}};schedule().workSignature=inputData().signature");await editing.ctx.validateCurrent();assert.deepEqual(editing.calls[0].input.staff.map(st=>st.monthlyDaysOff),[9,12,10]);editing.eval('saveTableDialog()');await editing.click('保存する');const snapshot=editing.get('data.savedTables.at(-1)');assert.deepEqual(snapshot.staff.map(st=>st.monthlyDaysOff),[9,12,10]);editing.eval('copySavedTableDialog(data.savedTables.at(-1))');await editing.click('編集用のコピーを作る');assert.equal(editing.get('state.tab'),'auto');assert.deepEqual(editing.get('data.staff.map(st=>st.monthlyDaysOff)'),[10,12,11]);assert.deepEqual(editing.calls.at(-1).input.staff.map(st=>st.monthlyDaysOff),[9,12,10]);assert.deepEqual(editing.get('data.savedTables.at(-1)'),snapshot);
 // おまかせでも、採用日数から比率を計算し、同じ勤務の公平性の証明だけを表示する。
 editing.eval("schedule().requests.a=Array.from({length:18},(_,i)=>i+1);schedule().assignments.a={'20':'overtime'};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE',optimizationPolicy:AutoHolidayPolicy.POLICY,overtimeFairness:{total:1,minimumSpreadProven:true,byStaff:{s0:1}}}");assert(editing.eval('allocationSummary()').text.includes('出勤できる日数の比率で比べて'));assert.deepEqual(editing.get('overtimeProfile(data.staff[0])'),{available:13,normal:22,proportional:true,cap:4});editing.eval("schedule().meta.overtimeFairness.byStaff.s0=2");assert(editing.eval('allocationSummary()').text.includes('まだ確認できていません'));
 // 入力変更前の古い応答を採用しない。
 let resolve;const pending=harness(null,{current:raw,response:async p=>new Promise(r=>resolve=()=>r(candidate(p)))});pending.eval("setTab('auto')");const task=pending.ctx.generate();pending.eval("data.schedules['2026-10'].requests.a.push(8)");resolve();await task;assert.equal(pending.get('hasTable()'),false);assert.deepEqual(pending.get('history()'),history);
 // 保存容量不足のときは計算を始めず、両方式の表と明示保存を残す。
 const quota=harness(null,{current:raw,quota:true});quota.eval("setTab('auto');schedule().assignments={a:{'1':'off'}};schedule().workSignature=inputData().signature");await quota.ctx.generate();assert.equal(quota.calls.length,0);assert.equal(quota.get('hasTable()'),true);
 console.log('PASS: おまかせと通常の独立入力・結果・再読込、共有希望・固定・前期、採用日数での検査・保存・コピー・バックアップ、古い応答と保存失敗の保護');
})().catch(e=>{console.error(e);process.exit(1);});
