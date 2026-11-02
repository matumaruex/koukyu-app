'use strict';
// 一行の二つの入口から、希望と前期の独立した状態・保存・復元を検証する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const oldHistory=['late','overtime','off','early','night','nightOff','off'];
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'a',name:'職員A',type:'full',nightShiftType:'all',monthlyDaysOff:9},
 {id:'b',name:'職員B',type:'part',monthlyDaysOff:11,startTime:'09:00',endTime:'17:00'},
 {id:'c',name:'職員C',type:'full',monthlyDaysOff:9}],
 schedules:{'2026-10':{requests:{a:[7]},assignments:{},history:{a:oldHistory,c:Array(5).fill('off')},requestReviewed:{a:true},excludedStaff:['c']}}};
const rows=h=>h.nodes.view.all('div').filter(n=>(n.className||'').split(' ').includes('staff-row'));
const entry=(h,id,kind)=>rows(h).find(r=>r.text.includes('職員'+id)).all('button').find(b=>b.attributes['data-input-kind']===kind);
const cells=h=>h.nodes['dialog-body'].all('button').filter(b=>b.attributes['data-history-day']!==undefined);
const kind=h=>h.nodes['dialog-body'].all('select')[0];
function paint(h,index,value){kind(h).value=value;kind(h).onchange();cells(h)[index].click();}
function start(){const h=harness(null,{current:raw});h.eval("schedule().assignments={a:{'1':'early'},b:{'1':'part'}};schedule().workSignature=inputData().signature;render();setTab('requests')");return h;}
(async()=>{
 const h=start(),historyBefore=h.get('schedule().history'),wishes=h.get('schedule().requests'),reviewed=h.get('schedule().requestReviewed'),snapshot=h.get('schedule().workSnapshot'),table=h.get('schedule().assignments');
 assert(h.nodes.view.text.includes('希望・前期'));assert.equal(rows(h).length,3);for(const row of rows(h))assert.deepEqual(row.all('button').map(b=>b.attributes['data-input-kind']),['requests','history']);
 assert.equal(entry(h,'A','requests').text,'希望済');assert.equal(entry(h,'A','history').text,'前期済');assert.equal(entry(h,'B','requests').text,'希望未');assert.equal(entry(h,'B','history').text,'前期未');assert.equal(entry(h,'C','history').text,'前期済');assert(entry(h,'C','history').attributes['aria-label'].includes('今期対象外'));
 entry(h,'A','requests').click();assert(h.nodes.dialog.attributes['aria-label'].includes('職員Aさんの希望入力'));assert.equal(cells(h).length,0);await h.click('閉じる');assert.deepEqual(h.get('schedule().history'),historyBefore);
 // 途中の前期実績は未保存。閉じる操作のキャンセルと破棄の両方を扱う。
 entry(h,'B','history').click();assert(h.nodes.dialog.attributes['aria-label'].includes('職員Bさんの前期入力'));assert.equal(cells(h).length,5);assert.equal(h.nodes['dialog-body'].all('select').length,1);assert.deepEqual(kind(h).all('option').map(o=>o.value),['early','late','night','nightOff','off','overtime','part']);paint(h,0,'part');assert.equal(h.get('schedule().history.b??null'),null);h.ctx.confirm=()=>false;await h.click('閉じる');assert(h.nodes.dialog.open);h.ctx.confirm=()=>true;await h.click('閉じる');assert(!h.nodes.dialog.open);assert.equal(h.get('schedule().history.b??null'),null);
 entry(h,'B','history').click();for(let i=0;i<5;i++)paint(h,i,i%2?'part':'off');await h.click('入力完了');assert(!h.nodes.dialog.open);assert.equal(entry(h,'B','history').text,'前期済');assert.equal(entry(h,'B','requests').text,'希望未');assert.deepEqual(h.get('schedule().history.b'),['off','part','off','part','off']);assert.deepEqual(h.get('schedule().history.a'),oldHistory);assert.deepEqual(h.get('schedule().requests'),wishes);assert.deepEqual(h.get('schedule().requestReviewed'),reviewed);assert.deepEqual(h.get('schedule().assignments'),table);assert.deepEqual(h.get('schedule().workSnapshot'),snapshot);assert(h.get('workChanged()'));
 const re=harness(null,{current:JSON.parse(h.values.get('koukyu_v4_data')),stored:{koukyu_v4_work:h.values.get('koukyu_v4_work')}});re.eval("setTab('requests')");assert.equal(entry(re,'B','history').text,'前期済');assert.equal(entry(re,'B','requests').text,'希望未');assert.deepEqual(re.get('schedule().assignments'),table);
 // 七日実績の先頭二日を残し、対象外の職員も勝手に参加させずに入力できる。
 entry(h,'A','history').click();paint(h,0,'late');await h.click('入力完了');assert.deepEqual(h.get('schedule().history.a'),['late','overtime','late','early','night','nightOff','off']);assert.equal(entry(h,'A','requests').text,'希望済');
 entry(h,'C','history').click();assert.deepEqual(cells(h).map(b=>b.all('span').at(-1).text),Array(5).fill('公'));paint(h,1,'early');await h.click('入力完了');assert.deepEqual(h.get('schedule().excludedStaff'),['c']);assert.equal(h.get('schedule().history.c[1]'),'early');assert.deepEqual(h.get('inputData().map'),{s0:'a',s1:'b'});
 // 再クリックで未入力へ戻す場合も、五日そろわなければ元の実績を上書きしない。
 const storedHistory=h.get('schedule().history.b');entry(h,'B','history').click();paint(h,0,'off');await h.click('入力完了');assert(h.nodes['dialog-body'].text.includes('5日分をすべて選んでください'));assert.deepEqual(h.get('schedule().history.b'),storedHistory);await h.click('閉じる');
 // 取り込みは一覧から。入力済みを保ち、未入力の職員だけを更新する。
 const imported=start();imported.eval("data.schedules['2026-09']={requests:{},assignments:{a:Object.fromEntries(Array.from({length:30},(_,i)=>[i+1,'off'])),b:Object.fromEntries(Array.from({length:30},(_,i)=>[i+1,'part']))}};data.savedTables.push(RosterStorage.capture(data,'2026-09','前期','previous'));delete data.schedules['2026-09'];render()");await imported.click('前期の表から取り込む','view');await imported.click('未入力の人だけ取り込む');assert.deepEqual(imported.get('schedule().history.a'),oldHistory);assert.deepEqual(imported.get('schedule().history.b'),Array(7).fill('part'));assert.equal(entry(imported,'B','history').text,'前期済');assert.equal(entry(imported,'B','requests').text,'希望未');assert.deepEqual(imported.get('schedule().requests'),wishes);
 const empty=start();await empty.click('前期の表から取り込む','view');assert(empty.nodes['dialog-body'].text.includes('保存表がありません'));await empty.click('入力一覧に戻る');assert.equal(empty.get('state.tab'),'requests');assert(!empty.nodes.dialog.open);
 // 前期入力は希望・前期に集約し、設定は必要人数の入口だけを保つ。
 h.ctx.setTab('schedule');assert(!h.nodes.view.all('button').some(b=>b.text==='前期の勤務を入力'||b.text==='必要人数を確認・変更'));h.ctx.setTab('requests');entry(h,'A','history').click();assert.equal(cells(h).length,5);await h.click('閉じる');h.ctx.settings();assert(!h.nodes['dialog-body'].all('button').some(b=>b.text==='前期の勤務を入力'));assert(h.nodes['dialog-body'].all('button').some(b=>b.text==='必要人数を確認・変更'));await h.click('閉じる');
 // 古い入力画面の操作は別期間へ実績を書き込まない。
 const stale=start();entry(stale,'B','history').click();for(let i=0;i<5;i++)paint(stale,i,'off');const complete=stale.nodes['dialog-body'].all('button').find(b=>b.text==='入力完了');stale.ctx.changePeriod(1);complete.click();assert.equal(stale.get('schedule().history?.b??null'),null);assert.equal(stale.get("data.schedules['2026-10'].history.b??null"),null);assert(!stale.nodes.dialog.open);
 assert.equal(h.calls.length,0);assert.equal(imported.calls.length,0);
 console.log('PASS: 希望・前期の一行一覧と別々の状態・五日カレンダー・途中入力の保護・七日保持・取り込み・対象外・期間分離・復元');
})().catch(e=>{console.error(e);process.exitCode=1;});
