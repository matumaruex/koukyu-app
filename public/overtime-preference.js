(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.OvertimePreference=api;})(globalThis,function(){
'use strict';
const POLICY='quality-first-8';
function check(value){if(value===undefined)return 0;if(!Number.isInteger(value)||value<0||value>2)throw Error('残業の配分は通常・少し多め・多めから選んでください。');return value;}
function label(value){return ['通常','少し多め（＋1回目安）','多め（＋2回目安）'][check(value)];}
return {POLICY,check,label};
});
