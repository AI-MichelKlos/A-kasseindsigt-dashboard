(function(){
  'use strict';
  const STORAGE_KEY='dak-a-kasseindsigt-personal-view-v1';
  const PARAM='pv';
  let applying=false;

  function encodeState(state){
    const json=JSON.stringify(state);
    const bytes=new TextEncoder().encode(json);
    let binary='';
    bytes.forEach(b=>binary+=String.fromCharCode(b));
    return btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
  }
  function decodeState(value){
    try{
      let b64=value.replace(/-/g,'+').replace(/_/g,'/');
      while(b64.length%4)b64+='=';
      const binary=atob(b64),bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));
      return JSON.parse(new TextDecoder().decode(bytes));
    }catch(_){return null;}
  }
  function sharedState(){return decodeState(new URLSearchParams(location.search).get(PARAM)||'');}
  function storedState(){try{return JSON.parse(localStorage.getItem(STORAGE_KEY)||'null');}catch(_){return null;}}
  function moduleKey(el,index){return el.dataset.personalViewKey||(el.dataset.personalViewKey='section-'+(index+1));}
  function modules(){
    const result=[];
    const kpis=document.querySelector('#dashboard > .kpis');
    if(kpis)result.push({key:'kpis',label:'Nøgletal øverst',nodes:[kpis]});
    document.querySelectorAll('#dashboard > section').forEach((section,index)=>{
      const label=section.querySelector('h2')?.textContent?.replace(/^\s*\d+\.\s*/,'').trim()||('Afsnit '+(index+1));
      result.push({key:moduleKey(section,index),label,nodes:[section]});
    });
    return result;
  }
  function hiddenKeys(){return modules().filter(m=>m.nodes.some(n=>n.hidden)).map(m=>m.key);}
  function currentState(){
    return {
      v:1,
      fund:document.getElementById('fundSelect')?.value||'',
      period:document.getElementById('periodSelect')?.value||'',
      compare:[...document.querySelectorAll('.compareCheck:checked')].map(x=>x.value),
      hidden:hiddenKeys()
    };
  }
  function save(){if(applying)return;try{localStorage.setItem(STORAGE_KEY,JSON.stringify(currentState()));}catch(_){}}
  function applyVisibility(hidden){
    const hiddenSet=new Set(Array.isArray(hidden)?hidden:[]);
    modules().forEach(m=>m.nodes.forEach(n=>n.hidden=hiddenSet.has(m.key)));
    document.querySelectorAll('[data-pv-module]').forEach(input=>input.checked=!hiddenSet.has(input.value));
  }
  function refreshChecks(){
    const host=document.getElementById('pvModules');
    if(!host)return;
    host.innerHTML=modules().map(m=>`<label class="pv-option"><input type="checkbox" data-pv-module value="${m.key}" ${m.nodes.some(n=>n.hidden)?'':'checked'}><span>${m.label}</span></label>`).join('');
    host.querySelectorAll('[data-pv-module]').forEach(input=>input.addEventListener('change',()=>{
      const mod=modules().find(m=>m.key===input.value);if(!mod)return;
      mod.nodes.forEach(n=>n.hidden=!input.checked);save();
    }));
  }
  function applyState(state){
    if(!state)return;
    applying=true;
    const fund=document.getElementById('fundSelect'),period=document.getElementById('periodSelect');
    if(state.fund&&fund&&[...fund.options].some(o=>o.value===state.fund))fund.value=state.fund;
    if(state.period&&period&&[...period.options].some(o=>o.value===String(state.period)))period.value=String(state.period);
    if(Array.isArray(state.compare)){
      document.querySelectorAll('.compareCheck').forEach(x=>x.checked=state.compare.includes(x.value));
    }
    applyVisibility(state.hidden||[]);
    if(typeof draw==='function')draw();
    refreshChecks();
    applying=false;
    save();
  }
  function injectStyle(){
    const style=document.createElement('style');
    style.textContent='.pv-bar{grid-column:1/-1;display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding-top:2px}.pv-details{position:relative}.pv-details>summary,.pv-btn{list-style:none;cursor:pointer;border:1px solid #d6dfd9;border-radius:8px;background:#fff;color:var(--ink);padding:9px 11px;font:inherit;font-weight:650}.pv-details>summary::-webkit-details-marker{display:none}.pv-details[open]>summary{border-color:var(--g)}.pv-panel{position:absolute;z-index:80;top:calc(100% + 6px);left:0;width:min(360px,88vw);background:#fff;border:1px solid #dfe5e1;border-radius:10px;box-shadow:0 12px 30px rgba(15,43,54,.18);padding:12px}.pv-panel strong{display:block;margin-bottom:8px}.pv-option{display:flex;gap:8px;align-items:center;padding:6px 2px;font-size:.84rem}.pv-option input{accent-color:var(--gd)}.pv-note{font-size:.76rem;color:var(--muted);margin:8px 0 2px}.pv-feedback{font-size:.78rem;color:var(--gd);font-weight:650}.pv-btn:hover,.pv-details>summary:hover{background:#f7faf8}@media(max-width:720px){.pv-panel{position:fixed;left:16px;right:16px;top:20%;width:auto;max-height:65vh;overflow:auto}.pv-btn,.pv-details>summary{width:auto}}';
    document.head.appendChild(style);
  }
  function injectControls(){
    const controls=document.querySelector('.controls');if(!controls||document.getElementById('pvControls'))return;
    const bar=document.createElement('div');bar.className='pv-bar';bar.id='pvControls';
    bar.innerHTML='<details class="pv-details" id="pvDetails"><summary>Tilpas visning</summary><div class="pv-panel"><strong>Vælg hvad du vil se</strong><div id="pvModules"></div><div class="pv-note">Dine valg gemmes kun i denne browser.</div></div></details><button class="pv-btn" id="pvShare" type="button">Del min visning</button><button class="pv-btn" id="pvReset" type="button">Nulstil</button><span class="pv-feedback" id="pvFeedback"></span>';
    controls.appendChild(bar);refreshChecks();
    document.getElementById('pvShare').addEventListener('click',async()=>{
      const url=new URL(location.href);url.searchParams.set(PARAM,encodeState(currentState()));
      try{await navigator.clipboard.writeText(url.toString());document.getElementById('pvFeedback').textContent='Link kopieret';}
      catch(_){prompt('Kopiér dette link',url.toString());}
      setTimeout(()=>{const f=document.getElementById('pvFeedback');if(f)f.textContent='';},2500);
    });
    document.getElementById('pvReset').addEventListener('click',()=>{
      localStorage.removeItem(STORAGE_KEY);const url=new URL(location.href);url.searchParams.delete(PARAM);location.replace(url.toString());
    });
  }
  function bindSave(){
    document.getElementById('fundSelect')?.addEventListener('change',()=>setTimeout(save,0));
    document.getElementById('periodSelect')?.addEventListener('change',()=>setTimeout(save,0));
    document.getElementById('compareOptions')?.addEventListener('change',()=>setTimeout(save,0));
  }
  function ready(){return typeof DATA!=='undefined'&&DATA&&document.getElementById('fundSelect')?.options.length>0&&!document.getElementById('dashboard')?.hidden;}
  function start(){
    if(!ready()){setTimeout(start,80);return;}
    injectStyle();injectControls();bindSave();
    const state=sharedState()||storedState();
    if(state)applyState(state);else{refreshChecks();save();}
  }
  start();
})();
