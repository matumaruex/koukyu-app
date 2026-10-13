'use strict';
// 3.48 エジプト（王墓）の見た目：文字は従来どおりで、強調・印のクラスだけを足す。印刷は従来の配色のまま。
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{harness}=require('./mobile_harness.cjs');
const root=path.join(__dirname,'../../public');
const raw={schemaVersion:4,savedTables:[],staff:[{id:'a',name:'職員A',type:'full',monthlyDaysOff:9,nightShiftType:'all',canOvertime:true},{id:'b',name:'職員B',type:'full',monthlyDaysOff:9,nightShiftType:'all',canOvertime:true}],
 schedules:{'2026-10':{requests:{},assignments:{},history:{}}},preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[0,0,0],maxReducedSundays:0}}};
const every=node=>[node,...node.children.filter(v=>v&&typeof v==='object').flatMap(every)],find=(node,test)=>every(node).filter(test);
(()=>{
 // まとめの数字：文字は従来の1行と同じで、数字を太字の要素に分ける。
 const h=harness(raw);h.eval("schedule().assignments={a:{'1':'night','2':'nightOff','3':'off','4':'overtime'},b:{'1':'off','2':'night','3':'nightOff'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
 const summary=h.eval('allocationSummary()');
 assert(summary.text.includes('夜勤：1〜1回 ／ 差0回'));assert(summary.text.includes('この表の残業：合計1回 ／ 人数超過：'));
 const stats=find(summary,e=>e.className==='stat-line');
 assert.equal(stats.length,2);assert.deepEqual(stats.map(p=>p.children[1].tagName),['B','B']);assert.equal(stats[0].children[1].textContent,'1〜1回');
 // 守れている項目に印のクラス。
 assert(find(h.nodes.view,e=>e.className==='small ok-line').some(p=>p.textContent==='A残の1サイクル1回：守れています'));

 // 希望を入れた日の説明は、希望があるときだけ。印刷では出さない。
 assert(!h.nodes.view.text.includes('金の三角の付いたマスは、希望を入れた日です。'));
 h.eval("schedule().requests={a:[3]};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
 const legend=find(h.nodes.view,e=>e.textContent==='金の三角の付いたマスは、希望を入れた日です。');
 assert(legend.length>=1);assert(legend.every(p=>p.className==='legend screen-only'));

 // 画面と版：読み込みの番号をそろえ、下の4つの画面と設定・期間の部品を残す。
 const html=fs.readFileSync(path.join(root,'index.html'),'utf8'),versions=[...html.matchAll(/\?v=(\d+)/g)].map(m=>m[1]);
 assert(versions.length>=10);assert.equal(new Set(versions).size,1);assert.equal(versions[0],'60');
 assert.deepEqual([...html.matchAll(/data-tab="([^"]+)"/g)].map(m=>m[1]),['schedule','requests','staff','saved']);
 for(const id of ['settings','previous','next','month','period-label','notice','view','toast','dialog','dialog-body','import'])assert(html.includes(`id="${id}"`),id);
 assert(html.includes('<footer>公休表 3.48</footer>'));
 // 暗い配色は画面だけ（@media screen の中）。印刷の規則には入れない。
 const css=fs.readFileSync(path.join(root,'mobile.css'),'utf8'),start=css.indexOf('@media screen{'),theme=css.slice(start);
 assert(start>0);assert(theme.includes('.month-table td.night{background:#0a1430'));
 assert(!css.slice(0,start).includes('#0a1430'));
 for(const block of css.matchAll(/@media print\{([^@]*)\}/g))assert(!block[1].includes('#0f1d3d')&&!block[1].includes('#0a1430'));
 // 象形文字は切り出した書体を自前で配る（外部の読み込みに失敗しても印が四角にならない）。ライセンスを同梱。
 assert(css.includes('src:url(/fonts/egypt-glyphs.woff2)'));assert(fs.statSync(path.join(root,'fonts/egypt-glyphs.woff2')).size<20000);
 assert(fs.readFileSync(path.join(root,'fonts/OFL.txt'),'utf8').includes('SIL Open Font License'));
 console.log('egypt theme ok');
})();
