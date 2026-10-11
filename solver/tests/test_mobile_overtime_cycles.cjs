'use strict';
// A残の1サイクル1回（3.40）：数え方、通常版だけの送信、集計の表示、候補の比較、3.39までの作業表の保持。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const cycles=require('../../public/overtime-cycles.js'),flow=require('../../public/creation-workflow.js');
const raw={schemaVersion:4,savedTables:[],staff:[{id:'a',name:'職員A',type:'full',monthlyDaysOff:9,nightShiftType:'all',canOvertime:true},{id:'b',name:'職員B',type:'full',monthlyDaysOff:9,nightShiftType:'all',canOvertime:true}],
 schedules:{'2026-10':{requests:{},assignments:{},history:{}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
(async()=>{
 // 数え方：公休・明けで区切り、夜勤は同じサイクル。希望・固定のA残も数える。前期は入力された実績だけつなげる。
 const none=()=>false;
 assert.deepEqual(cycles.scan({'1':'overtime','2':'early','3':'overtime','4':'off'},31,none),[{start:1,end:3,overtime:2,count:1,wishOnly:false}]);
 assert.deepEqual(cycles.scan({'1':'overtime','2':'off','3':'overtime'},31,none),[]);
 assert.deepEqual(cycles.scan({'1':'overtime','2':'night','3':'nightOff','4':'off','5':'overtime'},31,none),[]);
 assert.deepEqual(cycles.scan({'1':'overtime','3':'overtime','5':'overtime','6':'off'},31,none),[{start:1,end:5,overtime:3,count:2,wishOnly:false}]);
 assert.deepEqual(cycles.scan({'1':'overtime','3':'overtime','4':'off'},31,d=>d===1||d===3),[{start:1,end:3,overtime:2,count:1,wishOnly:true}]);
 assert.deepEqual(cycles.scan({'1':'overtime','3':'overtime','5':'overtime','6':'off'},31,d=>d===1||d===3).map(c=>[c.count,c.wishOnly]),[[2,false]]);
 assert.deepEqual(cycles.scan({'2':'overtime','3':'off'},31,none,['off','off','off','off','off','overtime','early']).map(c=>c.count),[1]);
 assert.deepEqual(cycles.scan({'2':'overtime','3':'off'},31,none,['off','off','off','off','overtime','off','early']),[]);

 // 通常版は常に送る。おまかせには送らない。
 const h=harness(null,{current:raw});
 assert.equal(h.get('inputData().p.overtimeCycleLimit'),true);assert(h.get('inputData().signature').startsWith('rules-3.45:'));
 h.eval("setTab('auto')");assert.equal(h.eval('inputData().p.overtimeCycleLimit'),undefined);

 // 作成結果：2回目のサイクルと理由。
 const rows={s0:{'1':'overtime','2':'early','3':'overtime','4':'off'},s1:{'1':'night','2':'nightOff','3':'off'}};
 const made=harness(raw,{response:async()=>({status:'FEASIBLE',assignments:rows,seconds:3,overtimeCycleExcess:1,overtimeCycles:{excess:1,items:[{staff:'s0',start:1,end:3,overtime:2,count:1}],minimumProven:true},allocation:{overtimeTotal:2,nightSpread:0},search:{done:true},boundaryComplete:true,optimizationPolicy:'quality-first-10'})});
 await made.ctx.generate();
 assert.equal(made.calls[0].input.overtimeCycleLimit,true);
 assert(made.nodes.view.text.includes('A残の1サイクル1回：2回目が1件（職員Aさん 10/16〜10/18） ・ 人数不足を減らすため'));
 // 手直しで作った2回目は理由を付けない。守れている表はそのまま表示。
 made.eval("schedule().assignments.a['6']='overtime';schedule().assignments.a['7']='early';schedule().assignments.a['8']='overtime';render()");
 assert(made.nodes.view.text.includes('A残の1サイクル1回：2回目が2件'));assert(!made.nodes.view.text.includes('2回目が2件（職員Aさん 10/16〜10/18、職員Aさん 10/20〜10/23） ・ 人数不足'));
 // 希望で入れたA残だけのサイクルは「希望・固定どおり」。人数不足の理由は付けない。
 const wish=harness(raw);wish.eval("schedule().shiftRequests={a:{'1':'overtime','3':'overtime'}};schedule().assignments={a:{'1':'overtime','2':'early','3':'overtime','4':'off'},b:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature,overtimeCycleExcess:1};render()");
 assert(wish.nodes.view.text.includes('A残の1サイクル1回：2回目が1件（職員Aさん 10/16〜10/18（希望・固定どおり））'));assert(!wish.nodes.view.text.includes('人数不足を減らすため'));
 const ok=harness(raw);ok.eval("schedule().assignments={a:{'1':'overtime','2':'off','3':'overtime'},b:{'1':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
 assert(ok.nodes.view.text.includes('A残の1サイクル1回：守れています'));

 // 候補の比較：人数不足 → A残の1サイクル1回 → 夜勤後の希望休・残業合計。
 const base={status:'FEASIBLE',assignments:{},allocation:{overtimeTotal:9}};
 assert(flow.compare({...base,staffingShortfallTotal:0,overtimeCycleExcess:2},{...base,staffingShortfallTotal:1,overtimeCycleExcess:0})<0);
 assert(flow.compare({...base,overtimeCycleExcess:0,nightRestPreferences:{unmet:[1,2]},allocation:{overtimeTotal:12}},{...base,overtimeCycleExcess:1})<0);

 // 3.39までに作った作業表（一時保存に作成時の条件がないもの）も、当時の条件を記録して保持する。
 const old=harness(null,{current:raw});old.eval("setTab('schedule');schedule().assignments={a:{'1':'early'},b:{'1':'off'}};schedule().workSignature=inputData().signature;render()");
 const work=JSON.parse(old.values.get('koukyu_v4_work')),w=work.schedules['2026-10'];
 w.workSignature=w.workSignature.replace('rules-3.45:','rules-3.35:').replace(',"overtimeCycleLimit":true}','}');delete w.workSnapshot;
 const reopened=harness(null,{current:raw,stored:{koukyu_v4_work:JSON.stringify(work)}});reopened.eval("setTab('schedule')");
 assert(reopened.get('hasTable()'));assert(reopened.get('workChanged()'));assert(reopened.get('Boolean(schedule().workSnapshot)'));
 assert.deepEqual(reopened.get('schedule().assignments'),w.assignments);
 assert(reopened.nodes.view.text.includes('最新の条件とは異なる条件で作成した表です。'));
 console.log('PASS: A残の1サイクル1回の数え方（明け・夜勤・希望と固定も数える・前期）、通常版だけの送信、2回目と理由・希望どおりの表示、候補の比較、3.39までの作業表の保持');
})().catch(e=>{console.error(e);process.exitCode=1;});
