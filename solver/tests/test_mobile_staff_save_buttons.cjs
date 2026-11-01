'use strict';
// 上下どちらも同じフォームで保存し、エラーも両方から見える。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={schemaVersion:4,savedTables:[],staff:[{id:'a',name:'変更前',type:'full',monthlyDaysOff:9,nightShiftType:'all'}],schedules:{'2026-10':{requests:{a:[3]},assignments:{},history:{a:Array(7).fill('off')}}}};
for(const position of [0,1]){
 const h=harness(null,{current:raw});h.eval('editStaff(data.staff[0])');
 const form=h.nodes['dialog-body'].all('form')[0],buttons=form.all('button').filter(b=>b.textContent==='保存する');
 assert.equal(buttons.length,2);assert(buttons.every(b=>b.type==='submit'));
 assert.equal(form.children[0],buttons[0]);assert.equal(form.children.at(-1),buttons[1]);
 const name=form.all('input')[0],errors=form.all('p').filter(p=>p.attributes.role==='alert');assert.equal(errors.length,2);
 name.value='  ';form.onsubmit({preventDefault(){},submitter:buttons[position]});
 assert(errors.every(e=>e.textContent==='名前を入力してください。'));assert.equal(h.get('data.staff[0].name'),'変更前');
 name.value='変更後';form.onsubmit({preventDefault(){},submitter:buttons[position]});
 assert.equal(h.get('data.staff[0].name'),'変更後');assert.equal(JSON.parse(h.values.get('koukyu_v4_data')).staff[0].name,'変更後');
 assert.deepEqual(h.get("data.schedules['2026-10'].history.a"),Array(7).fill('off'));
}
const failed=harness(null,{current:raw,quota:true});failed.eval('editStaff(data.staff[0])');
const form=failed.nodes['dialog-body'].all('form')[0],errs=form.all('p').filter(p=>p.attributes.role==='alert');
form.all('input')[0].value='保存失敗';form.onsubmit({preventDefault(){}});
assert(errs.every(e=>e.textContent.includes('保存')));assert.equal(failed.get('data.staff[0].name'),'変更前');
console.log('PASS: 上下の保存、同じ検査、両方のエラー表示、保存失敗と前期保持');
