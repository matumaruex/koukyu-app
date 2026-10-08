'use strict';
const assert=require('node:assert/strict'),flow=require('../../public/auto-creation-workflow.js');
const policy={a:{min:9,target:10,max:10,fixed:false}};
const result=(overtime=21)=>({status:'FEASIBLE',assignments:{a:{'1':'off'}},allocation:{overtimeTotal:overtime,overtimeBalance:1,overtimeProportional:false,nightSpread:1,surplusTotal:0,commonExtraDaysOff:0,minor:0},nightRestPreferences:{unmet:[]},overtimeFairness:{minimumSpreadProven:true},selectedQuota:{a:10},search:{done:true},seconds:60});
(async()=>{
 let seed=0,calls=[];const run=request=>flow.run({input:{},holidayPolicy:policy,request:async p=>{calls.push(p);return request(p);},nextSeed:()=>++seed});
 const base=result();let r=await run(p=>p.autoPhase==='base'?base:{...base,autoDone:true,autoChanged:false,autoReason:'quality_preserved',autoDetails:{daysProven:true},comparisonQuality:flow.quality(base),seconds:1});assert.equal(r.best.allocation.overtimeTotal,21);assert.equal(calls.length,2);assert.deepEqual(calls.map(p=>p.autoPhase),['base','adjust']);assert(!calls.some(p=>p.autoPhase==='finish'));
 calls=[];r=await run(p=>p.autoPhase==='base'?base:{...result(22),autoDone:true,autoChanged:true,comparisonQuality:flow.quality(result(22)),seconds:1});assert.equal(r.best.allocation.overtimeTotal,21);
 calls=[];r=await run(p=>p.autoPhase==='base'?base:p.autoPhase==='adjust'?{...base,selectedQuota:{a:9},staffingShortfallTotal:0,autoDone:true,autoChanged:true,autoDetails:{necessityProven:true},seconds:1}:{...base,selectedQuota:{a:9},seconds:1});assert.deepEqual(calls.map(p=>p.autoPhase),['base','adjust']);assert.equal(r.best.selectedQuota.a,10);
 // 勤務は同じでも、採用した最低公休が変われば、その条件で仕上げを行う。
 calls=[];r=await flow.run({input:{},holidayPolicy:{a:{min:10,target:10,max:11,fixed:false}},nextSeed:()=>++seed,request:async p=>{calls.push(p);return p.autoPhase==='base'?base:p.autoPhase==='adjust'?{...base,selectedQuota:{a:11},autoDone:true,autoChanged:true,comparisonQuality:flow.quality(base),autoDetails:{qualityPreserved:true},seconds:1}:{...base,selectedQuota:{a:11},seconds:1};}});assert.deepEqual(calls.map(p=>p.autoPhase),['base','adjust','finish']);assert.equal(r.best.selectedQuota.a,11);
 calls=[];r=await run(p=>{if(p.autoPhase==='base')return base;throw Error('通信失敗');});assert.equal(r.best.allocation.overtimeTotal,21);assert(r.error);assert.equal(r.best.autoReason,'days_unconfirmed');
 calls=[];r=await run(p=>p.autoPhase==='base'?{...base,seconds:60,search:{continueRecommended:true,resume:{stage:'placement',idle:0,proven:{}}}}:{status:'UNKNOWN',seconds:60});assert.equal(r.seconds,420);assert.equal(calls.filter(p=>p.autoPhase==='base').length,5);assert.equal(calls.filter(p=>p.autoPhase==='adjust').length,2);assert(calls.every(p=>p.seconds<=60));assert.equal(r.best.allocation.overtimeTotal,21);assert.equal(r.best.autoReason,'days_unconfirmed');
 let current=true;const stale=await flow.run({input:{},holidayPolicy:policy,nextSeed:()=>1,isCurrent:()=>current,request:async()=>{current=false;return base;}});assert(stale.stale);
 console.log('PASS: 基準300秒・検討120秒・合計480秒以内、1通信60秒、日数不変の再作成省略、悪化/通信失敗/古い応答で最良候補を保持');
})().catch(e=>{console.error(e);process.exit(1);});
