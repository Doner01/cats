const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function fixture(fetch) {
  const elements = new Map();
  function element(id, text='') {
    const node={id,innerText:text,textContent:text,src:'',value:'',dataset:{},style:{},children:[],attributes:{},classList:{add(){},remove(){},contains(){return false}},setAttribute(k,v){this.attributes[k]=v},appendChild(el){this.children.push(el)},addEventListener(){},querySelector(){return null}};
    elements.set(id,node); return node;
  }
  ['modal-like-count','modal-heart-icon','modal-cat-name','modal-cat-img','modal-cat-bio-box','modal-cat-bio-text','modal-comments-list','modal-comments-count','modal-comments-count-badge','modal-comment-input','cat-detail-modal'].forEach(id=>element(id,id==='modal-like-count'?'0':''));
  const context=vm.createContext({console,setTimeout:()=>0,URL,Map,Set,Date,
    document:{getElementById:id=>elements.get(id)||null,querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){},createElement:()=>element('created'),body:{style:{}}},
    window:{addEventListener(){}},fetch,showToast(){},supabaseClient:{auth:{getSession:async()=>({data:{session:{access_token:'test'}}})}},currentSession:{access_token:'test'}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/main.js'),'utf8'),context);
  return {context,element,elements,run:source=>vm.runInContext(source,context)};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('feed votes use the feed count and roll back after a failed request',async()=>{
 let resolve;const f=fixture(()=>new Promise(r=>resolve=r));
 f.element('like-count-cat-a','42');f.element('heart-icon-cat-a','🤍');
 const pending=f.run("toggleLike('cat-a')");await tick();
 assert.equal(f.elements.get('like-count-cat-a').innerText,43);
 resolve({ok:false,json:async()=>({error:'offline'})});await pending;
 assert.equal(f.elements.get('like-count-cat-a').innerText,42);
 assert.equal(f.run("pendingLikes.size"),0);
});

test('rapid double clicks send only one vote request',async()=>{
 let resolve;let requests=0;const f=fixture(()=>{requests++;return new Promise(r=>resolve=r)});
 f.element('like-count-cat-a','42');f.element('heart-icon-cat-a','🤍');
 const a=f.run("toggleLike('cat-a')");await tick();await f.run("toggleLike('cat-a')");
 assert.equal(requests,1);resolve({ok:true,json:async()=>({status:'liked',likes_count:43})});await a;
 assert.equal(f.elements.get('like-count-cat-a').innerText,43);
});

test('a different open modal cannot change the feed vote count',async()=>{
 const f=fixture(async()=>({ok:true,json:async()=>({status:'liked',likes_count:43})}));
 f.element('like-count-cat-a','42');f.element('heart-icon-cat-a','🤍');
 f.elements.get('modal-like-count').innerText='999';f.elements.get('modal-heart-icon').innerText='❤️';
 f.run("activeModalCatId='cat-b'");await f.run("toggleLike('cat-a')");
 assert.equal(f.elements.get('modal-like-count').innerText,'999');
 assert.equal(f.elements.get('like-count-cat-a').innerText,43);
});

test('late cat details cannot overwrite a newer modal',async()=>{
 const pending={};const f=fixture(url=>{
 if(url.endsWith('/comments'))return Promise.resolve({ok:true,json:async()=>({comments:[]})});
 return new Promise(resolve=>pending[url]=resolve);
 });
 const a=f.run("openCatModal('cat-a')");const b=f.run("openCatModal('cat-b')");
 pending['/api/cats/cat-b']({ok:true,json:async()=>({cat:{name:'Second',likes_count:20}})});await b;
 pending['/api/cats/cat-a']({ok:true,json:async()=>({cat:{name:'First',likes_count:10}})});await a;
 assert.equal(f.elements.get('modal-cat-name').innerText,'Second');
});

test('a closed modal ignores pending responses',async()=>{
 let resolve;const f=fixture(()=>new Promise(r=>resolve=r));
 const pending=f.run("openCatModal('cat-a')");f.run('closeCatModal()');
 resolve({ok:true,json:async()=>({cat:{name:'Late'}})});await pending;
 assert.equal(f.elements.get('modal-cat-name').innerText,'');
});

test('comment failures show a retry instead of an empty discussion',async()=>{
 const f=fixture(async()=>({ok:false,json:async()=>({error:'offline'})}));
 f.run("activeModalCatId='cat-a'");await f.run("loadCatComments('cat-a')");
 assert.equal(f.elements.get('modal-comments-list').textContent,'Could not load comments. ');
 assert.equal(f.elements.get('modal-comments-list').children[0].textContent,'Try again');
});
