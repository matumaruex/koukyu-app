(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.OvertimeCycles=api;})(globalThis,function(){
'use strict';
// A残は1回の出勤サイクル（公休・明けで区切った出勤のひと続き、夜勤を含む）に1回まで（3.40）。計算側の overtime_cycles.report と同じ数え方。
// 希望勤務・固定のA残も数える。wishOnly はそのサイクルの今期のA残がすべて希望・固定（計算が入れたA残がない）。
// fixedOvertime(day) は希望勤務か固定でA残にした日か。history は実際に入力された前期7日（なければ undefined）。
function carry(history){let value=0;for(const k of history||[])value=k==='overtime'?1:k==='off'||k==='nightOff'?0:value;return value;}
function scan(row,days,fixedOvertime,history){const items=[];let seen=carry(history),start=null,count=0,extra=0,computed=0;for(let day=1;day<=days+1;day++){const k=day<=days?row?.[day]:'off';if(k==='off'||k==='nightOff'){if(extra)items.push({start,end:day-1,overtime:count,count:extra,wishOnly:!computed});seen=0;start=null;count=0;extra=0;computed=0;continue;}if(start===null)start=day;if(k!=='overtime')continue;extra+=seen;seen=1;count++;if(!fixedOvertime(day))computed++;}return items;}
return {carry,scan};
});
