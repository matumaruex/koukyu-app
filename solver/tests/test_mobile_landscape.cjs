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

 // 条件を変更済みの作業表も、当時の職員と希望で表示し、新しい入力へ混ぜない。
 const stale=start();stale.eval("data.staff[0].name='変更後の職員A';data.staff[0].monthlyDaysOff=10;save(true);render()");
 assert(stale.get('workChanged()'));const changed=stale.get('data'),old=stale.get('schedule().workSnapshot');
 open(stale);assert(body(stale).text.includes('作成時の職員A'));assert(!body(stale).text.includes('変更後の職員A'));
 assert(body(stale).text.includes('最新の条件とは異なる条件で作成した表です。'));await stale.click('注意1件');assert.equal(body(stale).all('section')[0].hidden,false);await stale.click('注意を閉じる');await stale.click('閉じる');
 assert.deepEqual(stale.get('data'),changed);assert.deepEqual(stale.get('schedule().workSnapshot'),old);assert.equal(stale.calls.length,0);

 // 保存した表は現在の期間・職員を使わず、保存時の内容で表示する。
 const saved=start();saved.eval("data.savedTables.push(RosterStorage.capture(data,key(),'保存した表','saved'));data.staff[0].name='現在の別名';state.month=11;state.tab='saved';state.archiveId='saved';render()");
 const current=saved.get('data'),period=saved.get('[state.year,state.month]');
 open(saved);assert(body(saved).text.includes('作成時の職員A'));assert(!body(saved).text.includes('現在の別名'));
 assert(body(saved).text.includes('10月16日'));assert(body(saved).all('td').every(td=>!td.onclick));
 await saved.click('文字を大きく');await saved.click('閉じる');
 assert.deepEqual(saved.get('data'),current);assert.deepEqual(saved.get('[state.year,state.month]'),period);assert.equal(saved.calls.length,0);
 // 説明を省いても、注意は残す。
 const warning=start();warning.eval("schedule().meta={status:'DRAFT',signature:inputData().signature,ruleExceptions:[{code:'consecutive',staff:'s0',day:4,actual:4,limit:3}],historyVerification:{issues:[{staff:'s0',provided:5,required:6,reasons:['consecutive']}]},nightRestPreferences:{rule:'night-request-gap-1',unmet:[{staff:'s0',day:7}]}};render()");
 open(warning);for(const text of ['人数不足','勤務条件の例外：1件','前期をまたぐ条件の確認は未完了','夜勤後にできなかった希望休','作成時の職員A'])assert(body(warning).text.includes(text),text);
 assert(!body(warning).text.includes('記号・ルール'));
 const warned=warning.get('data'),warnedStorage=[...warning.values],dialog=body(warning),table=dialog.all('table')[0],rows=table.all('tr').map(r=>r.children.map(c=>c.text)),panel=dialog.all('section')[0],toggle=dialog.all('button').find(b=>b.text==='注意4件');
 assert(toggle);assert.equal(panel.hidden,true);assert.equal(toggle.attributes['aria-controls'],panel.id);assert.equal(toggle.attributes['aria-expanded'],'false');
 const line=dialog.all('div').find(e=>e.className==='landscape-title-line');assert(line.children.includes(toggle));assert.equal(line.children[0].text,'公休表');
 const wrap=dialog.all('div').find(e=>e.className==='month-wrap');assert(!wrap.children.some(e=>e.className==='month-notices'));assert(!wrap.text.includes('人数不足'));
 let focused='';panel.all('button')[0].focus=()=>{focused='close';};toggle.focus=()=>{focused='toggle';};
 await warning.click('注意4件');assert.equal(panel.hidden,false);assert.equal(toggle.attributes['aria-expanded'],'true');assert.equal(focused,'close');
 await warning.click('文字を大きく');assert.equal(panel.hidden,false);assert(dialog.className.includes('landscape-enlarged'));
 await warning.click('注意を閉じる');assert.equal(panel.hidden,true);assert.equal(focused,'toggle');assert.equal(toggle.attributes['aria-expanded'],'false');
 await warning.click('注意4件');let prevented=false,stopped=false;panel.onkeydown({key:'Escape',preventDefault(){prevented=true;},stopPropagation(){stopped=true;}});assert(prevented&&stopped);assert.equal(panel.hidden,true);assert(warning.nodes.dialog.open);
 assert.equal(dialog.all('table')[0],table);assert.deepEqual(table.all('tr').map(r=>r.children.map(c=>c.text)),rows);await warning.click('閉じる');
 assert.deepEqual(warning.get('data'),warned);assert.deepEqual([...warning.values],warnedStorage);assert.equal(warning.calls.length,0);
 // 希望休の注意が長くても見出しは件数だけ、一覧は全日付を保持する。
 const many=start();many.eval("schedule().meta.nightRestPreferences={rule:'night-request-gap-1',unmet:Array.from({length:31},(_,i)=>({staff:'s0',day:i+1}))};render()");const manyData=many.get('data');open(many);
 await many.click('注意1件');const manyPanel=body(many).all('section')[0];assert(manyPanel.text.includes('10月16日'));assert(manyPanel.text.includes('11月15日'));assert(!body(many).children[0].text.includes('夜勤後にできなかった希望休'));await many.click('注意を閉じる');await many.click('閉じる');assert.deepEqual(many.get('data'),manyData);assert.equal(many.calls.length,0);
 // 条件未確認や必須違反も消さずに見出しから開ける。
 for(const [meta,text]of [[null,'この表の条件確認は未完了です'],[{status:'INVALID'},'条件に合わない勤務があります']]){const bad=start();bad.ctx.testMeta=meta;bad.eval('schedule().meta=testMeta;render()');open(bad);await bad.click('注意1件');assert(body(bad).all('section')[0].text.includes(text));await bad.click('閉じる');}
 // 同じ勤務を通常・印刷・横表示・保存表で新しい記号にそろえ、値と入力署名を維持する。
 const marks=start();marks.eval("data.staff[0].canOvertime=true;schedule().assignments.a={'1':'overtime','2':'night','3':'nightOff','4':'off'};schedule().shiftRequests={a:{'1':'overtime','2':'night'}};schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
 const expected=['残','S','ー','公','・'],symbols=table=>table.all('tr')[2].children.slice(6,11).map(e=>e.text),markData=marks.get('data'),markSignature=marks.get('inputData().signature'),markStorage=[...marks.values];
 assert(marks.nodes.view.all('table').every(t=>JSON.stringify(symbols(t))===JSON.stringify(expected)));
 const legend=marks.nodes.view.text;for(const phrase of ['残 通し7:00','S 夜勤','ー 明け','公 公休'])assert(legend.includes(phrase),phrase);
 open(marks);assert.deepEqual(symbols(body(marks).all('table')[0]),expected);await marks.click('閉じる');
 marks.eval('editHistory()');const historyOptions=body(marks).all('select')[1].all('option').map(e=>e.text);for(const label of ['残（通し）','S（夜勤）','ー（明け）','公（公休）'])assert(historyOptions.includes(label));await marks.click('閉じる');
 marks.eval("editShift(data.staff[0],1)");assert(body(marks).all('option').some(e=>e.text==='残（通し）'));await marks.click('閉じる');
 marks.eval("editRequests('a')");const requestMarks=body(marks).all('span').filter(e=>e.className==='request-mark').map(e=>e.text);assert(requestMarks.includes('残'));assert(requestMarks.includes('S'));assert(requestMarks.includes('公'));await marks.click('閉じる');
 assert(marks.ctx.solverIssues(['職員1のA残の回数'],marks.get('inputData().map')).items[0].includes('作成時の職員Aの残の回数'));
 assert.deepEqual(marks.get('data'),markData);assert.equal(marks.get('inputData().signature'),markSignature);assert.deepEqual([...marks.values],markStorage);assert.equal(marks.calls.length,0);
 marks.eval("data.savedTables.push(RosterStorage.capture(data,key(),'記号確認','marks'));state.tab='saved';state.archiveId='marks';render()");assert(marks.nodes.view.all('table').every(t=>JSON.stringify(symbols(t))===JSON.stringify(expected)));
 // 28〜31日でも全日付・全職員・集計列を省かない。
 for(const [year,month,n]of [[2026,2,28],[2028,2,29],[2026,9,30],[2026,10,31]]){
  const days=start();days.ctx.testYear=year;days.ctx.testMonth=month;
  days.eval("state.year=testYear;state.month=testMonth;schedule().assignments=Object.fromEntries(data.staff.map(st=>[st.id,Object.fromEntries(Array.from({length:days()},(_,i)=>[String(i+1),i%2?'early':'off']))]));schedule().workSignature=inputData().signature;schedule().meta={status:'VALID',signature:inputData().signature};render()");
  const all=days.nodes.view.all('table')[0].all('tr').map(r=>r.children.map(c=>c.text));open(days);
  const viewed=body(days).all('table')[0].all('tr');assert.equal(viewed[0].children.length,n+6);assert.deepEqual(viewed.slice(2).map(r=>r.children.map(c=>c.text)),all.slice(2));
  // 16日始まり・月またぎ・うるう年でも、色を付ける日付/曜日の見出しが実際の土日と合う。
  for(let d=1;d<=n;d++){const weekday=new Date(Date.UTC(year,month-1,15+d)).getUTCDay(),cls=weekday===6?'sat':weekday===0?'sun':'';assert.equal(viewed[0].children[d+5].className||'',cls);assert.equal(viewed[1].children[d-1].className||'',cls);}
  await days.click('閉じる');assert(days.nodes.view.text.includes('記号・ルールの説明'));
 }
 console.log('PASS: 公休表の横表示・拡大・閉じる・別画面への復帰、旧作業表と保存表の参照、入力と表の保持');
})().catch(e=>{console.error(e);process.exitCode=1;});
