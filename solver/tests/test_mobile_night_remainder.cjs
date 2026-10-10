'use strict';
// 夜勤の端数優先（3.39）：職員設定→送信、夜勤の集計表示、例外の一覧、手直しの判定、候補の比較。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const flow=require('../../public/creation-workflow.js');
const raw={schemaVersion:4,savedTables:[],staff:[{id:'a',name:'職員A',type:'full',monthlyDaysOff:9,nightShiftType:'all'},{id:'b',name:'職員B',type:'full',monthlyDaysOff:9,nightShiftType:'all'},{id:'c',name:'職員C',type:'full',monthlyDaysOff:9,nightShiftType:'none'}],
 schedules:{'2026-10':{requests:{},assignments:{},history:{}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const box=(h,text)=>h.nodes['dialog-body'].all('label').find(l=>l.text.includes(text));
(async()=>{
 // 職員設定：夜勤できる人だけにチェックを出し、保存すると通常版で送る。未指定なら送信内容も署名も今までどおり。
 const h=harness(null,{current:raw});
 const before=h.get('inputData().signature');
 h.eval("setTab('staff');editStaff(data.staff[0])");
 const label=box(h,'多いほうの回数を優先');assert(label);assert.equal(label.hidden,false);
 label.children[0].checked=true;h.nodes['dialog-body'].all('form')[0].onsubmit({preventDefault(){}});
 assert.equal(h.get('data.staff[0].nightRemainderPriority'),true);
 h.eval("setTab('schedule')");
 assert.equal(h.get('inputData().p.staff[0].nightRemainderPriority'),true);assert.notEqual(h.get('inputData().signature'),before);
 assert(h.get('inputData().signature').startsWith('rules-3.35:'));
 h.eval("editStaff(data.staff[2])");assert.equal(box(h,'多いほうの回数を優先').hidden,true);
 h.eval("editStaff(data.staff[0])");const night=h.nodes['dialog-body'].all('select').find(s=>s.children.some(o=>o.text==='いつでも可'));
 night.value='none';night.onchange();assert.equal(box(h,'多いほうの回数を優先').hidden,true);
 h.nodes['dialog-body'].all('form')[0].onsubmit({preventDefault(){}});assert.equal(h.get('data.staff[0].nightRemainderPriority'),false);
 assert.throws(()=>h.ctx.checkBackup({staff:[{...raw.staff[0],nightRemainderPriority:'yes'}],schedules:{}}));

 // おまかせには送らない。
 const auto=harness(null,{current:{...raw,staff:[{...raw.staff[0],nightRemainderPriority:true},raw.staff[1],raw.staff[2]]}});
 auto.eval("setTab('auto')");assert.equal(auto.eval('inputData().p.staff[0].nightRemainderPriority'),undefined);

 // 作成結果：夜勤の集計に優先の人の回数、例外の一覧に目安を超えた人。
 const prio={...raw,staff:[{...raw.staff[0],nightRemainderPriority:true},raw.staff[1],raw.staff[2]]};
 const err={code:'night_remainder',staff:'s1',actual:16,fair:15,count:1,priority:false,exceptions:1};
 const rows={s0:Object.fromEntries(Array.from({length:15},(_,i)=>[String(i*2+1),'night'])),s1:Object.fromEntries(Array.from({length:16},(_,i)=>[String(i*2+(i<15?2:1)),'night'])),s2:{'1':'off'}};
 const made=harness(prio,{response:async()=>({status:'FEASIBLE',assignments:rows,seconds:3,ruleExceptions:[err],exceptionCount:0,nightRemainderExceptions:1,nightRemainder:{priorityStaff:['s0'],base:15,extras:1,exceptions:1,proven:true},validationErrors:[err],allocation:{overtimeTotal:0,nightSpread:1},search:{done:true},boundaryComplete:true,optimizationPolicy:'quality-first-8'})});
 await made.ctx.generate();
 assert.equal(made.calls[0].input.staff[0].nightRemainderPriority,true);
 const text=made.nodes.view.text;
 assert(text.includes('夜勤の端数を優先：職員Aさん15回'));
 assert(text.includes('連勤・連休・夜勤の端数・日勤の種類の例外：1件'));assert(text.includes('最少を確認済み'));
 assert(text.includes('職員Bさん：夜勤16回（端数を優先する人ではないため目安は15回）'));

 // 手直しで端数がほかの人へ行った場合は、条件違反ではなく例外として表を保つ。
 const edit=harness(prio,{response:async()=>({status:'INVALID',validationErrors:[err],boundaryComplete:true})});
 edit.eval("schedule().assignments={a:{'1':'night'},b:{'1':'off'},c:{'1':'off'}};schedule().workSignature=inputData().signature;");await edit.ctx.validateCurrent();
 assert.equal(edit.get('schedule().meta.status'),'VALID');

 // 候補の比較：連休なし→連勤など→夜勤の端数の順。
 const base={status:'FEASIBLE',assignments:{},allocation:{overtimeTotal:9}};
 assert(flow.compare({...base,nightRemainderExceptions:0,staffingShortfallTotal:3},{...base,nightRemainderExceptions:1,staffingShortfallTotal:0})<0);
 assert(flow.compare({...base,exceptionCount:0,nightRemainderExceptions:2},{...base,exceptionCount:1,nightRemainderExceptions:0})<0);
 console.log('PASS: 夜勤の端数優先の設定と表示条件・通常版だけの送信・署名の互換、集計と例外の表示、手直しの判定、候補の比較');
})().catch(e=>{console.error(e);process.exitCode=1;});
