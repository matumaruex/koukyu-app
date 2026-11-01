'use strict';
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const staff=[{id:'a',name:'職員A',type:'full',nightShiftType:'none',monthlyDaysOff:9}],schedule={requests:{},assignments:{a:{'1':'off'}}};
const saved=(id,mode)=>({id,name:id,period:'2026-10',createdAt:'2026-10-01T00:00:00Z',staff,preferences:{},schedule,...(mode?{creationMode:mode}:{})});
const raw={schemaVersion:4,staff,schedules:{},savedTables:[saved('normal'),saved('retired','auto')]};
const h=harness(null,{current:raw});assert.equal(h.get('state.loadError'),false);assert.deepEqual(h.get('data.savedTables.map(x=>x.id)'),['normal']);h.ctx.settings();assert(!h.nodes['dialog-body'].text.includes('公休おまかせを開く'));h.ctx.save(true);assert.deepEqual(JSON.parse(h.values.get('koukyu_v4_data')).savedTables.map(x=>x.id),['normal']);console.log('PASS: 通常保存表を保持し、おまかせの入口と保存表を除く');
