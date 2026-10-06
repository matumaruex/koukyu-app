'use strict';
// 中間ルール（連勤・日勤の種類）の設定、送信内容、例外の表示、手直し後の判定を確認する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const staff=[{id:'a',name:'職員A',type:'full',nightShiftType:'all',monthlyDaysOff:9,canOvertime:true},{id:'b',name:'職員B',type:'full',nightShiftType:'all',monthlyDaysOff:9}];
const raw={staff,schedules:{'2026-10':{assignments:{},requests:{}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const label=(h,text)=>h.nodes['dialog-body'].all('label').find(l=>l.text.includes(text));
(async()=>{
 // Aのみ・Bのみの人だけに「逆の日勤も可」を出し、保存すると計算に送る。
 const h=harness(raw);h.eval('editStaff(data.staff[0])');
 const flex=label(h,'逆の日勤');assert.equal(flex.hidden,true);
 const dayType=h.nodes['dialog-body'].all('select').find(s=>s.children.some(o=>o.value==='early'&&o.textContent.includes('Aのみ')));
 dayType.value='early';dayType.onchange();assert.equal(flex.hidden,false);
 flex.children[0].checked=true;h.nodes['dialog-body'].all('form')[0].onsubmit({preventDefault(){}});
 assert.equal(h.get('data.staff[0].dayShiftFlexible'),true);assert.equal(h.get('data.staff[0].dayShiftType'),'early');
 assert.equal(h.get('inputData().p.staff[0].dayShiftFlexible'),true);assert.equal(h.eval('inputData().p.staff[1].dayShiftFlexible'),undefined);
 // 両方できる人に戻すと、設定は送らない。
 h.eval('editStaff(data.staff[0])');const back=h.nodes['dialog-body'].all('select').find(s=>s.children.some(o=>o.value==='early'&&o.textContent.includes('Aのみ')));
 back.value='both';back.onchange();h.nodes['dialog-body'].all('form')[0].onsubmit({preventDefault(){}});assert.equal(h.get('data.staff[0].dayShiftFlexible'),false);
 assert.throws(()=>h.ctx.checkBackup({staff:[{...staff[0],dayShiftFlexible:'yes'}],schedules:{}}));

 // 作成結果の例外は一覧と点線枠で示す。
 const consecutive={code:'consecutive',staff:'s0',day:4,actual:4,limit:3,plusOne:false};
 const made=harness(raw,{response:async()=>({status:'FEASIBLE',assignments:{s0:{'1':'early','2':'early','3':'early','4':'early'},s1:{'1':'off'}},seconds:3,ruleExceptions:[consecutive],exceptionCount:1,exceptionsProvenMinimum:true,validationErrors:[consecutive],allocation:{overtimeTotal:0,nightSpread:0},search:{done:true},boundaryComplete:true,optimizationPolicy:'quality-first-2'})});
 await made.ctx.generate();
 assert(made.nodes.view.text.includes('連勤・日勤の種類の例外：1件'));
 assert(made.nodes.view.text.includes('職員Aさん 10月19日（月）：4連勤目（上限3日）'));
 assert(made.nodes.view.text.includes('最少を確認済み'));assert(made.nodes.view.text.includes('点線枠のマス'));
 const marked=made.nodes.view.all('td').filter(td=>(td.attributes['aria-label']||'').includes('（例外）'));
 assert.equal(marked.length,1);assert(marked[0].attributes['aria-label'].startsWith('職員A 10月19日'));

 // 手直し後の確認：例外だけなら表として使え、人数不足もあれば不足あり、それ以外は条件違反。
 const check=async errors=>{const v=harness(raw,{response:async()=>({status:'INVALID',validationErrors:errors,boundaryComplete:true})});
  v.eval("schedule().assignments={a:{'1':'early'},b:{'1':'off'}};schedule().workSignature=inputData().signature;");await v.ctx.validateCurrent();return v;};
 let v=await check([consecutive]);assert.equal(v.get('schedule().meta.status'),'VALID');assert.equal(v.get('schedule().meta.ruleExceptions.length'),1);assert.equal(v.get('ready()'),true);
 v=await check([consecutive,{code:'coverage',day:1,time:420,actual:1,required:2}]);assert.equal(v.get('schedule().meta.status'),'DRAFT');assert.equal(v.get('schedule().meta.ruleExceptions.length'),1);
 v=await check([{code:'request',staff:'s0',day:1}]);assert.equal(v.get('schedule().meta.status'),'INVALID');
 v=await check([{code:'day_shift_eligibility',staff:'s0',day:1,allowed:'early',actual:'late'}]);assert.equal(v.get('schedule().meta.status'),'INVALID');
 v=await check([{code:'night_coverage',day:1,actual:0,required:1}]);assert.equal(v.get('schedule().meta.status'),'INVALID');
 const flexRaw={...raw,staff:[{...staff[0],dayShiftType:'early',dayShiftFlexible:true},staff[1]]};
 const f=harness(flexRaw,{response:async()=>({status:'INVALID',validationErrors:[{code:'day_shift_eligibility',staff:'s0',day:1,allowed:'early',actual:'late'}],boundaryComplete:true})});
 f.eval("schedule().assignments={a:{'1':'late'},b:{'1':'off'}};schedule().workSignature=inputData().signature;");await f.ctx.validateCurrent();
 assert.equal(f.get('schedule().meta.status'),'VALID');assert(f.nodes.view.text.includes('Aのみ（早出）の設定ですが「B（遅出）」'));
 console.log('PASS: 逆の日勤の設定と送信、例外の一覧・点線枠・最少表示、手直し後の例外/不足/違反の判定、夜勤0人は違反');
})().catch(e=>{console.error(e);process.exitCode=1;});
