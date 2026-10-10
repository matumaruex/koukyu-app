(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.OvertimeCycles=api;})(globalThis,function(){
'use strict';
// A残は1回の出勤サイクル（公休・明けで区切った出勤のひと続き、夜勤を含む）に1回まで（3.40）。計算側の overtime_cycles.report と同じ数え方。
// 希望勤務・固定のA残どうしは数えない。計算が入れたA残と同じサイクルになった分を数える。
// fixedOvertime(day) は希望勤務か固定でA残にした日か。history は実際に入力された前期7日（なければ undefined）。
function carry(history){let value=0;for(const k of history||[])value=k==='overtime'?1:k==='off'||k==='nightOff'?0:value;return value;}
function scan(row,days,fixedOvertime,history){const items=[];let seen=carry(history),free=0,start=null,count=0,extra=0;for(let day=1;day<=days+1;day++){const k=day<=days?row?.[day]:'off';if(k==='off'||k==='nightOff'){if(extra)items.push({start,end:day-1,overtime:count,count:extra});seen=0;free=0;start=null;count=0;extra=0;continue;}if(start===null)start=day;if(k!=='overtime')continue;const fixed=!!fixedOvertime(day);extra+=fixed?free:seen;seen=1;count++;if(!fixed)free=1;}return items;}
return {carry,scan};
});
