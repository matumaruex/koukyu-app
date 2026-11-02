'use strict';
// チームは表示用。職員ID・勤務・計算条件・保存表の当時の所属を保持する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'p',name:'パート1',type:'part',startTime:'09:00',endTime:'17:00'},
 {id:'a',name:'職員A',type:'full',team:'太裳'},
 {id:'b',name:'職員B',type:'full',team:'清流'},
 {id:'c',name:'職員C',type:'full',team:'太裳'},
 {id:'u',name:'未設定の職員',type:'full'},
 {id:'p2',name:'パート2',type:'part',team:'清流',startTime:'09:00',endTime:'17:00'},
 {id:'x',name:'対象外の職員',type:'full',team:'表示しない',excludedByDefault:true}],
 schedules:{'2026-10':{excludedStaff:['x'],requests:{a:[2]},paidLeave:{a:[2]},assignments:{},locked:{a:{1:'early'}},history:{a:Array(5).fill('off')}}},
 preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const groups=t=>t.all('tr').filter(r=>r.className==='roster-team-row'),rows=t=>t.all('tr').filter(r=>r.className==='roster-staff-row');
const labels=t=>groups(t).map(r=>r.text),names=t=>rows(t).map(r=>r.children[0].text);
const form=h=>h.nodes['dialog-body'].all('form')[0],teamInput=h=>form(h).all('label').find(l=>l.text==='チーム（空欄は未設定）').all('input')[0];
const submit=h=>form(h).onsubmit({preventDefault(){}});
function start(){const h=harness(null,{current:raw});h.eval("schedule().assignments=Object.fromEntries(activeStaff().map(st=>[st.id,{'1':st.type==='part'?'part':'early','2':'off'}]));schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");return h;}
(async()=>{
 const h=start(),signature=h.get('inputData().signature'),assignments=h.get('schedule().assignments'),counts=h.get('countsAt(1)'),order=h.get('data.staff.map(s=>s.id)');
 const check=t=>{assert.deepEqual(labels(t),['チーム：太裳','チーム：清流','チーム未設定','パート']);assert.deepEqual(names(t),['職員A','職員C','職員B','未設定の職員','パート1','パート2']);assert(groups(t).every(r=>r.children[0].colSpan===37));assert.equal(t.all('tr').filter(r=>(r.className||'').startsWith('count-row')).length,4);assert.equal(rows(t)[0].children[7].text,'有');assert(groups(t).every(r=>!r.children.some(c=>c.onclick)));};
 for(const t of h.nodes.view.all('table'))check(t);assert.equal(h.get('days()'),31);
 const before=h.get('data'),stored=[...h.values];h.ctx.openLandscapeTable();check(h.nodes['dialog-body'].all('table')[0]);await h.click('閉じる');assert.deepEqual(h.get('data'),before);assert.deepEqual([...h.values],stored);assert.equal(h.calls.length,0);
 assert.equal(h.get('inputData().signature'),signature);assert.deepEqual(h.get('countsAt(1)'),counts);assert.deepEqual(h.get('schedule().assignments'),assignments);assert.deepEqual(h.get('data.staff.map(s=>s.id)'),order);

 // 所属だけの変更は再計算不要で、その場で作業表へ反映。既存のチームを候補に出す。
 h.eval("editStaff(data.staff.find(s=>s.id==='b'))");assert.deepEqual(form(h).all('datalist')[0].all('option').map(o=>o.value),['太裳','清流','表示しない']);teamInput(h).value='  太裳  ';submit(h);
 assert.equal(h.get("data.staff.find(s=>s.id==='b').team"),'太裳');assert.equal(h.get('inputData().signature'),signature);assert(!h.get('workChanged()'));assert.deepEqual(h.get('schedule().assignments'),assignments);assert.deepEqual(h.get('countsAt(1)'),counts);assert.deepEqual(labels(h.nodes.view.all('table')[0]),['チーム：太裳','チーム未設定','パート']);
 h.eval("editStaff(data.staff.find(s=>s.id==='b'))");teamInput(h).value='新チーム <北>';submit(h);assert.equal(h.get("data.staff.find(s=>s.id==='b').team"),'新チーム <北>');assert(labels(h.nodes.view.all('table')[0]).includes('チーム：新チーム <北>'));
 h.eval("editStaff(data.staff.find(s=>s.id==='u'))");teamInput(h).value='あ'.repeat(41);submit(h);assert(form(h).all('p').some(p=>p.text.includes('40文字以内')));assert.equal(h.get("data.staff.find(s=>s.id==='u').team"),'');teamInput(h).value='';submit(h);
 const reloaded=harness(null,{current:JSON.parse(h.values.get('koukyu_v4_data')),stored:{koukyu_v4_work:h.values.get('koukyu_v4_work')}});assert.equal(reloaded.get("data.staff.find(s=>s.id==='b').team"),'新チーム <北>');assert.deepEqual(reloaded.get('schedule().assignments'),assignments);assert.deepEqual(reloaded.get('schedule().history'),h.get('schedule().history'));assert.deepEqual(reloaded.get('schedule().paidLeave'),{a:[2]});

 // パートの所属は表示せず、勤務形態を戻す際の入力は保持する。
 h.eval("editStaff(data.staff.find(s=>s.id==='p2'))");const tf=form(h).all('label').find(l=>l.text==='チーム（空欄は未設定）');assert(tf.hidden);assert(form(h).all('p').some(p=>p.text.includes('パート職員は')&&!p.hidden));submit(h);assert.equal(h.get("data.staff.find(s=>s.id==='p2').team"),'清流');
 h.eval("editStaff(data.staff.find(s=>s.id==='p2'))");const type=form(h).all('select')[0];type.value='full';type.onchange();assert(!form(h).all('label').find(l=>l.text==='チーム（空欄は未設定）').hidden);assert.equal(teamInput(h).value,'清流');await h.click('閉じる');

 // 保存表・古い条件の作業表は当時の所属と並びを利用する。
 const saved=start();saved.eval("data.savedTables.push(RosterStorage.capture(data,key(),'保存表','saved'));data.staff.forEach(st=>st.team='現在の別チーム');state.tab='saved';state.archiveId='saved';render()");for(const t of saved.nodes.view.all('table'))check(t);const savedData=saved.get('data');saved.eval("openLandscapeTable(data.savedTables[0])");check(saved.nodes['dialog-body'].all('table')[0]);await saved.click('閉じる');assert.deepEqual(saved.get('data'),savedData);
 const stale=start();stale.eval("data.staff.find(s=>s.id==='a').monthlyDaysOff=10;data.staff.forEach(st=>st.team='現在の別チーム');render()");assert(stale.get('workChanged()'));for(const t of stale.nodes.view.all('table'))check(t);
 const backed=saved.get('RosterStorage.persisted(data)'),loaded=harness(null,{current:backed});assert(!loaded.get('state.loadError'));assert.equal(loaded.get('data.savedTables[0].staff[1].team'),'太裳');
 for(const bad of [null,1,{},[], 'あ'.repeat(41)]){const copy=structuredClone(raw);copy.staff[1].team=bad;const invalid=harness(null,{current:copy});assert(invalid.get('state.loadError'));assert.equal(invalid.values.get('koukyu_v4_data'),JSON.stringify(copy));}
 const invalidSaved=structuredClone(backed);invalidSaved.savedTables[0].staff[1].team={};assert(harness(null,{current:invalidSaved}).get('state.loadError'));
 const quota=harness(null,{current:raw,quota:true});quota.eval('editStaff(data.staff[1])');teamInput(quota).value='保存失敗';submit(quota);assert.equal(quota.get('data.staff[1].team'),'太裳');assert(form(quota).all('p').some(p=>p.text.includes('保存')));
 // 新規追加と所属解除。職員の登録順は表示のグループ化に使っても書き換えない。
 const fresh=harness(null,{current:raw});fresh.eval('editStaff()');form(fresh).all('input')[0].value='新職員';teamInput(fresh).value='清流';submit(fresh);assert.equal(fresh.get('data.staff.at(-1).team'),'清流');assert.equal(fresh.get('data.staff.at(-1).fixedDaysOff'),true);fresh.eval('editStaff(data.staff[1])');teamInput(fresh).value='  ';submit(fresh);assert.equal(fresh.get('data.staff[1].team'),'');assert.deepEqual(fresh.get('data.staff.slice(0,7).map(s=>s.id)'),order);
 // 同名の任意チームとパート・未設定の区分を混同せず、空グループを作らない。
 const special=harness(null,{current:{...structuredClone(raw),staff:[{id:'a',name:'同名',type:'full',team:'パート'},{id:'p',name:'パート',type:'part'}]}});assert.deepEqual(special.get('rosterTeams().map(g=>g.label)'),['チーム：パート','パート']);special.eval('data.staff=[]');assert.deepEqual(special.get('rosterTeams()'),[]);
 console.log('PASS: チーム設定・編集/解除/再読込・チーム別/未設定/パートの表示・横表示/印刷/保存表・計算と勤務の保持・不正入力と保存失敗');
})().catch(e=>{console.error(e);process.exitCode=1;});
