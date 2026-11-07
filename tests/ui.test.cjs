// Browser-state regressions, using only Node's built-in test runner.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync(require('node:path').join(__dirname,'../ui/app.js'),'utf8');
function harness(storage=new Map()){
 const timers=[];
 const context=vm.createContext({crypto:require('node:crypto').webcrypto,Date,performance,
  localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},
  document:{getElementById:()=>null},setTimeout:fn=>timers.push(fn),
  history:{pushState(){}},location:{hash:'#chat'}});
 vm.runInContext(source.slice(0,source.indexOf('async function api(')),context);
 vm.runInContext("function toast(){};function render(){};state.id='report-a';state.data={};",context);
 vm.runInContext(source.slice(source.indexOf('function newChat()'),source.indexOf('function renderAnswer(')),context);
 return {context,storage,timers,run:code=>vm.runInContext(code,context)};
}
test('New chat retains conversations; switching, reload, and document isolation work',()=>{
 const h=harness();
 h.run("activeConversation().messages.push({question:'First question',response:{answer:'Verified answer'}});activeConversation().title='First question';saveConversations();globalThis.firstId=activeConversation().id;newChat()");
 assert.equal(h.run('activeConversation().messages.length'),0);
 assert.equal(h.run('conversationStore().threads.length'),2);
 h.run('openConversation(firstId)');assert.equal(h.run('activeConversation().messages[0].response.answer'),'Verified answer');
 const reloaded=harness(h.storage);assert.equal(reloaded.run('activeConversation().messages[0].question'),'First question');
 reloaded.run("state.id='report-b'");assert.equal(reloaded.run('activeConversation().messages.length'),0);
});
test('An interrupted reply is restored without retrying or spending API credits',()=>{
 const h=harness();h.run("activeConversation().messages.push({question:'Pending question'});saveConversations()");
 const reloaded=harness(h.storage);assert.match(reloaded.run('activeConversation().messages[0].error'),/interrupted/);
});
test('One API request is made and a fast response waits for the presentation timer',async()=>{
 const h=harness();
 h.run("globalThis.requests=0;async function api(){requests++;return {answer:'Verified answer'}}");
 h.run(source.slice(source.indexOf('async function ask('),source.indexOf('\nlet previousFocus;')));
 const completion=h.run("ask('Summarise this report')");
 await Promise.resolve();
 assert.equal(h.run('requests'),1);assert.equal(h.run('state.asking'),true);
 assert.equal(h.run('activeConversation().messages[0].response'),undefined);
 h.timers[0]();await completion;
 assert.equal(h.run('state.asking'),false);
 assert.equal(h.run('activeConversation().messages[0].response.answer'),'Verified answer');
 assert.equal(h.run('requests'),1);
});
