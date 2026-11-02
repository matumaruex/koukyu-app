'use strict';
// 表の操作・注意・凡例を配置し直しても、表示中の表と保存時の条件を保持する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'a',name:'作成時の職員A',type:'full',monthlyDaysOff:9,nightShiftType:'all',canOvertime:true,minConsecutiveRest:1},
 {id:'b',name:'作成時の職員B',type:'full',monthlyDaysOff:9,nightShiftType:'all'}],
 schedules:{'2026-10':{requests:{a:[7]},assignments:{},locked:{a:{1:'early'}},history:{a:Array(5).fill('off'),b:Array(5).fill('off')}}},
 preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
function start(){const h=harness(null,{current:raw});h.eval("schedule().assignments={a:{'1':'early','2':'overtime','3':'early','4':'early','7':'off','8':'off'},b:{'1':'night','2':'nightOff','3':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'DRAFT',signature:inputData().signature,optimizationPolicy:OPTIMIZATION_POLICY,boundaryComplete:true,ruleExceptions:[{code:'consecutive',staff:'s0',day:4,actual:4,limit:3,plusOne:false}],unmetConditions:[{code:'coverage',day:1,time:420,actual:1,required:2}],nightRestPreferences:{rule:'night-request-gap-1',unmet:[{staff:'s0',day:7}],minimumUnmetProven:false}};render()");return h;}
const cls=(e,c)=>(e.className||'').split(' ').includes(c);
const wrap=h=>h.nodes.view.all('div').find(e=>cls(e,'month-wrap'));
const part=(w,c)=>w.children.find(e=>e&&cls(e,c));
const visible=e=>e.className==='print-only'?'':e.textContent+e.children.map(c=>typeof c==='object'&&c.children?visible(c):String(c)).join('');
(async()=>{
 const h=start(),w=wrap(h),heading=part(w,'month-heading'),operations=part(w,'month-operations'),scroll=part(w,'scroll'),guide=part(w,'month-guide');
 assert(heading&&operations&&scroll&&guide);assert(w.children.indexOf(heading)<w.children.indexOf(operations));assert(w.children.indexOf(operations)<w.children.indexOf(scroll));assert(w.children.indexOf(scroll)<w.children.indexOf(guide));
 assert(w.children.indexOf(part(w,'consecutive-rest-summary'))<w.children.indexOf(heading));
 assert.equal(heading.all('button').filter(b=>b.text==='横画面で見る').length,1);
 assert.equal(h.nodes.view.all('button').filter(b=>b.text==='横画面で見る').length,1);
 assert(operations.text.includes('表のマスを押すと、その日の勤務を変更できます。'));assert(!operations.text.includes('太枠'));
 for(const text of ['金の三角','点線枠','太枠','A 早出7:00','人数欄は実際/必要','必要人数：','希望休の初日は'])assert(guide.text.includes(text),text);
 assert(!guide.text.includes('表のマスを押すと'));assert(!guide.text.includes('夜勤後にできなかった希望休'));
 const text=visible(h.nodes.view);assert.equal(text.split('夜勤後にできなかった希望休').length-1,1);assert.equal(text.split('希望休の初日は').length-1,1);
 assert.equal(guide.text.split('赤は人数不足').length-1,1);assert(!text.includes('赤い人数欄は人数不足・夜勤未配置です。'));
 const roster=h.nodes.view.all('article').find(e=>e.id==='roster-result'),attention=roster.children.find(e=>cls(e,'result-attention'));
 assert(roster.children.indexOf(attention)<roster.children.indexOf(w));assert(attention.text.includes('4連勤目'));

 // 印刷は注意を表の上へ、横表示は見出し横のボタンから開く。
 const printable=h.nodes.view.all('div').find(e=>e.className==='print-only'),printed=printable.all('div').find(e=>cls(e,'month-wrap'));
 assert.equal(printed.all('button').length,0);assert(!part(printed,'month-operations'));
 assert(printed.children.indexOf(part(printed,'month-notices'))<printed.children.indexOf(part(printed,'scroll')));
 assert(part(printed,'month-guide').text.includes('希望休の初日は'));
 const before=h.get('data'),signature=h.get('inputData().signature');heading.all('button')[0].click();assert(h.nodes.dialog.open);
 const viewer=h.nodes['dialog-body'];assert(!viewer.all('button').some(b=>b.text==='横画面で見る'));assert(!viewer.text.includes('表のマスを押すと'));
 const viewed=viewer.all('div').find(e=>cls(e,'month-wrap'));assert(!part(viewed,'month-notices'));assert(part(viewed,'scroll'));const notice=viewer.all('section').find(e=>cls(e,'landscape-notice-panel'));assert(notice&&notice.hidden);assert(notice.text.includes('夜勤後にできなかった希望休'));assert(viewer.children[0].all('button').some(b=>b.text==='注意3件'));
 await h.click('閉じる');assert.deepEqual(h.get('data'),before);assert.equal(h.get('inputData().signature'),signature);assert.equal(h.calls.length,0);

 // 保存した表は、表のそばのボタンから保存時の職員・期間で開く。
 const saved=start();saved.eval("data.savedTables.push(RosterStorage.capture(data,key(),'保存した表','saved'));data.staff[0].name='現在の別名';state.month=11;state.tab='saved';state.archiveId='saved';render()");
 const sw=wrap(saved);assert(!part(sw,'month-operations'));assert(part(sw,'month-heading').all('button').some(b=>b.text==='横画面で見る'));
 assert.equal(visible(saved.nodes.view).split('夜勤後にできなかった希望休').length-1,1);
 const snapshot=saved.get('data');part(sw,'month-heading').all('button')[0].click();assert(saved.nodes['dialog-body'].text.includes('作成時の職員A'));assert(!saved.nodes['dialog-body'].text.includes('現在の別名'));await saved.click('閉じる');assert.deepEqual(saved.get('data'),snapshot);
 const stale=start();stale.eval("data.staff[0].monthlyDaysOff=10;save(true);render()");assert(stale.get('workChanged()'));assert(!part(wrap(stale),'month-operations'));assert(part(wrap(stale),'month-heading').all('button').some(b=>b.text==='横画面で見る'));
 console.log('PASS: 横表示ボタンと操作を表の直前へ・凡例とルールを表の下へ・注意を上に保持・重複整理・印刷/保存表/旧表の保持');
})().catch(e=>{console.error(e);process.exitCode=1;});
