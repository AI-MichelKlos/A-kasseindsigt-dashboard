(function(){
  'use strict';
  const STORAGE_KEY='dak-a-kasseindsigt-personal-view-v3';
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
  let nationalReference=false;
  let drawWrapped=false;

  function encodeState(state){
    const json=JSON.stringify(state),bytes=new TextEncoder().encode(json);let binary='';
    bytes.forEach(b=>binary+=String.fromCharCode(b));
    return btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
  }
  function decodeState(value){
    try{let b64=value.replace(/-/g,'+').replace(/_/g,'/');while(b64.length%4)b64+='=';const binary=atob(b64),bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));return JSON.parse(new TextDecoder().decode(bytes));}catch(_){return null;}
  }
  function sharedState(){return decodeState(new URLSearchParams(location.search).get(PARAM)||'');}
  function storedState(){try{return JSON.parse(localStorage.getItem(STORAGE_KEY)||localStorage.getItem('dak-a-kasseindsigt-personal-view-v2')||localStorage.getItem('dak-a-kasseindsigt-personal-view-v1')||'null');}catch(_){return null;}}
  function moduleKey(el,index){return el.dataset.personalViewKey||(el.dataset.personalViewKey='section-'+(index+1));}
  function modules(){
    const result=[],kpis=document.querySelector('#dashboard > .kpis');
    if(kpis)result.push({key:'kpis',label:'Nøgletal øverst',nodes:[kpis]});
    document.querySelectorAll('#dashboard > section').forEach((section,index)=>{
      const label=section.querySelector('h2')?.textContent?.replace(/^\s*\d+\.\s*/,'').trim()||('Afsnit '+(index+1));
      result.push({key:moduleKey(section,index),label,nodes:[section]});
    });
    return result;
  }
  function hiddenKeys(){return modules().filter(m=>m.nodes.some(n=>n.hidden)).map(m=>m.key);}
  function currentState(){return{v:3,region:document.getElementById('regionSelect')?.value||'all',fund:document.getElementById('fundSelect')?.value||'',period:document.getElementById('periodSelect')?.value||'',compare:[...document.querySelectorAll('.compareCheck:checked')].map(x=>x.value),hidden:hiddenKeys(),nationalReference:!!document.getElementById('pvNationalReference')?.checked};}
  function save(){if(applying)return;try{localStorage.setItem(STORAGE_KEY,JSON.stringify(currentState()));}catch(_){} }
  function applyVisibility(hidden){const set=new Set(Array.isArray(hidden)?hidden:[]);modules().forEach(m=>m.nodes.forEach(n=>n.hidden=set.has(m.key)));document.querySelectorAll('[data-pv-module]').forEach(input=>input.checked=!set.has(input.value));}
  function refreshChecks(){
    const host=document.getElementById('pvModules');if(!host)return;
    host.innerHTML=modules().map(m=>`<label class="pv-option"><input type="checkbox" data-pv-module value="${m.key}" ${m.nodes.some(n=>n.hidden)?'':'checked'}><span>${m.label}</span></label>`).join('');
    host.querySelectorAll('[data-pv-module]').forEach(input=>input.addEventListener('change',()=>{const mod=modules().find(m=>m.key===input.value);if(!mod)return;mod.nodes.forEach(n=>n.hidden=!input.checked);save();}));
  }

  function injectStyle(){
    if(document.getElementById('regionalPersonalViewStyle'))return;
    const style=document.createElement('style');style.id='regionalPersonalViewStyle';
    style.textContent=`
      .controls.with-regions{grid-template-columns:1.25fr 1.6fr .7fr 1fr auto}
      .regional-notice{display:none;margin:-2px 0 14px;padding:10px 12px;border:1px solid #d8e5dc;border-radius:8px;background:#f4f8f5;color:#405b63;font-size:.82rem;line-height:1.45}
      .regional-notice.show{display:block}.regional-notice strong{color:var(--ink)}
      .regional-unsupported{display:none!important}
      .geography-context{display:flex;align-items:center;gap:4px;width:max-content;max-width:100%;padding:4px 8px;border:1px solid #d8e5dc;border-radius:999px;background:#eef5f0;color:#405b63;font-size:.75rem;line-height:1.2}
      .geography-context span,.geography-context strong{display:inline;margin:0;font-size:inherit;line-height:inherit}.geography-context span{color:#405b63;font-weight:500}.geography-context strong{color:var(--ink);font-weight:700}
      .kpi>.geography-context{margin:7px 0 0}.card>.geography-context{margin:7px 0 11px}
      .regional-no-jobdata #dashboard>.kpis>.kpi:nth-child(n+3){display:none!important}
      .regional-no-jobdata #dashboard>section:nth-of-type(n+3){display:none!important}
      .regional-no-jobdata #dashboard>section:nth-of-type(2) .grid>.card:not(.wide){display:none!important}
      .pv-bar{grid-column:1/-1;display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding-top:2px}.pv-details{position:relative}
      .pv-details>summary,.pv-btn{list-style:none;cursor:pointer;border:1px solid #d6dfd9;border-radius:8px;background:#fff;color:var(--ink);padding:9px 11px;font:inherit;font-weight:650}
      .pv-details>summary::-webkit-details-marker{display:none}.pv-details[open]>summary{border-color:var(--g)}
      .pv-panel{position:absolute;z-index:80;top:calc(100% + 6px);left:0;width:min(380px,88vw);background:#fff;border:1px solid #dfe5e1;border-radius:10px;box-shadow:0 12px 30px rgba(15,43,54,.18);padding:12px}
      .pv-panel strong{display:block;margin-bottom:8px}.pv-option{display:flex;gap:8px;align-items:center;padding:6px 2px;font-size:.84rem}.pv-option input{accent-color:var(--gd)}
      .pv-divider{height:1px;background:var(--grid);margin:9px 0}.pv-ref-option{font-weight:650}.pv-ref-option.is-disabled{opacity:.55}
      .pv-note{font-size:.76rem;color:var(--muted);margin:8px 0 2px;line-height:1.4}.pv-feedback{font-size:.78rem;color:var(--gd);font-weight:650}.pv-btn:hover,.pv-details>summary:hover{background:#f7faf8}
      .national-ref-kpi{margin-top:9px;padding-top:8px;border-top:1px solid var(--grid);font-size:.76rem;color:#405b63;line-height:1.35}.national-ref-kpi strong{display:inline;font-size:inherit;margin:0;color:var(--ink)}
      .national-ref-strip{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:8px 0 12px;font-size:.78rem;color:#405b63}.national-ref-chip{padding:6px 8px;border:1px solid #e0e6e2;border-radius:7px;background:#f7faf8}.national-ref-chip strong{color:var(--ink)}.national-ref-chip.national{border-style:dashed}.national-ref-period{color:var(--muted);font-size:.75rem}
      @media(max-width:1100px){.controls.with-regions{grid-template-columns:1fr 1fr 1fr}}
      @media(max-width:720px){.controls.with-regions{grid-template-columns:1fr}.pv-panel{position:fixed;left:16px;right:16px;top:20%;width:auto;max-height:65vh;overflow:auto}.pv-btn,.pv-details>summary{width:auto}.national-ref-strip{align-items:flex-start}}
    `;
    document.head.appendChild(style);
  }

  function injectRegionControls(){
    const controls=document.querySelector('.controls');if(!controls||document.getElementById('regionSelect'))return;
    controls.classList.add('with-regions');
    const control=document.createElement('div');control.className='control region-control';control.innerHTML='<label for="regionSelect">Geografi</label><select id="regionSelect"></select>';
    const status=document.getElementById('statusPill');controls.insertBefore(control,status||null);
    const select=control.querySelector('select');REGIONS.forEach(([key,label])=>select.add(new Option(label,key)));
    const notice=document.createElement('div');notice.className='regional-notice';notice.id='regionalNotice';controls.parentElement.appendChild(notice);
    select.addEventListener('change',()=>setRegion(select.value).catch(handleRegionError));
  }

  function injectPersonalControls(){
    const controls=document.querySelector('.controls');if(!controls||document.getElementById('pvControls'))return;
    const bar=document.createElement('div');bar.className='pv-bar';bar.id='pvControls';
    bar.innerHTML='<details class="pv-details" id="pvDetails"><summary>Tilpas visning</summary><div class="pv-panel"><strong>Vælg hvad du vil se</strong><div id="pvModules"></div><div class="pv-divider"></div><label class="pv-option pv-ref-option" id="pvNationalReferenceLabel"><input type="checkbox" id="pvNationalReference"><span>Vis hele landet som reference</span></label><div class="pv-note" id="pvNationalReferenceNote">Vælg en region for at sammenligne den valgte a-kasse med samme a-kasse i hele landet.</div><div class="pv-note">Dine valg gemmes kun i denne browser.</div></div></details><button class="pv-btn" id="pvShare" type="button">Del min visning</button><button class="pv-btn" id="pvReset" type="button">Nulstil</button><span class="pv-feedback" id="pvFeedback"></span>';
    controls.appendChild(bar);refreshChecks();
    const details=document.getElementById('pvDetails');details?.addEventListener('mouseleave',()=>details.removeAttribute('open'));
    document.addEventListener('pointerdown',e=>{if(details?.open&&!details.contains(e.target))details.removeAttribute('open');});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&details?.open)details.removeAttribute('open');});
    document.getElementById('pvNationalReference')?.addEventListener('change',e=>{nationalReference=!!e.target.checked;if(typeof draw==='function')draw();save();});
    document.getElementById('pvShare').addEventListener('click',async()=>{const url=new URL(location.href);url.searchParams.set(PARAM,encodeState(currentState()));try{await navigator.clipboard.writeText(url.toString());document.getElementById('pvFeedback').textContent='Link kopieret';}catch(_){prompt('Kopiér dette link',url.toString());}setTimeout(()=>{const f=document.getElementById('pvFeedback');if(f)f.textContent='';},2500);});
    document.getElementById('pvReset').addEventListener('click',()=>{localStorage.removeItem(STORAGE_KEY);localStorage.removeItem('dak-a-kasseindsigt-personal-view-v2');localStorage.removeItem('dak-a-kasseindsigt-personal-view-v1');const url=new URL(location.href);url.searchParams.delete(PARAM);location.replace(url.toString());});
  }

  function setPeriodLimit(regional){const select=document.getElementById('periodSelect');if(!select)return;[...select.options].forEach(option=>{if(Number(option.value)>60){option.disabled=regional;option.hidden=regional;}});}

  function mergedRegionalData(payload){
    const unsupported=new Set(payload.meta?.unsupportedModules||[]),funds={};
    Object.entries(nationalData.funds||{}).forEach(([code,national])=>{
      const regional=payload.funds?.[code]||{},sourceJobs=regional.jobindsats||{},hasRegionalJobs=Object.keys(sourceJobs).length>0,regionalJobs={...sourceJobs};
      if(unsupported.has('exhaustedRights')&&national.jobindsats?.exhaustedRights)regionalJobs.exhaustedRights=national.jobindsats.exhaustedRights;
      funds[code]={...national,members:regional.members||{labels:[],values:[]},profileAge:regional.profileAge||[],unemploymentRate:regional.unemploymentRate||{labels:[],values:[]},jobindsats:regionalJobs,_regionalJobAvailable:hasRegionalJobs};
    });
    return {...nationalData,meta:{...nationalData.meta,sourceStatus:payload.meta.sourceStatus||{},regional:payload.meta},funds};
  }

  async function loadRegion(key){if(regionCache.has(key))return regionCache.get(key);const file=REGION_FILES.get(key);if(!file)throw new Error('Ukendt region');const response=await fetch(file,{cache:'no-store'});if(!response.ok)throw new Error('Regional data kunne ikke hentes (HTTP '+response.status+')');const payload=await response.json();if(!payload?.funds||!payload?.meta)throw new Error('Regional datafil er ugyldig');regionCache.set(key,payload);return payload;}

  function selectedRegionalJobsAvailable(){
    if(activeRegion==='all')return true;
    const code=document.getElementById('fundSelect')?.value;
    return DATA?.funds?.[code]?._regionalJobAvailable!==false;
  }

  function updateAvailability(){document.body.classList.toggle('regional-no-jobdata',activeRegion!=='all'&&!selectedRegionalJobsAvailable());}

  function updateUnsupported(){
    const exhaustedCard=document.getElementById('exhaustedChart')?.closest('.card');if(!exhaustedCard)return;
    const unsupported=activeRegion!=='all'&&(DATA?.meta?.regional?.unsupportedModules||[]).includes('exhaustedRights');
    exhaustedCard.classList.toggle('regional-unsupported',unsupported);
  }

  function referenceActive(){return activeRegion!=='all'&&nationalReference&&!!nationalData;}

  function updateReferenceControl(){
    const input=document.getElementById('pvNationalReference'),label=document.getElementById('pvNationalReferenceLabel'),note=document.getElementById('pvNationalReferenceNote');if(!input)return;
    input.disabled=activeRegion==='all';label?.classList.toggle('is-disabled',input.disabled);
    if(note)note.textContent=input.disabled?'Vælg en region for at sammenligne den valgte a-kasse med samme a-kasse i hele landet.':'Tilføjer hele landet som reference. Procenter og indeks vises i samme figur, mens antal vises som sammenligningstal ved figuren.';
  }

  function clearReferenceUi(){document.querySelectorAll('.national-ref-kpi,.national-ref-strip').forEach(el=>el.remove());}

  function referenceLabel(){const code=document.getElementById('fundSelect')?.value,name=nationalData?.funds?.[code]?.name||fund()?.name||'Valgt a-kasse';return name+' · Hele landet';}
  function regionalLabel(){return (fund()?.name||'Valgt a-kasse')+' · '+(REGION_LABELS.get(activeRegion)||'Valgt region');}
  function hasValues(values){return Array.isArray(values)&&values.some(v=>v!=null&&Number.isFinite(Number(v)));}

  function addNationalLine(chartKey,sourceData,field,useIndex=false){
    const chart=charts?.[chartKey];if(!chart||!sourceData?.labels?.length)return;
    const labels=chart.data.labels||[];let values=mapValues(sourceData,field,labels);if(useIndex)values=indexed(values);if(!hasValues(values))return;
    if(chart.data.datasets?.[0])chart.data.datasets[0].label=regionalLabel();
    chart.data.datasets.push({label:referenceLabel(),data:values,borderColor:C.x,backgroundColor:C.x,borderDash:[6,4],pointRadius:0,borderWidth:2.2,tension:.18,spanGaps:false});
    if(chartKey==='mi'){
      const all=chart.data.datasets.flatMap(s=>Array.isArray(s.data)?s.data:[]).map(Number).filter(Number.isFinite);
      if(all.length){const lowest=Math.min(...all);chart.options.scales.y.min=lowest<80?Math.floor(lowest/5)*5:80;}
    }
    chart.update('none');
  }

  function normalizedItems(items){const total=(items||[]).reduce((sum,item)=>sum+(+item.value||0),0);return(items||[]).map(item=>({label:item.label,value:total?+item.value/total*100:null}));}

  function addNationalBars(chartKey,items,normalize=false){
    const chart=charts?.[chartKey];if(!chart||!Array.isArray(items)||!items.length)return;
    const source=normalize?normalizedItems(items):items,m=new Map(source.map(item=>[item.label,item.value])),values=(chart.data.labels||[]).map(label=>m.has(label)?m.get(label):null);if(!hasValues(values))return;
    if(chart.data.datasets?.[0])chart.data.datasets[0].label=regionalLabel();
    chart.data.datasets.push({label:referenceLabel(),data:values,backgroundColor:C.x,borderColor:C.x,borderWidth:1,borderRadius:4});chart.update('none');
  }

  function alignedPair(regional,national,key){
    const r=last(regional,key);if(!r||!national?.labels?.length||!Array.isArray(national[key]))return null;
    const idx=national.labels.indexOf(r.period);if(idx>=0&&national[key][idx]!=null)return{regional:r,national:{period:r.period,value:national[key][idx]}};
    const n=last(national,key);return n?{regional:r,national:n}:null;
  }

  function addRawReference(canvasId,regional,national,key,formatter=num){
    const canvas=document.getElementById(canvasId),wrap=canvas?.closest('.chart'),pair=alignedPair(regional,national,key);if(!wrap||!pair)return;
    const same=pair.regional.period===pair.national.period,strip=document.createElement('div');strip.className='national-ref-strip';
    strip.innerHTML='<span class="national-ref-chip"><strong>'+REGION_LABELS.get(activeRegion)+':</strong> '+formatter(pair.regional.value)+'</span><span class="national-ref-chip national"><strong>Hele landet:</strong> '+formatter(pair.national.value)+'</span><span class="national-ref-period">'+(same?period(pair.regional.period):period(pair.regional.period)+' / '+period(pair.national.period))+'</span>';
    wrap.parentNode.insertBefore(strip,wrap);
  }

  function addDirectReference(canvasId,regionalValue,nationalValue,formatter){
    const canvas=document.getElementById(canvasId),wrap=canvas?.closest('.chart');if(!wrap||regionalValue==null||nationalValue==null)return;
    const strip=document.createElement('div');strip.className='national-ref-strip';strip.innerHTML='<span class="national-ref-chip"><strong>'+REGION_LABELS.get(activeRegion)+':</strong> '+formatter(regionalValue)+'</span><span class="national-ref-chip national"><strong>Hele landet:</strong> '+formatter(nationalValue)+'</span>';wrap.parentNode.insertBefore(strip,wrap);
  }

  function addKpiReference(id,regional,national,key,formatter){
    const kpi=document.getElementById(id)?.closest('.kpi'),pair=alignedPair(regional,national,key);if(!kpi||!pair)return;
    const div=document.createElement('div');div.className='national-ref-kpi';div.innerHTML='<strong>Hele landet:</strong> '+formatter(pair.national.value)+' · '+period(pair.national.period);kpi.appendChild(div);
  }

  function applyNationalReference(){
    clearReferenceUi();updateReferenceControl();if(!referenceActive())return;
    const code=document.getElementById('fundSelect')?.value,regional=DATA?.funds?.[code],national=nationalData?.funds?.[code];if(!regional||!national)return;

    addNationalLine('mi',national.members,'values',true);
    addNationalBars('age',national.profileAge,true);
    addNationalLine('u',national.unemploymentRate,'values',false);
    addNationalLine('li',national.jobindsats?.longTerm,'persons',true);
    addNationalLine('gs',national.jobindsats?.graduates,'share',false);
    addNationalBars('cons',national.jobindsats?.benefitConsumption?.items||[],true);
    addNationalBars('surv',national.jobindsats?.survival?.items||[],false);
    addNationalBars('status',national.jobindsats?.statusAfter3m?.items||[],false);
    addNationalLine('ac',national.jobindsats?.afterlonContrib,'share',false);
    addNationalLine('ss',national.jobindsats?.sanctions,'shareSanctioned',false);
    addNationalLine('sa',national.jobindsats?.sanctions,'avgPerSanctioned',false);
    addNationalBars('completedDuration',national.jobindsats?.completedDuration?.items||[],true);

    addRawReference('membersRawChart',regional.members,national.members,'values',num);
    addRawReference('longRawChart',regional.jobindsats?.longTerm,national.jobindsats?.longTerm,'persons',num);
    addRawReference('dagChart',regional.jobindsats?.dagpenge,national.jobindsats?.dagpenge,'persons',num);
    addRawReference('gradCountChart',regional.jobindsats?.graduates,national.jobindsats?.graduates,'persons',num);
    addRawReference('exhaustedChart',regional.jobindsats?.exhaustedRights,national.jobindsats?.exhaustedRights,'persons',num);
    addRawReference('talkChart',regional.jobindsats?.talkForms,national.jobindsats?.talkForms,'total',num);
    addRawReference('afterlonChart',regional.jobindsats?.afterlon,national.jobindsats?.afterlon,'persons',num);
    addRawReference('sanctionsTotalChart',regional.jobindsats?.sanctions,national.jobindsats?.sanctions,'total',num);
    addDirectReference('completedDurationChart',regional.jobindsats?.completedDuration?.averageWeeks,national.jobindsats?.completedDuration?.averageWeeks,v=>pf.format(v)+' uger');

    addKpiReference('k1',regional.members,national.members,'values',num);
    addKpiReference('k2',regional.unemploymentRate,national.unemploymentRate,'values',pct);
    addKpiReference('k3',regional.jobindsats?.longTerm,national.jobindsats?.longTerm,'persons',num);
    addKpiReference('k4',regional.jobindsats?.dagpenge,national.jobindsats?.dagpenge,'persons',num);
    addKpiReference('k5',regional.jobindsats?.graduates,national.jobindsats?.graduates,'share',pct);
    addKpiReference('k6',regional.jobindsats?.talkForms,national.jobindsats?.talkForms,'total',num);
  }

  function updateRegionalText(){
    document.querySelectorAll('#dashboard > section').forEach(section=>{const p=section.querySelector(':scope > p');if(p&&!p.dataset.nationalText)p.dataset.nationalText=p.textContent;if(activeRegion==='all'&&p?.dataset.nationalText)p.textContent=p.dataset.nationalText;});
  }

  /* DAK_GEOGRAPHY_CONTEXT_20260903 */
  function geographyLabel(){return REGION_LABELS.get(activeRegion)||'Hele landet';}

  function updateGeographyContext(){
    const label=geographyLabel();
    document.querySelectorAll('#dashboard > .kpis > .kpi, #dashboard .card').forEach(block=>{
      let context=block.querySelector(':scope > .geography-context');
      if(!context){
        context=document.createElement('div');context.className='geography-context';
        const anchor=block.querySelector(':scope > small, :scope > h3');
        if(anchor)anchor.insertAdjacentElement('afterend',context);else block.prepend(context);
      }
      context.textContent='';
      const caption=document.createElement('span'),value=document.createElement('strong');
      caption.textContent='Geografi:';value.textContent=label;context.append(caption,value);
      context.setAttribute('aria-label','Geografi: '+label);
    });
  }

  function updateNotice(message,isError=false){
    const note=document.getElementById('regionalNotice');if(!note)return;if(activeRegion==='all'&&!message){note.className='regional-notice';note.textContent='';return;}
    const name=DATA?.meta?.regional?.areaName||REGION_LABELS.get(activeRegion),unsupported=DATA?.meta?.regional?.unsupportedModules||[],refText=referenceActive()?' Hele landet er slået til som reference for den valgte a-kasse.':'';
    note.className='regional-notice show';
    if(message){note.innerHTML=message;}
    else if(!selectedRegionalJobsAvailable()){
      note.innerHTML='<strong>Regional visning:</strong> DST-tallene vises for '+name+'. Jobindsats har ingen regionale observationer for den valgte a-kasse, så de pågældende afsnit er skjult.'+refText;
    }else{
      note.innerHTML='<strong>Regional visning:</strong> Tallene vises for '+name+' og den valgte a-kasse. Historikken går op til 5 år tilbage.'+(unsupported.includes('exhaustedRights')?' Målingen af opbrugt dagpengeret kan ikke opdeles regionalt i den konkrete Jobindsats-kilde og er derfor skjult.':'')+refText;
    }
    note.style.borderColor=isError?'#e3b7b0':'';
  }

  function wrapDraw(){
    if(drawWrapped||typeof draw!=='function')return;
    const baseDraw=draw;
    draw=function(){
      let restore=null;
      if(activeRegion!=='all'&&!selectedRegionalJobsAvailable()){
        const code=document.getElementById('fundSelect')?.value,regionalFund=DATA?.funds?.[code],nationalFund=nationalData?.funds?.[code];
        if(regionalFund&&nationalFund){restore=regionalFund.jobindsats;regionalFund.jobindsats=nationalFund.jobindsats||{};}
      }
      try{baseDraw();}finally{if(restore!==null){const code=document.getElementById('fundSelect')?.value;if(DATA?.funds?.[code])DATA.funds[code].jobindsats=restore;}}
      updateRegionalText();updateGeographyContext();updateAvailability();updateUnsupported();applyNationalReference();if(activeRegion!=='all')updateNotice();
    };
    drawWrapped=true;
  }

  async function setRegion(key){
    if(!nationalData)return;const select=document.getElementById('regionSelect'),periodSelect=document.getElementById('periodSelect');if(!REGION_FILES.has(key))key='all';
    if(key==='all'){
      activeRegion='all';DATA=nationalData;document.body.classList.remove('regional-no-jobdata');setPeriodLimit(false);if(nationalPeriod&&[...periodSelect.options].some(o=>o.value===String(nationalPeriod)))periodSelect.value=String(nationalPeriod);if(select)select.value='all';updateNotice();updateUnsupported();if(typeof draw==='function')draw();save();return;
    }
    if(activeRegion==='all'){nationalPeriod=periodSelect.value;if(Number(periodSelect.value)<=60)regionalPeriod=periodSelect.value;}else if(Number(periodSelect.value)<=60)regionalPeriod=periodSelect.value;
    activeRegion=key;if(select)select.value=key;setPeriodLimit(true);periodSelect.value=Number(regionalPeriod)<=60?String(regionalPeriod):'60';updateNotice('<strong>Henter '+REGION_LABELS.get(key)+'...</strong>');
    const payload=await loadRegion(key);if(document.getElementById('regionSelect')?.value!==key)return;DATA=mergedRegionalData(payload);updateAvailability();updateNotice();if(typeof draw==='function')draw();save();
  }

  function handleRegionError(error){console.error(error);updateNotice('<strong>Regional visning kunne ikke indlæses.</strong> '+(error?.message||'Ukendt fejl')+'. Landsvisningen er bevaret.',true);activeRegion='all';DATA=nationalData;document.body.classList.remove('regional-no-jobdata');setPeriodLimit(false);const select=document.getElementById('regionSelect');if(select)select.value='all';updateUnsupported();if(typeof draw==='function')draw();}

  async function applyState(state){
    if(!state)return;applying=true;const fund=document.getElementById('fundSelect'),periodSelect=document.getElementById('periodSelect'),ref=document.getElementById('pvNationalReference');
    if(state.fund&&fund&&[...fund.options].some(o=>o.value===state.fund))fund.value=state.fund;if(state.period&&periodSelect&&[...periodSelect.options].some(o=>o.value===String(state.period)))periodSelect.value=String(state.period);
    if(Array.isArray(state.compare))document.querySelectorAll('.compareCheck').forEach(x=>x.checked=state.compare.includes(x.value));applyVisibility(state.hidden||[]);nationalReference=!!state.nationalReference;if(ref)ref.checked=nationalReference;
    const region=REGION_FILES.has(state.region)?state.region:'all';if(region!=='all'&&Number(periodSelect.value)<=60)regionalPeriod=periodSelect.value;try{await setRegion(region);}catch(error){handleRegionError(error);}if(typeof draw==='function')draw();refreshChecks();updateReferenceControl();applying=false;save();
  }

  function bindSave(){
    const redrawReference=()=>setTimeout(()=>{save();if(referenceActive()&&typeof draw==='function')draw();},0);
    document.getElementById('fundSelect')?.addEventListener('change',redrawReference);
    document.getElementById('periodSelect')?.addEventListener('change',()=>{if(activeRegion==='all')nationalPeriod=document.getElementById('periodSelect').value;else regionalPeriod=document.getElementById('periodSelect').value;redrawReference();});
    document.getElementById('compareOptions')?.addEventListener('change',redrawReference);
    document.getElementById('regionSelect')?.addEventListener('change',()=>setTimeout(save,0));
  }
  function ready(){return typeof DATA!=='undefined'&&DATA&&document.getElementById('fundSelect')?.options.length>0&&!document.getElementById('dashboard')?.hidden;}
  async function start(){injectStyle();injectRegionControls();if(!ready()){setTimeout(start,80);return;}if(!nationalData){nationalData=DATA;nationalPeriod=document.getElementById('periodSelect')?.value||'36';}wrapDraw();injectPersonalControls();updateGeographyContext();bindSave();const state=sharedState()||storedState();if(state)await applyState(state);else{refreshChecks();updateReferenceControl();save();}}
  start();
})();
