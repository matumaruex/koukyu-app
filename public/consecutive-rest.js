(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.ConsecutiveRest=api;})(globalThis,function(){
'use strict';
// 前期や翌期をつながず、今期内にある2日以上の公休のまとまりを数える。
function ranges(row,days){const result=[];let start=null;for(let day=1;day<=days+1;day++){if(day<=days&&row?.[day]==='off'){if(start===null)start=day;}else if(start!==null){if(day-start>=2)result.push({start,end:day-1});start=null;}}return result;}
function check(value){if(value===undefined)return 0;if(!Number.isInteger(value)||value<0||value>2)throw Error('連休の必須回数は指定なし・1回・2回から選んでください。');return value;}
return {ranges,check};
});
