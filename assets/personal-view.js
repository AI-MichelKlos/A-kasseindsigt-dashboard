(function(){
  'use strict';
  const STORAGE_KEY='dak-a-kasseindsigt-personal-view-v2';
  const PARAM='pv';
  const REGIONS=[
    ['all','Hele landet',null],
    ['hovedstaden','Region Hovedstaden','data/regions/hovedstaden.json'],
    ['sjaelland','Region Sjælland','data/regions/sjaelland.json'],
    ['syddanmark','Region Syddanmark','data/regions/syddanmark.json'],
    ['midtjylland','Region Midtjylland','data/regions/midtjylland.json'],
    ['nordjylland','Region Nordjylland','data/regions/nordjylland.json']
  ];
  const REGION_FILES=new Map(REGIONS.map(([key,,file])=>[key,file]));
  const REGION_LABELS=new Map(REGIONS.map(([key,label])=>[key,label]));
  const regionCache=new Map();
  let applying=false;
  let nationalData=null;
  let activeRegion='all';
  let nationalPeriod=null;
  let regionalPeriod='60';
  let drawWrapped=false;

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
  function storedState(){
    try{
      return JSON.parse(localStorage.getItem(STORAGE_KEY)||localStorage.getItem('dak-a-kasseindsigt-personal-view-v1')||'null');
    }catch(_){return null;}
  }
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
      v:2,
      region:document.getElementById('regionSelect')?.value||'all',
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

  function injectStyle(){
    if(document.getElementById('regionalPersonalViewStyle'))return;
    const style=document.createElement('style');
    style.id='regionalPersonalViewStyle';
    style.textContent=`
      .controls.with-regions{grid-template-columns:1fr 1.15fr 1.55fr .75fr auto}
      .regional-notice{display:none;margin:-2px 0 14px;padding:10px 12px;border:1px solid #d8e5dc;border-radius:8px;background:#f4f8f5;color:#405b63;font-size:.82rem;line-height:1.45}
      .regional-notice.show{display:block}
      .regional-notice strong{color:var(--ink)}
      .regional-mode #dashboard>.kpis{grid-template-columns:repeat(2,1fr)}
      .regional-mode #dashboard>.kpis>.kpi:nth-child(n+3){display:none}
      .regional-mode #dashboard>section:nth-of-type(n+3){display:none!important}
      .regional-mode #dashboard>section:nth-of-type(2) .grid>.card:not(.wide){display:none!important}
      .pv-bar{grid-column:1/-1;display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding-top:2px}
      .pv-details{position:relative}
      .pv-details>summary,.pv-btn{list-style:none;cursor:pointer;border:1px solid #d6dfd9;border-radius:8px;background:#fff;color:var(--ink);padding:9px 11px;font:inherit;font-weight:650}
      .pv-details>summary::-webkit-details-marker{display:none}
      .pv-details[open]>summary{border-color:var(--g)}
      .pv-panel{position:absolute;z-index:80;top:calc(100% + 6px);left:0;width:min(360px,88vw);background:#fff;border:1px solid #dfe5e1;border-radius:10px;box-shadow:0 12px 30px rgba(15,43,54,.18);padding:12px}
      .pv-panel strong{display:block;margin-bottom:8px}.pv-option{display:flex;gap:8px;align-items:center;padding:6px 2px;font-size:.84rem}.pv-option input{accent-color:var(--gd)}
      .pv-note{font-size:.76rem;color:var(--muted);margin:8px 0 2px}.pv-feedback{font-size:.78rem;color:var(--gd);font-weight:650}.pv-btn:hover,.pv-details>summary:hover{background:#f7faf8}
      @media(max-width:1100px){.controls.with-regions{grid-template-columns:1fr 1fr 1fr}.regional-mode #dashboard>.kpis{grid-template-columns:1fr 1fr}}
      @media(max-width:720px){.controls.with-regions{grid-template-columns:1fr}.pv-panel{position:fixed;left:16px;right:16px;top:20%;width:auto;max-height:65vh;overflow:auto}.pv-btn,.pv-details>summary{width:auto}}
      @media(max-width:450px){.regional-mode #dashboard>.kpis{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  function injectRegionControls(){
    const controls=document.querySelector('.controls');
    if(!controls||document.getElementById('regionSelect'))return;
    controls.classList.add('with-regions');
    const control=document.createElement('div');
    control.className='control region-control';
    control.innerHTML='<label for="regionSelect">Geografi</label><select id="regionSelect"></select>';
    controls.insertBefore(control,controls.firstElementChild);
    const select=control.querySelector('select');
    REGIONS.forEach(([key,label])=>select.add(new Option(label,key)));
    const notice=document.createElement('div');
    notice.className='regional-notice';notice.id='regionalNotice';
    controls.parentElement.appendChild(notice);
    select.addEventListener('change',()=>setRegion(select.value).catch(handleRegionError));
  }

  function injectPersonalControls(){
    const controls=document.querySelector('.controls');if(!controls||document.getElementById('pvControls'))return;
    const bar=document.createElement('div');bar.className='pv-bar';bar.id='pvControls';
    bar.innerHTML='<details class="pv-details" id="pvDetails"><summary>Tilpas visning</summary><div class="pv-panel"><strong>Vælg hvad du vil se</strong><div id="pvModules"></div><div class="pv-note">Dine valg gemmes kun i denne browser.</div></div></details><button class="pv-btn" id="pvShare" type="button">Del min visning</button><button class="pv-btn" id="pvReset" type="button">Nulstil</button><span class="pv-feedback" id="pvFeedback"></span>';
    controls.appendChild(bar);refreshChecks();
    const details=document.getElementById('pvDetails');
    details?.addEventListener('mouseleave',()=>details.removeAttribute('open'));
    document.addEventListener('pointerdown',e=>{if(details?.open&&!details.contains(e.target))details.removeAttribute('open');});
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&details?.open)details.removeAttribute('open');});
    document.getElementById('pvShare').addEventListener('click',async()=>{
      const url=new URL(location.href);url.searchParams.set(PARAM,encodeState(currentState()));
      try{await navigator.clipboard.writeText(url.toString());document.getElementById('pvFeedback').textContent='Link kopieret';}
      catch(_){prompt('Kopiér dette link',url.toString());}
      setTimeout(()=>{const f=document.getElementById('pvFeedback');if(f)f.textContent='';},2500);
    });
    document.getElementById('pvReset').addEventListener('click',()=>{
      localStorage.removeItem(STORAGE_KEY);localStorage.removeItem('dak-a-kasseindsigt-personal-view-v1');
      const url=new URL(location.href);url.searchParams.delete(PARAM);location.replace(url.toString());
    });
  }

  function setPeriodLimit(regional){
    const select=document.getElementById('periodSelect');if(!select)return;
    [...select.options].forEach(option=>{
      const tooLong=Number(option.value)>60;
      if(tooLong){option.disabled=regional;option.hidden=regional;}
    });
  }

  function mergedRegionalData(payload){
    const funds={};
    Object.entries(nationalData.funds||{}).forEach(([code,national])=>{
      const regional=payload.funds?.[code]||{};
      funds[code]={
        ...national,
        members:regional.members||{labels:[],values:[]},
        profileAge:regional.profileAge||[],
        unemploymentRate:regional.unemploymentRate||{labels:[],values:[]}
      };
    });
    return {
      ...nationalData,
      meta:{...nationalData.meta,regional:payload.meta},
      funds
    };
  }

  async function loadRegion(key){
    if(regionCache.has(key))return regionCache.get(key);
    const file=REGION_FILES.get(key);
    if(!file)throw new Error('Ukendt region');
    const response=await fetch(file,{cache:'no-store'});
    if(!response.ok)throw new Error('Regional data kunne ikke hentes (HTTP '+response.status+')');
    const payload=await response.json();
    if(!payload?.funds||!payload?.meta)throw new Error('Regional datafil er ugyldig');
    regionCache.set(key,payload);
    return payload;
  }

  function updateRegionalText(){
    const section2=document.querySelector('#dashboard > section:nth-of-type(2) > p');
    if(section2&&!section2.dataset.nationalText)section2.dataset.nationalText=section2.textContent;
    if(activeRegion==='all'){
      if(section2?.dataset.nationalText)section2.textContent=section2.dataset.nationalText;
      return;
    }
    if(section2)section2.textContent='Ledighedsprocent blandt forsikrede i den valgte region.';
  }

  function decorateRegionalSources(){
    if(activeRegion==='all')return;
    const meta=DATA?.meta?.regional||{};
    const name=meta.areaName||REGION_LABELS.get(activeRegion)||'Region';
    const sourceStatus=meta.sourceStatus||{};
    const aua=sourceStatus.AUA01?.latestPeriod;
    const aup=sourceStatus.AUP03?.latestPeriod;
    ['sAUA','sAUA2','sAUA3'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=name+(aua?' · Seneste: '+period(aua):'');});
    const aupEl=document.getElementById('sAUP');if(aupEl)aupEl.textContent=name+(aup?' · Seneste: '+period(aup):'');
  }

  function updateNotice(message,isError=false){
    const note=document.getElementById('regionalNotice');if(!note)return;
    if(activeRegion==='all'&&!message){note.className='regional-notice';note.textContent='';return;}
    note.className='regional-notice show';
    note.innerHTML=message||'<strong>Regional visning:</strong> Medlemstal, aldersprofil og ledighedsprocent vises for '+(DATA?.meta?.regional?.areaName||REGION_LABELS.get(activeRegion))+'. Regional historik går op til 5 år tilbage. Øvrige moduler er skjult, fordi de ikke indgår med verificeret region × a-kasse i den nuværende kildeopsætning.';
    if(isError)note.style.borderColor='#e3b7b0';else note.style.borderColor='';
  }

  function wrapDraw(){
    if(drawWrapped||typeof draw!=='function')return;
    const baseDraw=draw;
    draw=function(){baseDraw();decorateRegionalSources();updateRegionalText();};
    drawWrapped=true;
  }

  async function setRegion(key){
    if(!nationalData)return;
    const select=document.getElementById('regionSelect');
    const periodSelect=document.getElementById('periodSelect');
    if(!REGION_FILES.has(key))key='all';

    if(key==='all'){
      activeRegion='all';
      DATA=nationalData;
      document.body.classList.remove('regional-mode');
      setPeriodLimit(false);
      if(nationalPeriod&&[...periodSelect.options].some(o=>o.value===String(nationalPeriod)))periodSelect.value=String(nationalPeriod);
      if(select)select.value='all';
      updateNotice();updateRegionalText();
      if(typeof draw==='function')draw();
      save();
      return;
    }

    if(activeRegion==='all'){
      nationalPeriod=periodSelect.value;
      if(Number(periodSelect.value)<=60)regionalPeriod=periodSelect.value;
    }else if(Number(periodSelect.value)<=60){
      regionalPeriod=periodSelect.value;
    }

    activeRegion=key;
    if(select)select.value=key;
    setPeriodLimit(true);
    periodSelect.value=Number(regionalPeriod)<=60?String(regionalPeriod):'60';
    updateNotice('<strong>Henter '+REGION_LABELS.get(key)+'...</strong>');
    const payload=await loadRegion(key);
    if(document.getElementById('regionSelect')?.value!==key)return;
    DATA=mergedRegionalData(payload);
    document.body.classList.add('regional-mode');
    updateNotice();updateRegionalText();
    if(typeof draw==='function')draw();
    save();
  }

  function handleRegionError(error){
    console.error(error);
    updateNotice('<strong>Regional visning kunne ikke indlæses.</strong> '+(error?.message||'Ukendt fejl')+'. Landsvisningen er bevaret.',true);
    activeRegion='all';DATA=nationalData;document.body.classList.remove('regional-mode');setPeriodLimit(false);
    const select=document.getElementById('regionSelect');if(select)select.value='all';
    if(typeof draw==='function')draw();
  }

  async function applyState(state){
    if(!state)return;
    applying=true;
    const fund=document.getElementById('fundSelect'),periodSelect=document.getElementById('periodSelect');
    if(state.fund&&fund&&[...fund.options].some(o=>o.value===state.fund))fund.value=state.fund;
    if(state.period&&periodSelect&&[...periodSelect.options].some(o=>o.value===String(state.period)))periodSelect.value=String(state.period);
    if(Array.isArray(state.compare))document.querySelectorAll('.compareCheck').forEach(x=>x.checked=state.compare.includes(x.value));
    applyVisibility(state.hidden||[]);
    const region=REGION_FILES.has(state.region)?state.region:'all';
    if(region!=='all'&&Number(periodSelect.value)<=60)regionalPeriod=periodSelect.value;
    try{await setRegion(region);}catch(error){handleRegionError(error);}
    if(typeof draw==='function')draw();
    refreshChecks();
    applying=false;
    save();
  }

  function bindSave(){
    document.getElementById('fundSelect')?.addEventListener('change',()=>setTimeout(save,0));
    document.getElementById('periodSelect')?.addEventListener('change',()=>{
      if(activeRegion==='all')nationalPeriod=document.getElementById('periodSelect').value;
      else regionalPeriod=document.getElementById('periodSelect').value;
      setTimeout(save,0);
    });
    document.getElementById('compareOptions')?.addEventListener('change',()=>setTimeout(save,0));
    document.getElementById('regionSelect')?.addEventListener('change',()=>setTimeout(save,0));
  }
  function ready(){return typeof DATA!=='undefined'&&DATA&&document.getElementById('fundSelect')?.options.length>0&&!document.getElementById('dashboard')?.hidden;}
  async function start(){
    injectStyle();injectRegionControls();
    if(!ready()){setTimeout(start,80);return;}
    if(!nationalData){nationalData=DATA;nationalPeriod=document.getElementById('periodSelect')?.value||'36';}
    wrapDraw();injectPersonalControls();bindSave();
    const state=sharedState()||storedState();
    if(state)await applyState(state);else{refreshChecks();save();}
  }
  start();
})();
