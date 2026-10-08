'use strict';
// 実際の画面コードを動かし、保存領域・操作・通信の境界を検査する。
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element{
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.textContent='';this.attributes={};this.dataset={};this.value='';this.style={};this.classList={add(){},remove(){}};}
 append(...values){for(const v of values)this.children.push(v);}
 prepend(...values){this.children.unshift(...values);}
 replaceChildren(...values){this.children=values;}
 setAttribute(k,v){this.attributes[k]=String(v);}
 removeAttribute(k){delete this.attributes[k];}
 addEventListener(){} focus(){} scrollIntoView(){} click(){return this.onclick?.({preventDefault(){}});}
 showModal(){this.open=true;} close(){this.open=false;}
 get lastChild(){return this.children.at(-1);}
 get text(){return this.textContent+this.children.map(v=>v instanceof Element?v.text:String(v)).join('');}
 all(tag){return [...(this.tagName===tag.toUpperCase()?[this]:[]),...this.children.flatMap(v=>v instanceof Element?v.all(tag):[])];}
}
function harness(raw,options={}){
 class Clock extends Date{constructor(...args){super(...(args.length?args:[new Date(2026,9,6,12).getTime()]));}}
 const values=new Map(raw?[['koukyu_v3_data',JSON.stringify(raw)]]:[]),nodes={},all=[],period=new Element(),calls=[],confirmations=[],timers=[];
 if(options.current){values.clear();values.set('koukyu_v4_data',JSON.stringify(options.current));}
 // 作業中の表など、ほかの保存キーを読み込み前に置く。
 for(const[k,v]of Object.entries(options.stored||{}))values.set(k,v);
 const nav=['schedule','auto','requests','staff','saved'].map(tab=>{const e=new Element('button');e.dataset.tab=tab;return e;});
 const ctx={console,Date:Clock,Math,JSON,Set,Map,AbortController,File,URL,crypto:require('node:crypto').webcrypto,
  navigator:{storage:{persist:async()=>true}},window:{print(){}},confirm:message=>{confirmations.push(message);return true;},
  document:{getElementById:id=>nodes[id]??=new Element(),createElement:tag=>{const e=new Element(tag);all.push(e);return e;},querySelector:()=>period,querySelectorAll:selector=>selector==='[data-tab]'?nav:all.filter(e=>['BUTTON','INPUT','SELECT'].includes(e.tagName))},
  localStorage:{getItem:k=>values.get(k)??null,setItem:(k,v)=>{if(options.quota)throw Error('Quota');values.set(k,v);}},
  setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout(){},setInterval:()=>1,clearInterval(){},
  fetch:async(url,opts)=>{const body=JSON.parse(opts.body);calls.push(body);const response=options.response?await options.response(body):{status:'UNKNOWN'};return {ok:true,json:async()=>response};}};
 vm.createContext(ctx);
 const root=path.join(__dirname,'../../public');
 vm.runInContext(fs.readFileSync(path.join(root,'auto-holiday-policy.js'),'utf8'),ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'roster-storage.js'),'utf8'),ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'creation-workflow.js'),'utf8'),ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'auto-creation-workflow.js'),'utf8'),ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'auto-roster-ui.js'),'utf8'),ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'mobile.js'),'utf8'),ctx);
 return {ctx,values,nodes,calls,confirmations,timers,eval:s=>vm.runInContext(s,ctx),get:s=>JSON.parse(vm.runInContext('JSON.stringify('+s+')',ctx)),click:async(name,where='dialog-body')=>{const button=nodes[where].all('button').find(e=>e.text===name);if(!button)throw Error('Missing button '+name+' in '+nodes[where].text);await button.click();}};
}
module.exports={harness,Element};
