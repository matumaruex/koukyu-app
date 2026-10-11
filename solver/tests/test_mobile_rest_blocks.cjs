'use strict';
// 職員設定→両方式の送信→保存→コピー→手直しの判定を実際の画面コードで検査する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const rest=require('../../public/consecutive-rest.js');
const raw={schemaVersion:4,savedTables:[],staff:[{id:'a',name:'職員A',type:'full',monthlyDaysOff:9,nightShiftType:'all',canOvertime:true},{id:'p',name:'職員P',type:'part',monthlyDaysOff:11,startTime:'09:00',endTime:'17:00'}],schedules:{'2026-10':{requests:{a:[1,2,3,4]},assignments:{},history:{a:Array(7).fill('off'),p:Array(7).fill('off')}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const rows={a:{'1':'off','2':'off','3':'off','4':'off','5':'early','6':'nightOff','7':'off','8':'off'},p:{'1':'off','2':'off'}};
const required={...raw,staff:raw.staff.map(st=>({...st,minConsecutiveRest:st.id==='a'?2:1}))};
const diagnostic={status:'EXPLAINED',proven:true,missingNights:[],droppedWishes:[],restShortfalls:[{staff:'s0',required:2,actual:1,missing:1}]};
(async()=>{
 assert.deepEqual(rest.ranges({'0':'off','1':'off','3':'off','4':'off','5':'off','6':'nightOff','7':'off','31':'off','32':'off'},31),[{start:3,end:5}]);
 assert.deepEqual(rest.ranges({'1':'off','2':'off','3':'early','4':'off','5':'off'},31),[{start:1,end:2},{start:4,end:5}]);
 for(const value of [null,true,'1',3,-1,1.5])assert.throws(()=>rest.check(value));
 const h=harness(null,{current:raw,response:async()=>({status:'VALID',boundaryComplete:true})});
 assert(h.get('inputData().signature').startsWith('rules-3.45:'));
 assert(!Object.hasOwn(h.get('inputData().p.staff[0]'),'minConsecutiveRest'));
 h.eval("setTab('auto')");assert(h.get('inputData().signature').startsWith('auto-rules-6:'));
 h.eval("setTab('staff');editStaff(data.staff[0])");
 const select=h.nodes['dialog-body'].all('select').find(s=>s.children.some(o=>o.text==='月2回以上'));
 assert(select);assert.equal(select.value,'0');select.value='2';
 h.nodes['dialog-body'].all('form')[0].onsubmit({preventDefault(){}});
 assert.equal(h.get('data.staff[0].minConsecutiveRest'),2);
 h.eval("setTab('schedule')");assert(h.get('inputData().signature').startsWith('rules-3.45:'));
 assert.equal(h.get('inputData().p.staff[0].minConsecutiveRest'),2);
 h.eval("setTab('auto')");assert(h.get('inputData().signature').startsWith('auto-rules-6:'));
 assert.equal(h.get('inputData().sourceInput.staff[0].minConsecutiveRest'),2);
 assert.equal(h.get('inputData().p.staff[0].minConsecutiveRest'),2);
 const v=harness(null,{current:required,response:async()=>({status:'VALID',boundaryComplete:true})});
 v.ctx.testRows=rows;v.eval("schedule().assignments=clone(testRows);schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
 assert(v.nodes.view.text.includes('職員A：連休2回／必要2回（10/16〜10/19、10/22〜10/23）'));
 assert(v.nodes.view.text.includes('職員P：連休1回／必要1回'));
 v.eval('saveTableDialog()');await v.click('保存する');const saved=v.get('data.savedTables.at(-1)');
 assert.equal(saved.staff[0].minConsecutiveRest,2);
 const backup=v.get('RosterStorage.persisted(data)');
 const reload=harness(null,{current:backup});assert.equal(reload.get('state.loadError'),false);
 assert.equal(reload.get('data.staff[0].minConsecutiveRest'),2);
 assert.equal(reload.get('data.savedTables.at(-1).staff[0].minConsecutiveRest'),2);
 v.eval("setTab('auto');schedule().assignments=clone(testRows);schedule().selectedQuota={a:9,p:11};schedule().workSignature=inputData().signature;saveTableDialog()");await v.click('保存する');
 const autoSaved=v.get('data.savedTables.at(-1)');assert.equal(autoSaved.staff[0].minConsecutiveRest,2);
 // 共有設定を変えると両方式が古い条件になる。保存表と手入力の前期は残る。
 const history=v.get('history()');v.eval("data.staff[0].minConsecutiveRest=1;setTab('schedule')");assert.equal(v.get('hasTable()'),true);assert(v.get('workChanged()'));
 v.eval("setTab('auto')");assert.equal(v.get('hasTable()'),true);assert(v.get('workChanged()'));
 assert.deepEqual(v.get('data.savedTables[0]'),saved);assert.deepEqual(v.get('history()'),history);
 v.eval("setTab('saved');state.archiveId=data.savedTables[0].id;render()");assert(v.nodes.view.text.includes('連休2回／必要2回'));
 v.eval('copySavedTableDialog(data.savedTables[0])');await v.click('編集用のコピーを作る');
 assert.equal(v.get('data.staff[0].minConsecutiveRest'),2);assert.equal(v.calls.at(-1).input.staff[0].minConsecutiveRest,2);
 assert.deepEqual(v.get('data.savedTables[0]'),saved);assert.deepEqual(v.get('history()'),history);
 v.eval('copySavedTableDialog(data.savedTables.at(-1))');await v.click('編集用のコピーを作る');
 assert.equal(v.get('state.mode'),'auto');assert.equal(v.get('data.staff[0].minConsecutiveRest'),2);
 assert.deepEqual(v.get('data.savedTables.at(-1)'),autoSaved);
 // 手直し後は古い集計を使わず、最新の勤務から不足を表示。必須違反をDRAFTにしない。
 const edit=harness(null,{current:required,response:async()=>({status:'INVALID',boundaryComplete:true,validationErrors:[{code:'rest_blocks',staff:'s0',actual:1,required:2}],consecutiveRest:{s0:{actual:1,required:2,ranges:[{start:1,end:4}]}}})});
 edit.ctx.testRows=rows;edit.eval("schedule().assignments=clone(testRows);schedule().assignments.a['8']='early';schedule().workSignature=inputData().signature");
 await edit.ctx.validateCurrent();assert.equal(edit.get('schedule().meta.status'),'INVALID');assert.equal(edit.get('ready()'),false);
 assert.equal(edit.get('schedule().meta.consecutiveRest.s0.actual'),1);
 assert(edit.nodes.view.text.includes('職員A：連休1回／必要2回'));assert(edit.nodes.view.text.includes('1回不足'));
 assert(edit.eval("errorsText([{code:'rest_blocks',staff:'s0',actual:1,required:2}],inputData().map)").includes('職員Aさん：連休1回／必要2回'));
 for(const mode of ['normal','auto']){
  const fail=harness(null,{current:required,response:async p=>({status:'INFEASIBLE',seconds:.1,autoDone:true,...(p.autoPhase==='adjust'?{}:{diagnosis:diagnostic})})});
  if(mode==='auto')fail.eval("setTab('auto')");await fail.ctx.generate();
  assert.equal(fail.get('hasTable()'),false);assert(fail.nodes.view.text.includes('この条件では表を作れません'));
  assert(fail.nodes.view.text.includes('職員Aさん：連休2回必要'));assert(!fail.nodes.view.text.includes('次の0件を外すと作れます'));
 }
 // 保存時の職員の不正な設定も、入力と同様に読み込みを止める。
 const bad=JSON.parse(JSON.stringify(backup));bad.savedTables[0].staff[0].minConsecutiveRest='2';
 assert.throws(()=>h.ctx.checkBackup(bad));
 console.log('PASS: 連休設定・両方式の必須送信・ゼロ指定の互換性・実際の集計・日付・保存とコピー・前期保持・手直しの必須違反・不成立理由');
})().catch(e=>{console.error(e);process.exit(1);});
