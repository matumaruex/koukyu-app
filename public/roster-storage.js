'use strict';
// 入力条件・作業中の結果・明示的に保存した表の寿命を分ける。
const RosterStorage=(()=>{
  const HolidayPolicy=typeof AutoHolidayPolicy!=='undefined'?AutoHolidayPolicy:require('./auto-holiday-policy.js');
  const copy=value=>JSON.parse(JSON.stringify(value));
  const hasTable=s=>Object.values(s.assignments||{}).some(row=>Object.keys(row||{}).length);
  function periodParts(period){
    if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(period))throw Error('保存した表の対象期間を確認してください。');
    return period.split('-').map(Number);
  }
  function capture(data,period,name,id,createdAt=new Date().toISOString()){
    const schedule=copy(data.schedules[period]);
    for(const field of ['previous','workSignature','retryLong'])delete schedule[field];
    return {id,name,period,createdAt,staff:copy(data.staff),preferences:copy(data.preferences),schedule};
  }
  function clearResult(schedule){
    schedule.assignments={};
    for(const field of ['meta','previous','workSignature','retryLong','selectedQuota','autoDetails','autoReason','autoReferenceActualOff','creationMode'])delete schedule[field];
  }
  function persisted(data){
    const out=copy(data);out.schemaVersion=4;out.savedTables??=[];
    for(const schedule of Object.values(out.schedules))clearResult(schedule);
    delete out.autoSchedules;
    return out;
  }
  function prepare(raw,validate){
    const data=validate(copy(raw));
    const policy=HolidayPolicy.check(raw.autoHolidayPolicy,data.staff);if(policy)data.autoHolidayPolicy=policy;
    if(raw.schemaVersion!==undefined&&raw.schemaVersion!==4)throw Error('このバックアップの形式には対応していません。');
    if(raw.schemaVersion===4){
      if(!Array.isArray(raw.savedTables))throw Error('保存した表の一覧を確認してください。');
      const ids=new Set();
      data.savedTables=raw.savedTables.map(record=>{
        if(!record||typeof record.id!=='string'||!record.id||ids.has(record.id)||typeof record.name!=='string'||!record.name.trim()||record.name.length>80||typeof record.createdAt!=='string'||Number.isNaN(Date.parse(record.createdAt)))throw Error('保存した表の情報を確認してください。');
        ids.add(record.id);periodParts(record.period);
        if(record.creationMode!==undefined&&!['normal','auto'].includes(record.creationMode))throw Error('保存した表の作成方式を確認してください。');
        if(record.creationMode==='auto'){
          HolidayPolicy.check(record.autoHolidayPolicy,record.staff);
          const quotas=record.schedule?.selectedQuota;if(!quotas||typeof quotas!=='object'||Array.isArray(quotas)||Object.entries(quotas).some(([sid,q])=>!record.staff.some(st=>st.id===sid&&st.monthlyDaysOff===q)||!Number.isInteger(q)||q<0||q>31))throw Error('保存した表の採用公休日数を確認してください。');
          if(record.normalMinimums!==undefined&&(!record.normalMinimums||typeof record.normalMinimums!=='object'||Array.isArray(record.normalMinimums)||Object.values(record.normalMinimums).some(q=>!Number.isInteger(q)||q<0||q>31)))throw Error('保存した表の通常公休日数を確認してください。');
        }
        const checked=validate(copy({staff:record.staff,preferences:record.preferences,schedules:{[record.period]:record.schedule}}));
        if(!hasTable(checked.schedules[record.period]))throw Error('保存した表の勤務を確認してください。');
        return {...copy(record),staff:checked.staff,preferences:checked.preferences,schedule:checked.schedules[record.period]};
      });
    }else{
      data.savedTables=[];
      // 移行前に参照していた前期7日間だけを確定し、手入力は常に優先する。
      for(const [period,s] of Object.entries(data.schedules)){
        const [y,m]=periodParts(period),previousDate=new Date(Date.UTC(y,m-2,1));
        const previousKey=previousDate.getUTCFullYear()+'-'+String(previousDate.getUTCMonth()+1).padStart(2,'0');
        const previous=data.schedules[previousKey],n=new Date(Date.UTC(previousDate.getUTCFullYear(),previousDate.getUTCMonth()+1,0)).getUTCDate();
        for(const st of data.staff){
          if(s.history?.[st.id]!==undefined||s.excludedStaff?.includes(st.id)||previous?.excludedStaff?.includes(st.id))continue;
          const row=previous?.assignments?.[st.id],history=Array.from({length:7},(_,i)=>row?.[n-6+i]);
          if(history.every(v=>['early','late','night','nightOff','off','overtime','part'].includes(v))){s.history??={};s.history[st.id]=history;}
        }
      }
      for(const [period,s] of Object.entries(data.schedules)){
        if(hasTable(s))data.savedTables.push(capture(data,period,period+'（移行した表）','legacy-'+period+'-current'));
        if(s.previous&&hasTable(s.previous)){
          const record=capture(data,period,period+'（移行したひとつ前の表）','legacy-'+period+'-previous');
          record.schedule={...record.schedule,...copy(s.previous)};delete record.schedule.previous;
          data.savedTables.push(record);
        }
      }
      for(const record of data.savedTables)validate(copy({staff:record.staff,preferences:record.preferences,schedules:{[record.period]:record.schedule}}));
    }
    for(const s of Object.values(data.schedules))clearResult(s);
    data.schemaVersion=4;return data;
  }
  // 手入力済みの人を上書きせず、指定した保存表から不足する前期履歴だけを取り込む。
  function takeHistory(record,period,staff,manual,shiftNames){
    const [y,m]=periodParts(period),date=new Date(Date.UTC(y,m-2,1));
    const previousKey=date.getUTCFullYear()+'-'+String(date.getUTCMonth()+1).padStart(2,'0');
    if(record.period!==previousKey)throw Error('直前の期間の表を選んでください。');
    const n=new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+1,0)).getUTCDate(),out=copy(manual||{});let added=0;
    for(const st of staff){
      if(out[st.id]!==undefined||record.schedule.excludedStaff?.includes(st.id))continue;
      const row=record.schedule.assignments[st.id],values=Array.from({length:7},(_,i)=>row?.[n-6+i]);
      if(values.every(v=>Object.hasOwn(shiftNames,v))){out[st.id]=values;added++;}
    }
    return {history:out,added};
  }
  return {prepare,persisted,capture,clearResult,takeHistory,periodParts};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=RosterStorage;
