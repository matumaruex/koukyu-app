(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.ConsecutiveRest=api;})(globalThis,function(){
'use strict';
// 前期や翌期をつながず、今期内にある2日以上の公休のまとまりを数える。
function ranges(row,days){const result=[];let start=null;for(let day=1;day<=days+1;day++){if(day<=days&&row?.[day]==='off'){if(start===null)start=day;}else if(start!==null){if(day-start>=2)result.push({start,end:day-1});start=null;}}return result;}
function check(value){if(value===undefined)return 0;if(!Number.isInteger(value)||value<0||value>2)throw Error('連休の必須回数は指定なし・1回・2回から選んでください。');return value;}
function checkNone(value,min){if(value===undefined)return false;if(typeof value!=='boolean')throw Error('連休なしの設定を確認してください。');if(value&&min)throw Error('連休なしと連休の必須回数は同時に選べません。');return value;}
// 連休なしの人：前日と当日がともに公休で、両日とも希望休・固定の公休・前期の実績ではない組を、ひと続きごとにまとめる（計算側の rest_blocks.forbidden_ranges と同じ）。
// fixedOff(day) は希望休か固定の公休か。previousOff は実際に入力された前期の最終日が公休か。
function forbidden(row,days,fixedOff,previousOff){const off=day=>day<=0?!!previousOff:row?.[day]==='off',fixed=day=>day<=0||!!fixedOff(day),result=[];for(let day=1;day<=days;day++){if(off(day)&&off(day-1)&&!(fixed(day-1)&&fixed(day))){const last=result.at(-1);if(last&&last.end===day-1){last.end=day;last.count++;}else result.push({start:day-1,end:day,count:1});}}return result;}
return {ranges,check,checkNone,forbidden};
});
