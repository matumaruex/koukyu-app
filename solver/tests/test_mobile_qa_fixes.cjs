'use strict';
// 3.47 QAで見つかった表示の修正：作り直す前との比較、読み込めないファイルの案内、中間ルールの説明、説明文の重複。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={schemaVersion:4,savedTables:[],staff:[{id:'a',name:'職員A',type:'full',monthlyDaysOff:9,nightShiftType:'all',canOvertime:true}],schedules:{'2026-10':{requests:{},assignments:{},history:{}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const rows={s0:{'1':'overtime','2':'off'}};
const reply=(ot,before,done)=>({status:'FEASIBLE',assignments:rows,seconds:60,allocation:{overtimeTotal:ot,nightSpread:0,before:{overtimeTotal:before},overtimeReducedBy:before-ot},search:{done,continueRecommended:!done,resume:done?null:{stage:'overtime',idle:1,proven:{}}},boundaryComplete:true,optimizationPolicy:'quality-first-10'});
const said=h=>h.nodes.view.text.match(/作り直す前[^。]*。/)?.[0];
(async()=>{
 // さらに改善する：押す前の表（A残3回）と比べる。途中の通信の表とは比べない。
 let n=0;const improve=harness(raw,{response:async()=>(++n===1?reply(1,3,false):reply(1,1,true))});
 improve.eval("schedule().assignments={a:{'1':'overtime','3':'overtime','5':'overtime','2':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'FEASIBLE',signature:inputData().signature,allocation:{overtimeTotal:3,nightSpread:0}};render()");
 await improve.ctx.generate('improve');
 assert.equal(improve.calls.length,2);assert.equal(said(improve),'作り直す前より残業が2回減りました。');
 // 新しく作る：作り直す前の表はないので比較を出さない（自動の続き計算でも）。
 n=0;const fresh=harness(raw,{response:async()=>(++n===1?reply(2,2,false):reply(1,2,true))});
 await fresh.ctx.generate();
 assert.equal(fresh.calls.length,2);assert.equal(said(fresh),undefined);
 // 読み込めないファイルは日本語で案内する。
 const bad=harness(raw);
 await bad.ctx.document.getElementById('import').onchange({target:{files:[{size:8,text:async()=>'not json'}],value:'x'}});
 assert.equal(bad.nodes.notice.textContent,'ファイルを読み取れませんでした。公休表のバックアップ（.json）を選んでください。');
 // 作れないときの説明に、今の中間ルールをすべて書く。
 const impossible=harness(raw,{response:async()=>({status:'INFEASIBLE',seconds:.1,diagnosis:{status:'EXPLAINED',proven:true,missingNights:[3],droppedWishes:[]}})});
 await impossible.ctx.generate();
 assert(impossible.nodes.view.text.includes('連勤上限・日勤の種類（許可した人）・連休なし・夜勤の端数・連休の回数の差は、守ると作れないときだけ最小限破って表に表示します。'));
 // 希望休の夜勤後配置の説明は、表がないときは作成の欄、表があるときは表の下に1回だけ。
 // 画面に見える部分だけ数える（印刷用に隠している表の写しは除く）。
 const visible=e=>e.className==='print-only'?'':e.textContent+e.children.map(c=>typeof c==='object'&&c.children?visible(c):String(c)).join('');
 const count=h=>visible(h.nodes.view).split('希望休の初日は、夜勤→明け→希望休').length-1;
 const empty=harness(raw);empty.eval('render()');assert.equal(count(empty),1);
 const table=harness(raw);table.eval("schedule().assignments={a:{'1':'early','2':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature,allocation:{overtimeTotal:0,nightSpread:0}};render()");
 assert.equal(count(table),1);
 console.log('PASS: 作り直す前との比較（押す前の表が基準・新規では出さない）、読み込めないファイルの案内、中間ルールの説明、説明文を1回だけ');
})().catch(e=>{console.error(e);process.exitCode=1;});
