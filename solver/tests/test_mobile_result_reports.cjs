'use strict';
// 注意事項を集計より先に出し、重複を除いても必要な報告・証明・旧表を保持する。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'a',name:'職員A',type:'full',monthlyDaysOff:9,nightShiftType:'all',canOvertime:true},
 {id:'b',name:'職員B',type:'full',monthlyDaysOff:9,nightShiftType:'all',canOvertime:true}],
 schedules:{'2026-10':{requests:{a:[7]},assignments:{},history:{a:Array(7).fill('off'),b:Array(7).fill('off')}}},
 preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const exception={code:'consecutive',staff:'s0',day:4,actual:4,limit:3,plusOne:false};
const coverage={code:'coverage',day:1,time:420,actual:1,required:2};
const meta={status:'DRAFT',boundaryComplete:true,optimizationPolicy:'quality-first-16',
 unmetConditions:[coverage,Object.fromEntries(Object.entries(exception).reverse())],ruleExceptions:[exception],
 exceptionCount:1,exceptionsProvenMinimum:false,staffingShortfallTotal:1,shortfallProvenMinimum:false,
 nightRestPreferences:{rule:'night-request-gap-1',unmet:[{staff:'s0',day:7}],minimumUnmetProven:false},
 allocation:{overtimeTotal:1,minimumOvertimeProven:false}};
function start(){const h=harness(null,{current:raw});h.ctx.reportMeta=meta;h.eval("schedule().assignments={a:{'1':'early','2':'overtime','7':'off'},b:{'1':'night','2':'nightOff','3':'off'}};schedule().workSignature=inputData().signature;schedule().meta=clone(reportMeta);schedule().meta.signature=inputData().signature;render()");return h;}
const node=(root,cls)=>root.all('section').find(e=>e.className.split(' ').includes(cls));
const visible=root=>root.className==='print-only'?'':root.textContent+root.children.map(c=>typeof c==='object'&&c.children?visible(c):String(c)).join('');
const h=start(),roster=h.nodes.view.all('article').find(e=>e.id==='roster-result');
const attention=node(roster,'result-attention'),summary=node(roster,'result-info');
assert(attention);assert(summary);assert(roster.children.indexOf(attention)<roster.children.indexOf(summary));
assert.equal(attention.children[0].text,'確認すること');
assert(attention.children[1].text.includes('不足あり'));
assert(attention.children[2].text.includes('連勤・連休・夜勤の端数・日勤の種類の例外：1件'));
assert(attention.children[3].text.includes('夜勤後にできなかった希望休：1件（希望休は守っています）'));
assert.equal(attention.text.split('4連勤目').length-1,1);
assert(!attention.children[1].text.includes('連勤'));
assert(attention.children[1].text.includes('人数が不足する時間帯：1か所'));
assert(!attention.text.includes('最少を確認済み'));assert(!attention.text.includes('この件数が最少'));
assert(attention.children.slice(1).every(panel=>panel.children[0].className==='result-report-heading'));
assert(attention.children.every(panel=>panel.tagName!=='DETAILS'));
assert(summary.text.includes('夜勤：0〜1回 ／ 差1回'));
assert(summary.text.includes('この表の残業：合計1回'));
const explanation=summary.all('details').find(e=>e.className==='result-explanation');
assert(explanation);assert(!explanation.open);assert(explanation.text.includes('人数超過は朝・昼・夕'));
assert(!explanation.text.includes('4連勤目'));assert(!explanation.text.includes('夜勤後にできなかった'));

// 表示される例外と同一でないエラーは消さない。古い表の独自情報も保持する。
h.ctx.extra={code:'request',staff:'s1',day:7};h.eval('schedule().meta.unmetConditions.push(extra)');
const shortage=h.eval('shortfallPanel(metadata())');assert(shortage.text.includes('希望休への出勤'));assert(!shortage.text.includes('連勤上限'));
// 最少の証明は、折りたたまれた説明とは別に見える位置へ残す。
h.eval("schedule().meta.exceptionsProvenMinimum=true;schedule().meta.nightRestPreferences.minimumUnmetProven=true;schedule().meta.allocation.minimumOvertimeProven=true;render()");
const proven=node(h.nodes.view,'result-attention');assert(proven.text.includes('最少を確認済み'));assert(proven.text.includes('人数不足を最少にしたうえで、この件数が最少'));
const provenSummary=h.eval('allocationSummary()');assert(provenSummary.text.includes('残業合計が最少'));
assert(!provenSummary.all('details')[0].text.includes('残業合計が最少'));

// 作業中と保存した表で報告をそろえ、保存時の職員名を使う。
const saved=start();saved.eval("data.savedTables.push(RosterStorage.capture(data,key(),'保存した表','saved'));data.staff[0].name='変更後の別名';state.tab='saved';state.archiveId='saved';render()");
const archived=node(saved.nodes.view,'result-attention');assert(archived.text.includes('職員Aさん'));assert(!archived.text.includes('変更後の別名'));
assert(archived.text.includes('夜勤後にできなかった希望休'));assert.equal(archived.text.split('4連勤目').length-1,1);
assert.equal(saved.calls.length,0);

// 問題がない表に注意欄を出さず、編集時の必須違反は要修正として表示する。
const clean=start();clean.eval("schedule().meta={status:'VALID',signature:inputData().signature,boundaryComplete:true};render()");
assert(!node(clean.nodes.view,'result-attention'));assert(node(clean.nodes.view,'result-info'));
clean.eval("schedule().meta={status:'INVALID',signature:inputData().signature,validationErrors:[{code:'request',staff:'s0',day:1}]};render()");
const invalid=node(clean.nodes.view,'result-attention').children[1];assert(invalid.text.includes('要修正'));assert.equal(invalid.attributes.role,'alert');
assert(visible(clean.nodes.view).includes('この表はそのまま使用できません。'));

// 報告を組み立てても入力・勤務・前期・端末保存を変更せず、通信しない。
const stable=start(),before=stable.get('data'),stored=[...stable.values],signature=stable.get('inputData().signature');
stable.eval("appendResultReports(el('div'),{check:true})");
assert.deepEqual(stable.get('data'),before);assert.deepEqual([...stable.values],stored);assert.equal(stable.get('inputData().signature'),signature);assert.equal(stable.calls.length,0);
console.log('PASS: 注意を先に統一表示・不足と例外の重複除去・重要な報告と証明を維持・保存表との統一・入力と表の保持');
