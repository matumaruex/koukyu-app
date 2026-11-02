'use strict';
// 名前欄だけを色分けし、勤務・集計・計算条件と当時の区分を保持する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'p',name:'パート1',type:'part',startTime:'09:00',endTime:'17:00'},
 {id:'a',name:'職員A',type:'full',teamGroup:'A'},
 {id:'b',name:'職員B',type:'full',teamGroup:'B'},
 {id:'c',name:'職員C',type:'full',teamGroup:'A'},
 {id:'u',name:'未設定の職員',type:'full'},
 {id:'v',name:'職員D',type:'full',teamGroup:'C'},
 {id:'p2',name:'パート2',type:'part',teamGroup:'B',startTime:'09:00',endTime:'17:00'},
 {id:'x',name:'対象外の職員',type:'full',teamGroup:'C',excludedByDefault:true}],
 schedules:{'2026-10':{excludedStaff:['x'],requests:{a:[2]},paidLeave:{a:[2]},assignments:{},locked:{a:{1:'early'}},history:{a:Array(5).fill('off')}}},
 preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const rows=t=>t.all('tr').filter(r=>r.className==='roster-staff-row'),names=t=>rows(t).map(r=>r.children[0].text),colors=t=>rows(t).map(r=>r.children[0].className);
const form=h=>h.nodes['dialog-body'].all('form')[0],team=h=>form(h).all('label').find(l=>l.text.startsWith('チーム（')).all('select')[0],submit=h=>form(h).onsubmit({preventDefault(){}});
function start(){const h=harness(null,{current:raw});h.eval("schedule().assignments=Object.fromEntries(activeStaff().map(st=>[st.id,{'1':st.type==='part'?'part':'early','2':'off'}]));schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");return h;}
(async()=>{
 const h=start(),signature=h.get('inputData().signature'),assignments=h.get('schedule().assignments'),counts=h.get('countsAt(1)'),order=h.get('data.staff.map(s=>s.id)');
 const check=t=>{assert.deepEqual(names(t),['職員A','職員C','職員B','職員D','未設定の職員','パート1','パート2']);assert.deepEqual(colors(t),['name team-A','name team-A','name team-B','name team-C','name','name team-part','name team-part']);assert.equal(t.all('tr').length,13);assert(!t.all('tr').some(r=>r.className==='roster-team-row'));assert(!t.text.includes('チーム：'));assert(!t.text.includes('チーム未設定'));assert.equal(rows(t)[0].children[7].text,'有');assert(rows(t).every(r=>r.children.length===37));};
 for(const t of h.nodes.view.all('table'))check(t);
 const before=h.get('data'),stored=[...h.values];h.ctx.openLandscapeTable();check(h.nodes['dialog-body'].all('table')[0]);await h.click('閉じる');assert.deepEqual(h.get('data'),before);assert.deepEqual([...h.values],stored);assert.equal(h.calls.length,0);
 assert.equal(h.get('inputData().signature'),signature);assert.deepEqual(h.get('countsAt(1)'),counts);assert.deepEqual(h.get('schedule().assignments'),assignments);assert.deepEqual(h.get('data.staff.map(s=>s.id)'),order);
 // チーム変更・解除は再計算せず、作業表の名前欄と表示順へ反映する。
 h.eval("editStaff(data.staff.find(s=>s.id==='b'))");assert.deepEqual(team(h).all('option').map(o=>o.value),['','A','B','C']);assert.equal(form(h).all('datalist').length,0);team(h).value='A';submit(h);
 assert.equal(h.get("data.staff.find(s=>s.id==='b').teamGroup"),'A');assert.equal(h.get('inputData().signature'),signature);assert(!h.get('workChanged()'));assert.deepEqual(h.get('schedule().assignments'),assignments);assert.deepEqual(h.get('countsAt(1)'),counts);assert.equal(rows(h.nodes.view.all('table')[0])[1].children[0].className,'name team-A');
 h.eval("editStaff(data.staff.find(s=>s.id==='b'))");team(h).value='';submit(h);assert.equal(h.get("data.staff.find(s=>s.id==='b').teamGroup"),'');assert.equal(rows(h.nodes.view.all('table')[0]).find(r=>r.children[0].text==='職員B').children[0].className,'name');
 const reloaded=harness(null,{current:JSON.parse(h.values.get('koukyu_v4_data')),stored:{koukyu_v4_work:h.values.get('koukyu_v4_work')}});assert.equal(reloaded.get("data.staff.find(s=>s.id==='b').teamGroup"),'');assert.deepEqual(reloaded.get('schedule().assignments'),assignments);assert.deepEqual(reloaded.get('schedule().history'),h.get('schedule().history'));assert.deepEqual(reloaded.get('schedule().paidLeave'),{a:[2]});
 // パートは専用色を使い、勤務形態を戻す時の区分は保持する。
 h.eval("editStaff(data.staff.find(s=>s.id==='p2'))");assert(form(h).all('label').find(l=>l.text.startsWith('チーム（')).hidden);submit(h);assert.equal(h.get("data.staff.find(s=>s.id==='p2').teamGroup"),'B');h.eval("editStaff(data.staff.find(s=>s.id==='p2'))");const type=form(h).all('select')[0];type.value='full';type.onchange();assert(!form(h).all('label').find(l=>l.text.startsWith('チーム（')).hidden);assert.equal(team(h).value,'B');await h.click('閉じる');
 // 保存表・古い条件の作業表は当時の区分・表示順を利用する。
 const saved=start();saved.eval("data.savedTables.push(RosterStorage.capture(data,key(),'保存表','saved'));data.staff.forEach(st=>st.teamGroup='C');state.tab='saved';state.archiveId='saved';render()");for(const t of saved.nodes.view.all('table'))check(t);const savedData=saved.get('data');saved.eval("openLandscapeTable(data.savedTables[0])");check(saved.nodes['dialog-body'].all('table')[0]);await saved.click('閉じる');assert.deepEqual(saved.get('data'),savedData);
 const stale=start();stale.eval("data.staff.find(s=>s.id==='a').monthlyDaysOff=10;data.staff.forEach(st=>st.teamGroup='C');render()");assert(stale.get('workChanged()'));for(const t of stale.nodes.view.all('table'))check(t);
 const backed=saved.get('RosterStorage.persisted(data)'),loaded=harness(null,{current:backed});assert(!loaded.get('state.loadError'));assert.equal(loaded.get('data.savedTables[0].staff[1].teamGroup'),'A');
 for(const bad of [null,1,{},[], 'D','a']){const copy=structuredClone(raw);copy.staff[1].teamGroup=bad;const invalid=harness(null,{current:copy});assert(invalid.get('state.loadError'));assert.equal(invalid.values.get('koukyu_v4_data'),JSON.stringify(copy));}
 const invalidSaved=structuredClone(backed);invalidSaved.savedTables[0].staff[1].teamGroup={};assert(harness(null,{current:invalidSaved}).get('state.loadError'));
 const quota=harness(null,{current:raw,quota:true});quota.eval('editStaff(data.staff[1])');team(quota).value='C';submit(quota);assert.equal(quota.get('data.staff[1].teamGroup'),'A');assert(form(quota).all('p').some(p=>p.text.includes('保存')));
 // 新規追加は公休固定を維持。所属によって元の職員配列を並べ替えない。
 const fresh=harness(null,{current:raw});fresh.eval('editStaff()');form(fresh).all('input')[0].value='新職員';team(fresh).value='B';submit(fresh);assert.equal(fresh.get('data.staff.at(-1).teamGroup'),'B');assert.equal(fresh.get('data.staff.at(-1).fixedDaysOff'),true);assert.deepEqual(fresh.get('data.staff.slice(0,8).map(s=>s.id)'),order);
 // 名前付きの旧チームは対応を一度確定し、再読込・並べ替え後も所属と元の名前を保持。
 const legacyRaw=structuredClone(raw);legacyRaw.staff=[{id:'a',name:'旧1',type:'full',team:'太裳'},{id:'b',name:'旧2',type:'full',team:'清流'},{id:'c',name:'旧3',type:'full',team:'太裳'},{id:'d',name:'旧4',type:'full',team:'第三'},{id:'e',name:'旧5',type:'full',team:'第四'}];const legacy=harness(null,{current:legacyRaw});assert.deepEqual(legacy.get('data.staff.map(st=>st.teamGroup)'),['A','B','A','C','']);assert.deepEqual(legacy.get('data.staff.map(st=>st.team)'),['太裳','清流','太裳','第三','第四']);legacy.eval('data.staff.reverse();save(true)');const again=harness(null,{current:JSON.parse(legacy.values.get('koukyu_v4_data'))});assert.deepEqual(again.get('data.staff.map(st=>st.teamGroup)'),['','C','A','B','A']);
 legacy.eval('editStaff(data.staff.find(st=>st.id===\'a\'))');team(legacy).value='C';submit(legacy);assert.equal(legacy.get("data.staff.find(st=>st.id==='a').team"),'太裳');assert.equal(legacy.get("data.staff.find(st=>st.id==='a').teamGroup"),'C');
 const reserved=structuredClone(raw);reserved.staff=[{id:'a',name:'既存A',type:'full',team:'A'},{id:'b',name:'名前付き',type:'full',team:'清流'}];assert.deepEqual(harness(null,{current:reserved}).get('data.staff.map(st=>st.teamGroup)'),['A','B']);
 console.log('PASS: 名前欄だけの色分け・見出し行撤去・A/B/C選択と解除・パート専用色・旧チーム移行・保存表/印刷/横表示・計算と勤務の保持');
})().catch(e=>{console.error(e);process.exitCode=1;});
