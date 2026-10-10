'use strict';
// 一覧→入力→完了→再読込を通して、希望・確認状態・旧表を保持する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'b',name:'職員B',type:'full',canOvertime:true,nightShiftType:'all',monthlyDaysOff:9,noConsecutiveRest:true,nightRemainderPriority:true,overtimePreference:2},
 {id:'a',name:'職員A',type:'part',nightShiftType:'none',monthlyDaysOff:11,startTime:'09:00',endTime:'17:00'},
 {id:'c',name:'職員C',type:'full',nightShiftType:'none',monthlyDaysOff:9}],
 schedules:{'2026-10':{assignments:{},requests:{b:[7]},shiftRequests:{b:{8:'early',9:'night'}},requestReviewed:{b:true},excludedStaff:['c'],fairnessExcludedStaff:['c'],history:{b:Array(7).fill('off')}}},
 preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[4,4,4],maxReducedSundays:0}}};
function start(options={}){const h=harness(null,{current:raw,...options});h.eval("setTab('requests')");return h;}
const day=(h,d)=>h.nodes['dialog-body'].all('button').find(e=>e.attributes['data-request-day']===String(d));
const mode=h=>h.nodes['dialog-body'].all('select')[0];
const row=(h,id)=>h.nodes.view.all('div').find(e=>e.className?.startsWith('staff-row')&&e.text.includes('職員'+id));
(async()=>{
 const h=start(),before=h.get('inputData()');
 assert.deepEqual(h.nodes.view.all('strong').map(e=>e.text),['職員B','職員A','職員C今期対象外']);
 assert(row(h,'B').text.includes('入力済み'));assert(row(h,'A').text.includes('未確認'));assert(row(h,'C').text.includes('今期対象外'));assert(row(h,'C').all('input')[0].checked);
 assert.equal(h.nodes.view.all('select').length,0);assert(!h.nodes.view.text.includes('公休表を作る'));assert(!h.nodes.view.text.includes('希望休：'));
 // 3.41の追加ルール・時間を変えず、開く/閉じるだけでは条件も確認状態も変わらない。
 h.ctx.editRequests('b');assert.equal(h.nodes.dialog.open,true);assert(h.nodes['dialog-body'].text.includes('希望休：1日 ／ 希望出勤：1日 ／ 希望夜勤：1日'));
 assert(!h.nodes['dialog-body'].text.includes('希望の種類を選んで'));assert(!h.nodes['dialog-body'].text.includes('すべて必ず守る指定'));
 await h.click('閉じる');assert.equal(h.nodes.dialog.open,false);assert.deepEqual(h.get('inputData()'),before);
 assert.equal(before.p.overtimeCycleLimit,true);assert.equal(before.p.staff[1].nightRemainderPriority,true);assert.equal(before.p.staff[1].noConsecutiveRest,true);
 // 作業表は作成時の希望を残し、希望の編集後も勤務を保持する。
 h.eval("schedule().assignments={b:{1:'early',7:'off'},a:{1:'part'}};schedule().workSignature=inputData().signature;render()");
 const snapshot=h.get('schedule().workSnapshot'),assignments=h.get('schedule().assignments'),history=h.get('schedule().history');assert(snapshot);
 h.ctx.editRequests('b');day(h,10).click();assert(h.get('schedule().requests.b').includes(10));assert.equal(h.get('schedule().requestReviewed.b'),false);assert(row(h,'B').text.includes('入力中'));assert(h.nodes['dialog-body'].text.includes('希望休：2日'));
 // 希望の種類変更・置換・再クリック解除。すべての記号は種類にかかわらず表示する。
 mode(h).value='night';mode(h).onchange();day(h,10).click();assert(!h.get('schedule().requests.b').includes(10));assert.equal(h.get('schedule().shiftRequests.b[10]'),'night');assert(day(h,8).text.endsWith('A'));assert(h.nodes['dialog-body'].text.includes('希望夜勤：2日'));
 day(h,10).click();assert.equal(h.get('schedule().shiftRequests.b[10]??null'),null);
 await h.click('入力完了');assert.equal(h.nodes.dialog.open,false);assert(row(h,'B').text.includes('入力済み'));assert.equal(h.get('state.reqStaff'),'b');assert.deepEqual(h.get('schedule().assignments'),assignments);assert.deepEqual(h.get('schedule().workSnapshot'),snapshot);assert.deepEqual(h.get('schedule().history'),history);
 // パートにA/夜勤を提示しない。未入力の完了は希望なし。
 h.ctx.editRequests('a');assert.deepEqual(mode(h).children.map(e=>e.value),['off','part']);await h.click('入力完了');assert(row(h,'A').text.includes('希望なし'));assert(h.nodes.view.text.includes('2 / 2人 確認済み'));
 assert(!h.nodes.view.text.includes('公休表を作る'));
 // 長期休暇は従来の公休比較設定だけを今期に保存する。
 const leave=row(h,'B').all('input')[0];leave.checked=true;leave.onchange();assert.deepEqual(h.get('schedule().fairnessExcludedStaff'),['c','b']);assert.deepEqual(h.get('schedule().requests.b'),[7]);assert.deepEqual(h.get('schedule().excludedStaff'),['c']);
 // 対象外の人も編集可能だが、参加を勝手に変えない。
 h.ctx.editRequests('c');day(h,12).click();await h.click('入力完了');assert.deepEqual(h.get('schedule().requests.c'),[12]);assert.deepEqual(h.get('schedule().excludedStaff'),['c']);
 const reopen=harness(null,{current:JSON.parse(h.values.get('koukyu_v4_data')),stored:{koukyu_v4_work:h.values.get('koukyu_v4_work')}});reopen.eval("setTab('requests')");assert(row(reopen,'B').text.includes('入力済み'));assert(row(reopen,'A').text.includes('希望なし'));assert.deepEqual(reopen.get('schedule().assignments'),assignments);
 reopen.ctx.changePeriod(1);assert.deepEqual(reopen.get('schedule().fairnessExcludedStaff||[]'),[]);assert.deepEqual(reopen.get('schedule().requests'),{});
 // 古い入力画面の操作は別の期へ書き込めない。
 h.ctx.editRequests('b');const staleDay=day(h,13);h.ctx.changePeriod(1);staleDay.click();assert.deepEqual(h.get('schedule().requests'),{});assert.equal(h.nodes.dialog.open,false);
 // 容量不足では希望・確認・長期休暇を戻す。入力画面は閉じず失敗を示す。
 const q=start({quota:true}),original=q.get('schedule().requests');q.ctx.editRequests('b');day(q,11).click();assert.deepEqual(q.get('schedule().requests'),original);assert.equal(q.get('schedule().requestReviewed.b'),true);assert(q.nodes['dialog-body'].text.includes('この端末に保存できませんでした'));
 q.ctx.editRequests('a');await q.click('入力完了');assert.notEqual(q.get('schedule().requestReviewed.a??null'),true);assert.equal(q.nodes.dialog.open,true);assert(q.nodes['dialog-body'].text.includes('この端末に保存できませんでした'));
 const failedLeave=row(q,'B').all('input')[0];failedLeave.checked=true;failedLeave.onchange();assert.deepEqual(q.get('schedule().fairnessExcludedStaff'),['c']);assert.equal(row(q,'B').all('input')[0].checked,false);
 const empty=start({current:{...raw,staff:[],schedules:{}}});assert(empty.nodes.view.text.includes('職員を登録する'));
 console.log('PASS: 希望の2段一覧、種類・日数・完了・再編集、長期休暇・対象外・期間分離、保存失敗の復元、旧表・前期・計算条件の保持');
})().catch(e=>{console.error(e);process.exitCode=1;});
