'use strict';
// 有給は公休日数の内数。計算へは希望休として渡し、入力と表・保存で区別を保持する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={schemaVersion:4,savedTables:[],staff:[{id:'a',name:'職員A',type:'full',monthlyDaysOff:9,fixedDaysOff:true,canOvertime:true,nightShiftType:'all'},{id:'b',name:'職員B',type:'part',monthlyDaysOff:11,nightShiftType:'none',startTime:'09:00',endTime:'17:00'}],schedules:{'2026-10':{requests:{a:[7]},assignments:{},history:{a:Array(5).fill('off')}}}};
const day=(h,d)=>h.nodes['dialog-body'].all('button').find(e=>e.attributes['data-request-day']===String(d));
const mode=h=>h.nodes['dialog-body'].all('select')[0];
(async()=>{
 const h=harness(null,{current:raw}),input=h.get('inputData()');
 h.ctx.editRequests('a');assert(mode(h).children.some(e=>e.value==='paidLeave'&&e.text.includes('有給')));
 mode(h).value='paidLeave';mode(h).onchange();day(h,7).click();assert.equal(h.get("requestAt('a',7)"),'paidLeave');assert.deepEqual(h.get('schedule().requests.a'),[7]);assert.deepEqual(h.get('schedule().paidLeave.a'),[7]);assert.equal(h.get("requestCount('a')"),1);assert.equal(day(h,7).all('span').at(-1).text,'有');assert(day(h,7).attributes['aria-label'].includes('有給'));assert(h.nodes['dialog-body'].text.includes('希望休：0日 ／ 有給：1日'));
 assert.deepEqual(h.get('inputData()'),input);assert.equal(h.get('inputData().p.staff[0].monthlyDaysOff'),9);assert.equal(h.get('inputData().p.staff[0].fixedDaysOff'),true);assert(!Object.hasOwn(h.get('inputData().p'),'paidLeave'));
 // 公休との切り替えは計算条件を変えず、出勤との切り替えと解除では有給の指定を消す。
 mode(h).value='off';mode(h).onchange();day(h,7).click();assert.equal(h.get("requestAt('a',7)"),'off');assert.deepEqual(h.get('inputData()'),input);assert.equal(h.get('schedule().paidLeave??null'),null);
 mode(h).value='paidLeave';mode(h).onchange();day(h,7).click();mode(h).value='early';mode(h).onchange();day(h,7).click();assert.equal(h.get("requestAt('a',7)"),'early');assert.deepEqual(h.get('schedule().requests.a'),[]);assert.equal(h.get('schedule().paidLeave??null'),null);
 mode(h).value='paidLeave';mode(h).onchange();day(h,7).click();day(h,7).click();assert.equal(h.get("requestAt('a',7)??null"),null);assert.equal(h.get('schedule().paidLeave??null'),null);
 day(h,7).click();await h.click('入力完了');const stored=JSON.parse(h.values.get('koukyu_v4_data')),re=harness(null,{current:stored});assert.deepEqual(re.get('schedule().paidLeave.a'),[7]);assert.equal(re.get("requestAt('a',7)"),'paidLeave');assert.equal(re.get('schedule().requestReviewed.a'),true);
 re.ctx.editRequests('b');assert(mode(re).children.some(e=>e.value==='paidLeave'));mode(re).value='paidLeave';mode(re).onchange();day(re,8).click();assert.deepEqual(re.get('schedule().requests.b'),[8]);assert.deepEqual(re.get('schedule().paidLeave.b'),[8]);await re.click('閉じる');
 // 9日の休みのうち2日だけを「有」と表示し、合計は9日。計算用の勤務キーはoffのまま。
 const rows={s0:Object.fromEntries(Array.from({length:31},(_,i)=>[String(i+1),i<9?'off':'early'])),s1:{'1':'part'}};
 const made=harness(null,{current:raw,response:async()=>({status:'FEASIBLE',seconds:3,assignments:rows,search:{done:true},boundaryComplete:true,optimizationPolicy:'quality-first-19'})});made.eval("toggleRequest('a',7,'paidLeave');toggleRequest('a',8,'paidLeave')");await made.ctx.generate();assert.deepEqual(made.calls[0].input.requests.s0,[7,8]);assert(!Object.values(made.calls[0].input.shiftRequests||{}).some(row=>Object.values(row).includes('paidLeave')));
 const table=made.nodes.view.all('table')[0],row=table.all('tr').find(r=>r.className==='roster-staff-row'),cells=row.children.slice(6);assert.equal(cells.filter(c=>c.text==='有').length,2);assert.equal(cells.filter(c=>c.text==='公').length,7);assert.equal(row.children[1].text,'9');assert(row.children[1].attributes['aria-label'].includes('有給2日を含む'));assert.equal(made.get('schedule().assignments.a[7]'),'off');assert.deepEqual(made.get('countsAt(7)'),[0,0,0]);
 for(const t of made.nodes.view.all('table'))assert.equal(t.all('tr').find(r=>r.className==='roster-staff-row').children.slice(6).filter(c=>c.text==='有').length,2);
 const restored=harness(null,{current:JSON.parse(made.values.get('koukyu_v4_data')),stored:{koukyu_v4_work:made.values.get('koukyu_v4_work')}});assert.equal(restored.nodes.view.all('table')[0].all('tr').find(r=>r.className==='roster-staff-row').children.slice(6).filter(c=>c.text==='有').length,2);
 const snapshot=made.get('data');made.ctx.openLandscapeTable();assert.equal(made.nodes['dialog-body'].all('table')[0].all('tr').find(r=>r.className==='roster-staff-row').children.slice(6).filter(c=>c.text==='有').length,2);await made.click('閉じる');assert.deepEqual(made.get('data'),snapshot);
 made.eval("editShift(data.staff[0],7)");assert(made.nodes['dialog-body'].all('option').some(o=>o.value==='off'&&o.text==='有（有給）'));await made.click('閉じる');
 assert(made.ctx.diagnosisIssues({status:'EXPLAINED',proven:true,droppedWishes:[{kind:'request',staff:'s0',day:7}]},made.get('inputData().map')).items[0].includes('有給'));
 assert(made.ctx.errorsText([{code:'request',staff:'s0',day:7}],made.get('inputData().map')).includes('有給の希望日への出勤'));
 made.eval("data.savedTables.push(RosterStorage.capture(data,key(),'有給確認','saved'));testSavedSnapshot(data.savedTables.find(r=>r.id==='saved'))");assert(made.nodes.view.all('table').every(t=>t.all('tr').find(r=>r.className==='roster-staff-row').children.slice(6).filter(c=>c.text==='有').length===2));
 const checked=made.ctx.checkBackup(made.get('data'));assert.deepEqual(checked.savedTables[0].schedule.paidLeave.a,[7,8]);
 // 公休→有給の表記変更は、現在の表や計算の署名を保持してすぐ反映する。
 const same=harness(null,{current:raw});same.eval("schedule().assignments={a:{'7':'off'},b:{'1':'part'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");const signature=same.get('inputData().signature');same.eval("toggleRequest('a',7,'paidLeave')");assert.equal(same.get('inputData().signature'),signature);assert(!same.get('workChanged()'));assert.equal(same.nodes.view.all('table')[0].all('tr').find(r=>r.className==='roster-staff-row').children[12].text,'有');
 // 保存表は当時の有給、作業表は現在の有給を表示する。
 same.eval("data.savedTables.push(RosterStorage.capture(data,key(),'有給保存','paid'));toggleRequest('a',7,'off');testSavedSnapshot(data.savedTables.find(r=>r.id==='paid'))");assert.equal(same.nodes.view.all('table')[0].all('tr').find(r=>r.className==='roster-staff-row').children[12].text,'有');assert.equal(same.get("data.schedules[key()].paidLeave??null"),null);
 // バックアップでは、同じ日の希望休に属さない指定や日付の壊れを拒否する。
 for(const paid of [null,[],{a:[0]},{a:[32]},{a:[7,7]},{a:['7']},{a:[8]}])assert.throws(()=>h.ctx.checkBackup({...raw,schedules:{'2026-10':{...raw.schedules['2026-10'],paidLeave:paid}}}));
 const q=harness(null,{current:raw,quota:true}),before=q.get('data');assert.equal(q.ctx.toggleRequest('a',7,'paidLeave'),false);assert.deepEqual(q.get('data'),before);
 console.log('PASS: 有給の選択・解除・切替・保存復元、公休日数の内数、人数から除外、表/印刷/横表示/保存表、検査と保存失敗');
})().catch(e=>{console.error(e);process.exitCode=1;});
