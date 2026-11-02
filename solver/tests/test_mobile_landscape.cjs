'use strict';
// 横表示の出入り・拡大で、現在の入力と作成当時の表を変更しない。
const assert=require('node:assert/strict'),{harness}=require('./mobile_harness.cjs');
const raw={schemaVersion:4,savedTables:[],staff:[
 {id:'a',name:'作成時の職員A',type:'full',monthlyDaysOff:9,nightShiftType:'all'},
 {id:'b',name:'作成時の職員B',type:'full',monthlyDaysOff:9,nightShiftType:'all'}],
 schedules:{'2026-10':{requests:{a:[7]},assignments:{},history:{a:Array(7).fill('off'),b:Array(7).fill('off')}}}};
function start(){
 const h=harness(null,{current:raw});
 h.eval("schedule().assignments={a:{'1':'early','7':'off'},b:{'1':'night','2':'nightOff','3':'off'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
 const shell=h.nodes.dialog;
 shell.className='';shell.classList={
  add(...names){shell.className=[...new Set([...shell.className.split(' ').filter(Boolean),...names])].join(' ');},
  remove(...names){shell.className=shell.className.split(' ').filter(v=>v&&!names.includes(v)).join(' ');}
 };
 return h;
}
const open=h=>h.nodes.view.all('button').find(b=>b.text==='横画面で見る').click();
const body=h=>h.nodes['dialog-body'];
(async()=>{
 const empty=harness(null,{current:raw});assert(!empty.nodes.view.all('button').some(b=>b.text==='横画面で見る'));
 empty.ctx.openLandscapeTable();assert(!empty.nodes.dialog.open);
 const h=start(),before=h.get('data'),signature=h.get('inputData().signature'),stored=[...h.values];
 const originalRows=h.nodes.view.all('table')[0].all('tr').slice(2).map(r=>r.children.map(c=>c.text));
 open(h);assert(h.nodes.dialog.open);assert(h.nodes.dialog.className.includes('landscape-dialog'));
 assert(!body(h).all('button').some(b=>b.text.startsWith('注意')));
 assert.equal(body(h).className,'landscape-body');assert(body(h).text.includes('作成時の職員A'));assert(body(h).text.includes('公休表'));
 assert(body(h).all('table').length===1);assert(body(h).all('td').every(td=>!td.onclick&&td.attributes.role!=='button'));
 assert.deepEqual(body(h).all('table')[0].all('tr').slice(2).map(r=>r.children.map(c=>c.text)),originalRows);
 for(const text of ['記号・ルールの説明','赤い文字','A 早出7:00','表は上下左右にスクロールできます。','連休の確認'])assert(!body(h).text.includes(text),text);
 assert(!body(h).all('div').some(e=>e.className==='month-heading'||e.className==='month-guide'));
 assert(!body(h).all('button').some(b=>b.text.includes('保存')||b.text.includes('変更')));
 await h.click('文字を大きく');assert(body(h).className.includes('landscape-enlarged'));
 const zoom=body(h).all('button').find(b=>b.text==='標準の大きさ');assert.equal(zoom.attributes['aria-pressed'],'true');
 await h.click('標準の大きさ');assert.equal(body(h).className,'landscape-body');
 await h.click('閉じる');assert.equal(h.nodes.dialog.open,false);
 assert.deepEqual(h.get('data'),before);assert.equal(h.get('inputData().signature'),signature);assert.deepEqual([...h.values],stored);assert.equal(h.calls.length,0);
 // 横表示の後にほかの入力を開いても、横向きのレイアウトを引き継がない。
 h.eval('editStaff(data.staff[0])');
 assert(!h.nodes.dialog.className.includes('landscape-dialog'));await h.click('閉じる');
 open(h);assert.equal(body(h).className,'landscape-body');await h.click('閉じる');
 h.eval('state.busy=true');h.ctx.openLandscapeTable();assert(!h.nodes.dialog.open);h.eval('state.busy=false');

 // 横表示だけ名前の空白と集計見出しを圧縮し、登録名・値・読み上げを保持する。
 const compact=start();compact.eval("data.staff[0].name='久 木　山';data.staff[1].name='松　井';render()");
 const compactData=compact.get('data'),compactStorage=[...compact.values],compactSignature=compact.get('inputData().signature'),normal=compact.nodes.view.all('table')[0];
 assert.deepEqual(normal.all('tr')[0].children.slice(-5).map(c=>c.text),['公休','残業','夜勤','A','B']);
 assert.equal(normal.all('tr').find(r=>r.className==='roster-staff-row').children[0].text,'久 木　山');
 open(compact);const narrow=body(compact).all('table')[0],narrowRows=narrow.all('tr').filter(r=>r.className==='roster-staff-row');
 assert.deepEqual(narrow.all('tr')[0].children.slice(-5).map(c=>c.text),['休','残','夜','A','B']);
 assert.deepEqual(narrowRows.map(r=>r.children[0].text),['久木山','松井']);assert.equal(narrowRows[0].children[0].attributes.title,'久 木　山');assert(narrowRows[0].children[0].attributes['aria-label'].includes('久 木　山'));
 assert.deepEqual(narrowRows.map(r=>r.children.slice(1).map(c=>c.text)),normal.all('tr').filter(r=>r.className==='roster-staff-row').map(r=>r.children.slice(1).map(c=>c.text)));
 await compact.click('閉じる');assert.deepEqual(compact.get('data'),compactData);assert.deepEqual([...compact.values],compactStorage);assert.equal(compact.get('inputData().signature'),compactSignature);assert.equal(compact.calls.length,0);

 // 条件を変更済みの作業表も、当時の職員と希望で表示し、新しい入力へ混ぜない。
 const stale=start();stale.eval("data.staff[0].name='変更後の職員A';data.staff[0].monthlyDaysOff=10;save(true);render()");
 assert(stale.get('workChanged()'));const changed=stale.get('data'),old=stale.get('schedule().workSnapshot');
 open(stale);assert(body(stale).text.includes('作成時の職員A'));assert(!body(stale).text.includes('変更後の職員A'));
 assert(body(stale).text.includes('最新の条件とは異なる条件で作成した表です。'));await stale.click('注意1件');assert.equal(body(stale).all('section')[0].hidden,false);await stale.click('注意を閉じる');await stale.click('閉じる');
 assert.deepEqual(stale.get('data'),changed);assert.deepEqual(stale.get('schedule().workSnapshot'),old);assert.equal(stale.calls.length,0);

 // 保存した表は現在の期間・職員を使わず、保存時の内容で表示する。
 const saved=start();saved.eval("data.savedTables.push(RosterStorage.capture(data,key(),'保存した表','saved'));data.staff[0].name='現在の別名';state.month=11;testSavedSnapshot(data.savedTables.find(r=>r.id==='saved'))");
 const current=saved.get('data'),period=saved.get('[state.year,state.month]');
 open(saved);assert(body(saved).text.includes('作成時の職員A'));assert(!body(saved).text.includes('現在の別名'));
 assert(body(saved).text.includes('10月16日'));assert(body(saved).all('td').every(td=>!td.onclick));
 await saved.click('文字を大きく');await saved.click('閉じる');
 assert.deepEqual(saved.get('data'),current);assert.deepEqual(saved.get('[state.year,state.month]'),period);assert.equal(saved.calls.length,0);
 // 説明を省いても、注意は残す。
 const warning=start();warning.eval("schedule().meta={status:'DRAFT',signature:inputData().signature,ruleExceptions:[{code:'consecutive',staff:'s0',day:4,actual:4,limit:3}],historyVerification:{issues:[{staff:'s0',provided:5,required:6,reasons:['consecutive']}]},nightRestPreferences:{rule:'night-request-gap-1',unmet:[{staff:'s0',day:7}]}};render()");
 open(warning);for(const text of ['人数不足','勤務条件の例外：1件','前期をまたぐ条件の確認が未完了','夜勤後にできなかった希望休','作成時の職員A'])assert(body(warning).text.includes(text),text);
 assert(!body(warning).text.includes('記号・ルール'));
 const warned=warning.get('data'),warnedStorage=[...warning.values],dialog=body(warning),table=dialog.all('table')[0],rows=table.all('tr').map(r=>r.children.map(c=>c.text)),panel=dialog.all('section')[0],toggle=dialog.all('button').find(b=>b.text==='注意4件');
 assert(toggle);assert.equal(panel.hidden,true);assert.equal(toggle.attributes['aria-controls'],panel.id);assert.equal(toggle.attributes['aria-expanded'],'false');
 const line=dialog.all('div').find(e=>e.className==='landscape-title-line');assert(line.children.includes(toggle));assert.equal(line.children[0].text,'公休表');
 const wrap=dialog.all('div').find(e=>e.className==='month-wrap');assert(!wrap.children.some(e=>e.className==='month-notices'));assert(!wrap.text.includes('人数不足'));
 let focused='';panel.all('button')[0].focus=()=>{focused='close';};toggle.focus=()=>{focused='toggle';};
 await warning.click('注意4件');assert.equal(panel.hidden,false);assert.equal(toggle.attributes['aria-expanded'],'true');assert.equal(focused,'close');assert(panel.text.includes('作成時の職員A 10月19日（月）：4連勤目（上限3日）'));assert(panel.text.includes('入力5日／確認に必要6日'));
 await warning.click('文字を大きく');assert.equal(panel.hidden,false);assert(dialog.className.includes('landscape-enlarged'));
 await warning.click('注意を閉じる');assert.equal(panel.hidden,true);assert.equal(focused,'toggle');assert.equal(toggle.attributes['aria-expanded'],'false');
 await warning.click('注意4件');let prevented=false,stopped=false;panel.onkeydown({key:'Escape',preventDefault(){prevented=true;},stopPropagation(){stopped=true;}});assert(prevented&&stopped);assert.equal(panel.hidden,true);assert(warning.nodes.dialog.open);
 assert.equal(dialog.all('table')[0],table);assert.deepEqual(table.all('tr').map(r=>r.children.map(c=>c.text)),rows);await warning.click('閉じる');
 assert.deepEqual(warning.get('data'),warned);assert.deepEqual([...warning.values],warnedStorage);assert.equal(warning.calls.length,0);
 // 例外の種類・名前・日付・上限を省かず、8件超でも注意内で全件を読める。
 const detail=start();detail.eval("schedule().meta={status:'VALID',signature:inputData().signature,optimizationPolicy:OPTIMIZATION_POLICY,ruleExceptions:[{code:'consecutive',staff:'s0',day:4,actual:4,limit:3},{code:'consecutive_plus_one',staff:'s1',actual:2},{code:'day_shift_eligibility',staff:'s0',day:5,allowed:'early',actual:'late'},{code:'night_remainder',staff:'s1',actual:6,fair:5,priority:false},{code:'no_consecutive_rest',staff:'s0',start:7,end:8},{code:'rest_balance',high:3,low:1,counts:{s0:3,s1:1}},{code:'isolated_work',staff:'s0',day:10,workDay:10},{code:'rest_streak',staff:'s1',day:15,start:12,end:15,count:1},{code:'consecutive',staff:'s1',day:31,actual:5,limit:3}]};render()");
 const detailData=detail.get('data'),detailStored=[...detail.values];open(detail);await detail.click('注意1件');const dp=body(detail).all('section')[0];
 for(const text of ['勤務条件の例外：9件','4連勤目（上限3日）','上限＋1日の連勤が2回','Aのみ（早出）の設定ですが「B（遅出）','夜勤6回','連休なしの設定','連休の回数の差が2回','1日だけの出勤','4連休（3日まで','11月15日（日）：5連勤目'])assert(dp.text.includes(text),text);
 assert.equal(dp.all('li').length,9);assert.equal(dp.all('details').length,0);await detail.click('閉じる');assert.deepEqual(detail.get('data'),detailData);assert.deepEqual([...detail.values],detailStored);assert.equal(detail.calls.length,0);
 // 保存時の名前と期間で詳細を作り、後の入力変更を混ぜない。
 detail.eval("data.savedTables.push(RosterStorage.capture(data,key(),'注意確認','notice-saved'));data.staff[0].name='変更後';data.staff[0].monthlyDaysOff=10;render()");open(detail);await detail.click('注意2件');assert(body(detail).all('section')[0].text.includes('作成時の職員A 10月19日'));assert(!body(detail).all('section')[0].text.includes('変更後'));await detail.click('閉じる');
 // 人数不足と必須違反も、見出しに続いて該当日と内容を示す。
 const shortages=start();shortages.eval("schedule().meta={status:'DRAFT',signature:inputData().signature,boundaryComplete:true,unmetConditions:[{code:'coverage',day:1,time:420,actual:1,required:4}]};render()");open(shortages);await shortages.click('注意1件');assert(body(shortages).all('section')[0].text.includes('10月16日（金） 朝7:00：1人／必要4人（3人不足）'));await shortages.click('閉じる');
 const invalid=start();invalid.eval("schedule().meta={status:'INVALID',signature:inputData().signature,validationErrors:[{code:'shift_request',staff:'s0',day:4,requested:'early',actual:'late'}]};render()");open(invalid);await invalid.click('注意1件');for(const text of ['作成時の職員A','10月19日（月）','希望は「A（早出）','表は「B（遅出）'])assert(body(invalid).all('section')[0].text.includes(text),text);await invalid.click('閉じる');
 // 希望休の注意が長くても見出しは件数だけ、一覧は全日付を保持する。
 const many=start();many.eval("schedule().meta.nightRestPreferences={rule:'night-request-gap-1',unmet:Array.from({length:31},(_,i)=>({staff:'s0',day:i+1}))};render()");const manyData=many.get('data');open(many);
 await many.click('注意1件');const manyPanel=body(many).all('section')[0];assert(manyPanel.text.includes('10月16日'));assert(manyPanel.text.includes('11月15日'));assert(!body(many).children[0].text.includes('夜勤後にできなかった希望休'));await many.click('注意を閉じる');await many.click('閉じる');assert.deepEqual(many.get('data'),manyData);assert.equal(many.calls.length,0);
 // 条件未確認や必須違反も消さずに見出しから開ける。
 for(const [meta,text]of [[null,'この表の条件確認は未完了です'],[{status:'INVALID'},'条件に合わない勤務があります']]){const bad=start();bad.ctx.testMeta=meta;bad.eval('schedule().meta=testMeta;render()');open(bad);await bad.click('注意1件');assert(body(bad).all('section')[0].text.includes(text));await bad.click('閉じる');}
 // 同じ勤務を通常・印刷・横表示・保存表で新しい記号にそろえ、値と入力署名を維持する。
 const marks=start();marks.eval("data.staff[0].canOvertime=true;schedule().assignments.a={'1':'overtime','2':'night','3':'nightOff','4':'off'};schedule().shiftRequests={a:{'1':'overtime','2':'night'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
 const expected=['残','S','ー','公','・'],symbols=table=>table.all('tr').find(r=>r.className==='roster-staff-row').children.slice(1,6).map(e=>e.text),markData=marks.get('data'),markSignature=marks.get('inputData().signature'),markStorage=[...marks.values];
 assert(marks.nodes.view.all('table').every(t=>JSON.stringify(symbols(t))===JSON.stringify(expected)));
 const legend=marks.nodes.view.text;for(const phrase of ['記号・ルールの説明','残 通し7:00','S 夜勤','ー 明け','公 公休'])assert(!legend.includes(phrase),phrase);
 open(marks);assert.deepEqual(symbols(body(marks).all('table')[0]),expected);await marks.click('閉じる');
 marks.eval("editHistory('a')");const historyOptions=body(marks).all('select')[0].all('option').map(e=>e.text);for(const label of ['残（通し）','S（夜勤）','ー（明け）','公（公休）'])assert(historyOptions.includes(label));await marks.click('閉じる');
 marks.eval("editShift(data.staff[0],1)");assert(body(marks).all('option').some(e=>e.text==='残（通し）'));await marks.click('閉じる');
 marks.eval("editRequests('a')");const requestMarks=body(marks).all('span').filter(e=>e.className==='request-mark').map(e=>e.text);assert(requestMarks.includes('残'));assert(requestMarks.includes('S'));assert(requestMarks.includes('公'));await marks.click('閉じる');
 assert(marks.ctx.solverIssues(['職員1のA残の回数'],marks.get('inputData().map')).items[0].includes('作成時の職員Aの残の回数'));
 assert.deepEqual(marks.get('data'),markData);assert.equal(marks.get('inputData().signature'),markSignature);assert.deepEqual([...marks.values],markStorage);assert.equal(marks.calls.length,0);
 marks.eval("data.savedTables.push(RosterStorage.capture(data,key(),'記号確認','marks'));testSavedSnapshot(data.savedTables.find(r=>r.id==='marks'))");assert(marks.nodes.view.all('table').every(t=>JSON.stringify(symbols(t))===JSON.stringify(expected)));
 // 28〜31日でも全日付・全職員・集計列を省かない。
 for(const [year,month,n]of [[2026,2,28],[2028,2,29],[2026,9,30],[2026,10,31]]){
  const days=start();days.ctx.testYear=year;days.ctx.testMonth=month;
  days.eval("state.year=testYear;state.month=testMonth;schedule().assignments=Object.fromEntries(data.staff.map(st=>[st.id,Object.fromEntries(Array.from({length:days()},(_,i)=>[String(i+1),i%2?'early':'off']))]));schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
  const all=days.nodes.view.all('table')[0].all('tr').map(r=>r.children.map(c=>c.text));open(days);
  const viewed=body(days).all('table')[0].all('tr');assert.equal(viewed[0].children.length,n+6);assert.deepEqual(viewed.slice(2).map(r=>r.children.map(c=>c.text)),all.slice(2));
  assert.equal(viewed[0].children[0].text,'職員');assert.equal(viewed[0].children.slice(1,-5).length,n);assert.deepEqual(viewed[0].children.slice(-5).map(c=>c.text),['休','残','夜','A','B']);
  for(const r of viewed.slice(2)){assert.equal(r.children.reduce((sum,c)=>sum+(c.colSpan||1),0),n+6);if(r.className==='roster-staff-row'){assert(r.children.slice(-5).every(c=>c.className.startsWith('total count-')));}else{assert.equal(r.children[0].text,'');assert(r.children[0].attributes['aria-label'].includes('の人数'));assert.equal(r.children.at(-1).colSpan,5);assert.equal(r.children.at(-1).text,'');}}
  // 16日始まり・月またぎ・うるう年でも、土日の列が勤務・人数欄の最下段まで合う。
  // 保存表・印刷用にも同じ日付を使い、名前と個人集計には曜日色を付けない。
  const archived=days.eval("withSavedTable(RosterStorage.capture(data,key(),'曜日確認','weekends'),()=>monthTable(false))").all('table')[0];
  for(const table of [...days.nodes.view.all('table'),body(days).all('table')[0],archived]){
   const rs=table.all('tr');
   for(let d=1;d<=n;d++){const weekday=new Date(Date.UTC(year,month-1,15+d)).getUTCDay(),cls=weekday===6?'sat':weekday===0?'sun':'';assert.equal(rs[0].children[d].className||'',cls);assert.equal(rs[1].children[d-1].className||'',cls);
    for(const r of rs.slice(2)){const offset=1;assert.equal(r.children[d+offset-1].attributes['data-weekday']||'',cls);assert(r.children.slice(0,offset).every(c=>!c.attributes['data-weekday']));}
   }
  }
  await days.click('閉じる');assert(!days.nodes.view.text.includes('記号・ルールの説明'));
 }
 console.log('PASS: 公休表の横表示・拡大・閉じる・別画面への復帰、旧作業表と保存表の参照、入力と表の保持');
})().catch(e=>{console.error(e);process.exitCode=1;});
