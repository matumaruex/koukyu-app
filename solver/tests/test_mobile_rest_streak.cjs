'use strict';
// 全員共通の3連休上限、旧表保持、例外と手直しの解説、候補比較。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs'),flow=require('../../public/creation-workflow.js');
const raw={schemaVersion:4,savedTables:[],staff:[{id:'a',name:'職員A',type:'full',monthlyDaysOff:9,fixedDaysOff:true,nightShiftType:'all'},{id:'b',name:'職員B',type:'part',monthlyDaysOff:11,nightShiftType:'none',startTime:'09:00',endTime:'17:00'}],schedules:{'2026-10':{requests:{a:[10,11,12,13]},assignments:{},history:{a:Array(5).fill('off')}}}};
const error={code:'rest_streak',staff:'s0',day:12,start:9,end:12,count:1};
(async()=>{
 const h=harness(null,{current:raw});assert.equal(h.get('inputData().p.maxConsecutiveOff'),3);assert(h.get('inputData().signature').startsWith('rules-3.73:'));
 for(const st of h.get('data.staff')){h.ctx.testStaff=st;h.eval('editStaff(testStaff)');assert(!h.nodes['dialog-body'].text.includes('3連休まで'));await h.click('閉じる');}
 // 旧3.72の表は当時の勤務・希望・実績を保持する。
 h.eval("schedule().assignments={a:{'1':'early'},b:{'1':'part'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
 const work=JSON.parse(h.values.get('koukyu_v4_work')),w=work.schedules['2026-10'];delete w.workSnapshot;w.workSignature=w.workSignature.replace(/,"maxConsecutiveOff":3}(?=\|staff:|$)/,'}').replace('rules-3.73:','rules-3.72:');w.meta.signature=w.workSignature;w.meta.optimizationPolicy='quality-first-18';
 const old=harness(null,{current:JSON.parse(h.values.get('koukyu_v4_data')),stored:{koukyu_v4_work:JSON.stringify(work)}});assert(old.get('hasTable()'));assert(old.get('workChanged()'));assert.deepEqual(old.get('schedule().workSnapshot.schedule.requests.a'),[10,11,12,13]);assert.deepEqual(old.get('schedule().workSnapshot.schedule.history.a'),Array(5).fill('off'));assert.equal(old.get('schedule().workSnapshot.schedule.assignments.a[1]'),'early');
 const made=harness(null,{current:raw,response:async()=>({status:'FEASIBLE',seconds:3,assignments:{s0:{'9':'off','10':'off','11':'off','12':'off','13':'off'},s1:{'1':'part'}},ruleExceptions:[error],validationErrors:[error],exceptionCount:0,exceptionsProvenMinimum:true,restStreak:{limit:3,count:1,minimum:1,proven:true,policy:'requested-off-max3-1'},restStreakExceptions:1,search:{done:true},boundaryComplete:true,optimizationPolicy:'quality-first-19'})});
 await made.ctx.generate();assert.equal(made.calls[0].input.maxConsecutiveOff,3);const text=made.nodes.view.text;assert(text.includes('勤務条件の例外：1件'));assert(text.includes('4連休（3日まで・自動配置を含む上限超え1日分）'));assert(text.includes('最少を確認済み'));assert(text.includes('自動で配置する公休は3連休まで。希望休だけの連休は例外'));
 const marked=made.nodes.view.all('td').filter(e=>(e.attributes['aria-label']||'').includes('（例外）'));assert.equal(marked.length,4);assert(marked.every(e=>(e.attributes['aria-label']||'').includes('職員A')));
 const before=made.get('data');made.ctx.openLandscapeTable();assert(made.nodes['dialog-body'].text.includes('勤務条件の例外：1件'));await made.click('閉じる');assert.deepEqual(made.get('data'),before);
 made.eval("data.savedTables.push(RosterStorage.capture(data,key(),'保存表','saved'));testSavedSnapshot(data.savedTables.find(r=>r.id==='saved'))");assert(made.nodes.view.text.includes('4連休（3日まで'));assert(made.nodes.view.text.includes('最少を確認済み'));
 // 手直しした表は最少と断定せず、検査結果の実件数を表示する。
 const edit=harness(null,{current:raw,response:async()=>({status:'INVALID',validationErrors:[error],restStreak:{limit:3,count:1,proven:false,policy:'requested-off-max3-1'},boundaryComplete:true})});edit.eval("schedule().assignments={a:{'9':'off','10':'off','11':'off','12':'off'},b:{'1':'part'}};schedule().workSignature=inputData().signature;");await edit.ctx.validateCurrent();assert.equal(edit.get('schedule().meta.status'),'VALID');assert.equal(edit.get('schedule().meta.restStreakExceptions'),1);assert(edit.nodes.view.text.includes('4連休以上があります。避けられないかは未確認です'));assert(!edit.nodes.view.text.includes('最少を確認済み'));
 assert(edit.ctx.progressText({},{search:{reason:'rest_streak_unconfirmed'}}).includes('まだ不可能とは判定していません'));
 const base={status:'FEASIBLE',assignments:{},allocation:{overtimeTotal:0}};
 assert(flow.compare({...base,restStreakExceptions:0,staffingShortfallTotal:9},{...base,restStreakExceptions:1,staffingShortfallTotal:0})<0);
 assert(flow.compare({...base,isolatedWorkExceptions:0,restStreakExceptions:9},{...base,isolatedWorkExceptions:1,restStreakExceptions:0})<0);
 console.log('PASS: 全員共通3連休上限・旧表の保持・解説/印/横表示/保存・手直しの未確認・比較順');
})().catch(e=>{console.error(e);process.exitCode=1;});
