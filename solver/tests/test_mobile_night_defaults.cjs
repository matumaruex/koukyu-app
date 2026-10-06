'use strict';
// 旧オン・オフの保存値に影響されず、希望と対象職員を送ることを確認する。
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../../public/mobile.js'),'utf8');
assert(!source.includes('function nightRestRequestControl'));
assert(!source.includes('function setNightRestRequired'));
assert(!source.includes('この職員の希望休は、できるだけ夜勤後にする'));
const functions=['inputData','metadata','renderRequests'].map(name=>source.split('\n').find(line=>line.startsWith(`function ${name}(`))).join('\n');
const staff=[{id:'a',name:'職員A',type:'full',nightShiftType:'all',monthlyDaysOff:9},
 {id:'b',name:'職員B',type:'full',nightShiftType:'none',monthlyDaysOff:9},
 {id:'c',name:'職員C',type:'part',nightShiftType:'none',monthlyDaysOff:9},
 {id:'d',name:'職員D',type:'full',nightShiftType:'all',monthlyDaysOff:9}];
const saved={assignments:{a:{'6':'off'}},requests:{a:[6],b:[6],c:[6],d:[6]},nightRestRequiredStaff:[],excludedStaff:['d']};
let rendered=[];
const ctx={state:{year:2026,month:3,reqStaff:'a',requestType:'off'},data:{staff,preferences:{maxExtraOffSpread:1,staffing:{requiredStaff:[4,4,4],maxReducedSundays:3}}},
 schedule:()=>saved,history:()=>({}),activeStaff:()=>staff.filter(s=>s.id!=='d'),clone:x=>JSON.parse(JSON.stringify(x)),normalizeStaffing:x=>x,
 card:()=>({append:(...nodes)=>rendered.push(...nodes)}),select:()=>({}),field:(name)=>({field:name}),el:(tag,text)=>({tag,text}),
 requestChoices:()=>[['off','希望休']],staffIncluded:id=>id!=='d',requestStatus:()=>'',requestCount:()=>1,
 requestCalendar:()=>({calendar:true}),button:()=>({button:true}),fairnessExceptionControl:()=>({fairness:true}),banner:()=>({banner:true})};
vm.createContext(ctx);vm.runInContext(functions,ctx);
const first=JSON.parse(JSON.stringify(ctx.inputData()));
assert(!Object.hasOwn(first.p,'nightRestRequiredStaff'));
assert.equal(first.p.staff.length,3);
assert.deepEqual(Object.values(first.map),['a','b','c']);
assert.deepEqual(first.p.requests.s0,[6]);
saved.nightRestRequiredStaff=['a'];
assert.equal(ctx.inputData().signature,first.signature);
assert(first.signature.startsWith('rules-3.22:'));
saved.meta={status:'OPTIMAL',signature:first.signature.replace('rules-3.22:','rules-3.12:')};
assert.equal(ctx.metadata(),null);
ctx.renderRequests({append:()=>{}});
assert.deepEqual(rendered.filter(n=>n.field).map(n=>n.field),['職員を選ぶ','入力する希望']);
assert.deepEqual(saved.requests.a,[6]);
assert.deepEqual(saved.assignments.a,{'6':'off'});
console.log('PASS: チェック項目を削除し、旧設定に関係なく同じ条件を送信。希望・表・対象職員を保持');
