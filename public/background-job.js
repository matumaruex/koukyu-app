(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.BackgroundJob=api;})(globalThis,function(){
'use strict';
const KEY='koukyu_background_job_v1';
function load(){try{const v=JSON.parse(localStorage.getItem(KEY)||'null');return v&&v.version===1&&typeof v.runId==='string'&&typeof v.token==='string'?v:null;}catch(e){return null;}}
function store(job){localStorage.setItem(KEY,JSON.stringify(job));}
function clear(job){const v=load();if(v&&v.runId===job.runId)localStorage.removeItem(KEY);}
function randomToken(){const bytes=new Uint8Array(32);crypto.getRandomValues(bytes);return [...bytes].map(v=>v.toString(16).padStart(2,'0')).join('');}
async function call(payload){const r=await fetch('/api/background',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),cache:'no-store'});let value;try{value=await r.json();}catch(e){throw Error('作成サービスとの通信を確認できません。');}if(!r.ok){const e=Error(value.error||'作成サービスとの通信を確認できません。');e.status=r.status;throw e;}return value;}
async function start(details,identity){const token=randomToken();let response;try{response=await call({action:'start',token,...details});}catch(e){throw Error('作成を開始できたか確認できませんでした。少し待ってからもう一度お試しください。');}if(!response.runId)throw Error('作成の開始を確認できませんでした。');const job={version:1,token,runId:response.runId,...identity,startedAt:Date.now()};try{store(job);}catch(e){call({action:'cancel',token,runId:job.runId}).catch(()=>{});throw Error('作成状況をこの端末に保存できませんでした。端末の保存設定を確認してください。');}return job;}
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function wait(job,{isCurrent=()=>true,onWait=()=>{}}={}){while(isCurrent()){
 try{const r=await call({action:'status',token:job.token,runId:job.runId});if(!isCurrent())return {stale:true};if(r.status==='completed')return r.result;if(r.status==='failed'||r.status==='cancelled')throw Object.assign(Error('作成を完了できませんでした。元の表は残っています。'),{permanent:true});onWait(false);}
 catch(e){if(!isCurrent())return {stale:true};if(e.permanent||e.status===403||e.status===404||e.status===410)throw e;onWait(true);}
 await sleep(4000);
}return {stale:true};}
async function cancel(job){if(!job)return;clear(job);try{for(let i=0;i<6;i++){const r=await call({action:'cancel',token:job.token,runId:job.runId});if(r.status!=='not_ready')return;await sleep(1000);}}catch(e){}}
return {load,clear,start,wait,cancel};
});
