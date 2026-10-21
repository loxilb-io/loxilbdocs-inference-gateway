import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';
const script = readFileSync(new URL('../docs/javascripts/analytics.js', import.meta.url), 'utf8');
function setup({choice=null,host='loxilb-io.github.io',path='/loxilbdocs-inference-gateway/latest/',dnt=false,gpc=false,badCanonical=false}={}) {
  const appended=[];
  const buttons=[];
  const cookieWrites=[];
  const storage=new Map(choice ? [['igw_analytics_consent_v1',choice]] : []);
  const element=tag=>({tag,dataset:{},hidden:false,handlers:{},setAttribute(){},
    addEventListener(name,fn){this.handlers[name]=fn;},
    querySelectorAll(){
      for(const value of ['granted','denied'])buttons.push({...element('button'),dataset:{choice:value}});
      return buttons;
    }});
  const location={protocol:'https:',hostname:host,pathname:path,origin:'https://'+host,
    href:'https://'+host+path+'?token=SYNTHETIC_PRIVATE#secret',reload(){this.reloaded=true;}};
  const document={title:'Public docs',referrer:'https://example.com/private?token=SYNTHETIC_PRIVATE',
    querySelector(){return {href:badCanonical?'https://evil.invalid/':location.origin+path};},
    createElement:element,body:{appendChild(el){appended.push(el);}},head:{appendChild(el){appended.push(el);}}};
  Object.defineProperty(document,'cookie',{get(){return '_ga=old; _ga_WJSBVPS5RV=old; unrelated=keep';},set(v){cookieWrites.push(v);}});
  const context={location,document,navigator:{doNotTrack:dnt?'1':'0',globalPrivacyControl:gpc},
    localStorage:{getItem(k){return storage.get(k)||null;},setItem(k,v){storage.set(k,v);}},URL};
  context.window=context;
  vm.runInNewContext(script,context);
  return {context,appended,buttons,cookieWrites,storage};
}
function google(s){return s.appended.filter(el=>el.tag==='script');}
test('no consent and reject produce no Google request',()=>{
  const s=setup();assert.equal(google(s).length,0);
  s.buttons[1].handlers.click();assert.equal(google(s).length,0);
  assert.equal(s.storage.get('igw_analytics_consent_v1'),'denied');
});
test('explicit accept starts once with sanitized page and referrer',()=>{
  const s=setup();s.buttons[0].handlers.click();s.buttons[0].handlers.click();
  assert.equal(google(s).length,1);assert.equal(google(s)[0].referrerPolicy,'no-referrer');
  const calls=s.context.dataLayer.map(x=>Array.from(x));
  const config=calls.find(x=>x[0]==='config')[2];
  assert.equal(config.send_page_view,false);assert.equal(config.cookie_expires,0);
  assert.equal(config.page_location,'https://loxilb-io.github.io/loxilbdocs-inference-gateway/latest/');
  assert.equal(config.page_referrer,'https://example.com/');
  assert.equal(config.allow_google_signals,false);
  assert.ok(!JSON.stringify(calls).includes('SYNTHETIC_PRIVATE'));
  assert.equal(calls.filter(x=>x[0]==='event'&&x[1]==='page_view').length,1);
});
test('stored acceptance starts, withdrawal disables and clears only owned cookies',()=>{
  const s=setup({choice:'granted'});assert.equal(google(s).length,1);
  s.buttons[1].handlers.click();assert.equal(s.context['ga-disable-G-WJSBVPS5RV'],true);
  assert.equal(s.cookieWrites.length,2);assert.ok(s.cookieWrites.every(x=>!x.includes('unrelated')));
  assert.equal(s.context.dataLayer.at(-1)[2].analytics_storage,'denied');
});
test('DNT and GPC override saved consent',()=>{
  for(const flags of [{dnt:true},{gpc:true}])assert.equal(google(setup({choice:'granted',...flags})).length,0);
});
test('local preview, forks and other Pages projects never collect',()=>{
  for(const flags of [{host:'localhost'},{host:'fork.github.io'},{path:'/another-project/'}]) {
    const s=setup({choice:'granted',...flags});for(const b of s.buttons)b.handlers.click();
    assert.equal(google(s).length,0);
  }
});
test('untrusted canonical target disables collection',()=>assert.equal(google(setup({choice:'granted',badCanonical:true})).length,0));
