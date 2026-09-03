(function(){
  'use strict';
  const STORAGE_KEY='dak-a-kasseindsigt-personal-view-v4';
  const PARAM='pv';
  const COMPARISON_CODE='__dak_cross_geography_comparison__';
  const COMPARISON_SENTINEL='__DAK_COMPARISON__';
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
  const GEOGRAPHY_MODULES=new Map([
    ['k1','members'],['k2','unemploymentRate'],['k3','longTerm'],['k4','dagpenge'],['k5','graduates'],['k6','talkForms'],
    ['membersRawChart','members'],['membersIndexChart','members'],['ageChart','profileAge'],['unempChart','unemploymentRate'],
    ['longRawChart','longTerm'],['longIndexChart','longTerm'],['dagChart','dagpenge'],['gradCountChart','graduates'],['gradChart','graduates'],
    ['consChart','benefitConsumption'],['exhaustedChart','exhaustedRights'],['survChart','survival'],['completedDurationChart','completedDuration'],
    ['statusChart','statusAfter3m'],['talkChart','talkForms'],['afterlonChart','afterlon'],['afterlonContribChart','afterlonContrib'],
    ['sanctionsTotalChart','sanctions'],['sanctionsShareChart','sanctions'],['sanctionsTypeChart','sanctions'],['sanctionsAvgChart','sanctions'],
    ['mr','members'],['mi','members'],['age','profileAge'],['u','unemploymentRate'],['lr','longTerm'],['li','longTerm'],
    ['d','dagpenge'],['gc','graduates'],['gs','graduates'],['cons','benefitConsumption'],['ex','exhaustedRights'],
    ['surv','survival'],['completedDuration','completedDuration'],['status','statusAfter3m'],['talk','talkForms'],
    ['al','afterlon'],['ac','afterlonContrib'],['st','sanctions'],['ss','sanctions'],['sty','sanctions'],['sa','sanctions']
  ]);
  const regionCache=new Map();
  const mergedRegionCache=new Map();
  let applying=false;
  let nationalData=null;
  let activeRegion='all';
  let nationalPeriod=null;
  let regionalPeriod='60';
  let comparisonFundCode='';
  let comparisonRegionChoice='same';
  let comparisonData=null;
  let comparisonDataRegion=null;
  let comparisonLoadToken=0;
  let drawingComparisonPair=null;
  let comparisonBridgeInstalled=false;
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
  function storedState(){try{return JSON.parse(localStorage.getItem(STORAGE_KEY)||localStorage.getItem('dak-a-kasseindsigt-personal-view-v3')||localStorage.getItem('dak-a-kasseindsigt-personal-view-v2')||localStorage.getItem('dak-a-kasseindsigt-personal-view-v1')||'null');}catch(_){return null;}}
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
  function currentState(){return{v:4,region:document.getElementById('regionSelect')?.value||'all',fund:document.getElementById('fundSelect')?.value||'',period:document.getElementById('periodSelect')?.value||'',comparisonFund:comparisonFundCode,comparisonRegion:comparisonRegionChoice,hidden:hiddenKeys()};}
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
      .geography-context,.comparison-context{display:inline-flex;align-items:center;flex-wrap:wrap;gap:4px;width:max-content;max-width:100%;padding:4px 8px;border:1px solid #d8e5dc;border-radius:999px;background:#eef5f0;color:#405b63;font-size:.75rem;line-height:1.2;vertical-align:middle}
      .geography-context span,.geography-context strong,.comparison-context span,.comparison-context strong{display:inline;margin:0;font-size:inherit;line-height:inherit}.geography-context span,.comparison-context span{color:#405b63;font-weight:500}.geography-context strong,.comparison-context strong{color:var(--ink);font-weight:700}
      .geography-context.is-national-fallback{border-color:#e8c9a9;background:#fff7ed}.geography-context.is-national-fallback .geography-context-note{color:#7a4b22;font-weight:650}
      .comparison-context{border-color:#c8ddeb;background:#f2f7fb}.comparison-context.is-national-fallback{border-color:#e8c9a9;background:#fff7ed}.comparison-context.is-unavailable{border-color:#d8d8d8;background:#f6f6f6}.comparison-context .comparison-context-note{font-weight:650}
      .kpi>.geography-context,.kpi>.comparison-context{margin:7px 6px 0 0}.card>.geography-context,.card>.comparison-context{margin:7px 6px 11px 0}
      .compare-menu.comparison-menu{max-height:none;overflow:visible;padding:12px}.comparison-builder{display:grid;gap:10px}.comparison-field{display:grid;gap:5px;color:var(--muted);font-size:.78rem;font-weight:700}.comparison-field select{width:100%;min-height:40px}.comparison-note{font-size:.75rem;color:var(--muted);line-height:1.4}.comparison-note.error{color:#9a3f32}.comparison-note strong{color:var(--ink)}
      .pv-bar{grid-column:1/-1;display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding-top:2px}.pv-details{position:relative}
      .pv-details>summary,.pv-btn{list-style:none;cursor:pointer;border:1px solid #d6dfd9;border-radius:8px;background:#fff;color:var(--ink);padding:9px 11px;font:inherit;font-weight:650}
      .pv-details>summary::-webkit-details-marker{display:none}.pv-details[open]>summary{border-color:var(--g)}
      .pv-panel{position:absolute;z-index:80;top:calc(100% + 6px);left:0;width:min(380px,88vw);background:#fff;border:1px solid #dfe5e1;border-radius:10px;box-shadow:0 12px 30px rgba(15,43,54,.18);padding:12px}
      .pv-panel strong{display:block;margin-bottom:8px}.pv-option{display:flex;gap:8px;align-items:center;padding:6px 2px;font-size:.84rem}.pv-option input{accent-color:var(--gd)}
      .pv-divider{height:1px;background:var(--grid);margin:9px 0}
      .pv-note{font-size:.76rem;color:var(--muted);margin:8px 0 2px;line-height:1.4}.pv-feedback{font-size:.78rem;color:var(--gd);font-weight:650}.pv-btn:hover,.pv-details>summary:hover{background:#f7faf8}
      .comparison-kpi{margin-top:9px;padding-top:8px;border-top:1px solid var(--grid);font-size:.76rem;color:#405b63;line-height:1.35}.comparison-kpi strong{display:inline;font-size:inherit;margin:0;color:var(--ink)}
      .comparison-strip{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:8px 0 12px;font-size:.78rem;color:#405b63}.comparison-chip{padding:6px 8px;border:1px dashed #bdd4e3;border-radius:7px;background:#f2f7fb}.comparison-chip strong{color:var(--ink)}.comparison-period{color:var(--muted);font-size:.75rem}
      @media(max-width:1100px){.controls.with-regions{grid-template-columns:1fr 1fr 1fr}}
      @media(max-width:720px){.controls.with-regions{grid-template-columns:1fr}.pv-panel{position:fixed;left:16px;right:16px;top:20%;width:auto;max-height:65vh;overflow:auto}.pv-btn,.pv-details>summary{width:auto}.comparison-strip{align-items:flex-start}}
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

  /* DAK_CROSS_GEOGRAPHY_COMPARE_20260903 */
  function injectComparisonControls(){
    const host=document.getElementById('compareOptions');if(!host||document.getElementById('comparisonFundSelect'))return;
    host.classList.add('comparison-menu');
    host.innerHTML='<div class="comparison-builder"><label class="comparison-field"><span>Enhed</span><select id="comparisonFundSelect"></select></label><label class="comparison-field"><span>Geografi</span><select id="comparisonRegionSelect"></select></label><div class="comparison-note" id="comparisonNote">Der vises én sammenligning ad gangen.</div></div>';
    const fundSelect=document.getElementById('comparisonFundSelect'),regionSelect=document.getElementById('comparisonRegionSelect'),total=nationalData?.meta?.totalFundCode;
    fundSelect.add(new Option('Ingen sammenligning',''));
    if(total&&nationalData?.funds?.[total])fundSelect.add(new Option('I alt',total));
    Object.entries(nationalData?.funds||{}).filter(([code])=>code!==total).sort((a,b)=>a[1].name.localeCompare(b[1].name,'da')).forEach(([code,item])=>fundSelect.add(new Option(item.name,code)));
    regionSelect.add(new Option('Samme geografi som hovedvalget','same'));
    REGIONS.forEach(([key,label])=>regionSelect.add(new Option(label,key)));
    comparisonFundCode=total&&nationalData?.funds?.[total]?total:'';comparisonRegionChoice='same';
    fundSelect.value=comparisonFundCode;regionSelect.value=comparisonRegionChoice;
    fundSelect.addEventListener('change',()=>setComparisonSelection(fundSelect.value,regionSelect.value).catch(handleComparisonError));
    regionSelect.addEventListener('change',()=>setComparisonSelection(fundSelect.value,regionSelect.value).catch(handleComparisonError));
    updateComparisonControls();
  }

  function updateSameRegionOption(){
    const select=document.getElementById('comparisonRegionSelect'),option=select?.querySelector('option[value="same"]');
    if(option)option.textContent='Samme geografi som hovedvalget ('+(REGION_LABELS.get(activeRegion)||'Hele landet')+')';
  }

  function updateComparisonControls(message='',isError=false){
    const fundSelect=document.getElementById('comparisonFundSelect'),regionSelect=document.getElementById('comparisonRegionSelect'),note=document.getElementById('comparisonNote');
    if(fundSelect&&fundSelect.value!==comparisonFundCode)fundSelect.value=comparisonFundCode;
    if(regionSelect){if(regionSelect.value!==comparisonRegionChoice)regionSelect.value=comparisonRegionChoice;regionSelect.disabled=!comparisonFundCode;}
    updateSameRegionOption();
    if(note){
      const sameChoice=comparisonFundCode===document.getElementById('fundSelect')?.value&&resolvedComparisonRegion()===activeRegion;
      const isTotal=comparisonFundCode===nationalData?.meta?.totalFundCode;
      const defaultMessage=!comparisonFundCode?'Vælg I alt eller en a-kasse for at tilføje en sammenligning.':sameChoice?'Sammenligningen er identisk med hovedvalget. Vælg en anden a-kasse eller geografi.':isTotal?'I alt vises direkte i procenter, indeks og fordelinger samt som tydelige sammenligningstal ved grafer med rå antal.':'Der vises én sammenligning ad gangen.';
      note.classList.toggle('error',isError);note.textContent=message||defaultMessage;
    }
    updateComparisonSummary();
  }

  function injectPersonalControls(){
    const controls=document.querySelector('.controls');if(!controls||document.getElementById('pvControls'))return;
    const bar=document.createElement('div');bar.className='pv-bar';bar.id='pvControls';
    bar.innerHTML='<details class="pv-details" id="pvDetails"><summary>Tilpas visning</summary><div class="pv-panel"><strong>Vælg hvad du vil se</strong><div id="pvModules"></div><div class="pv-divider"></div><div class="pv-note">Dine valg gemmes kun i denne browser.</div></div></details><button class="pv-btn" id="pvShare" type="button">Del min visning</button><button class="pv-btn" id="pvReset" type="button">Nulstil</button><span class="pv-feedback" id="pvFeedback"></span>';
    controls.appendChild(bar);refreshChecks();
    const details=document.getElementById('pvDetails');details?.addEventListener('mouseleave',()=>details.removeAttribute('open'));
    document.addEventListener('pointerdown',e=>{if(details?.open&&!details.contains(e.target))details.removeAttribute('open');});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&details?.open)details.removeAttribute('open');});
    document.getElementById('pvShare').addEventListener('click',async()=>{const url=new URL(location.href);url.searchParams.set(PARAM,encodeState(currentState()));try{await navigator.clipboard.writeText(url.toString());document.getElementById('pvFeedback').textContent='Link kopieret';}catch(_){prompt('Kopiér dette link',url.toString());}setTimeout(()=>{const f=document.getElementById('pvFeedback');if(f)f.textContent='';},2500);});
    document.getElementById('pvReset').addEventListener('click',()=>{localStorage.removeItem(STORAGE_KEY);localStorage.removeItem('dak-a-kasseindsigt-personal-view-v3');localStorage.removeItem('dak-a-kasseindsigt-personal-view-v2');localStorage.removeItem('dak-a-kasseindsigt-personal-view-v1');const url=new URL(location.href);url.searchParams.delete(PARAM);location.replace(url.toString());});
  }

  function setPeriodLimit(regional){const select=document.getElementById('periodSelect');if(!select)return;[...select.options].forEach(option=>{if(Number(option.value)>60){option.disabled=regional;option.hidden=regional;}});}

  function mergedRegionalData(payload){
    const unsupported=new Set(payload.meta?.unsupportedModules||[]),funds={};
    Object.entries(nationalData.funds||{}).forEach(([code,national])=>{
      const regional=payload.funds?.[code]||{},sourceJobs=regional.jobindsats||{},nationalJobs=national.jobindsats||{},hasRegionalJobs=Object.keys(sourceJobs).length>0,regionalJobs={...sourceJobs},nationalFallbackModules=new Set();
      if(!hasRegionalJobs)Object.keys(nationalJobs).forEach(module=>nationalFallbackModules.add(module));
      unsupported.forEach(module=>{if(nationalJobs[module]){regionalJobs[module]=nationalJobs[module];nationalFallbackModules.add(module);}});
      funds[code]={...national,members:regional.members||{labels:[],values:[]},profileAge:regional.profileAge||[],unemploymentRate:regional.unemploymentRate||{labels:[],values:[]},jobindsats:regionalJobs,_regionalJobAvailable:hasRegionalJobs,_nationalFallbackModules:[...nationalFallbackModules]};
    });
    return {...nationalData,meta:{...nationalData.meta,sourceStatus:payload.meta.sourceStatus||{},regional:payload.meta},funds};
  }

  async function loadRegion(key){if(regionCache.has(key))return regionCache.get(key);const file=REGION_FILES.get(key);if(!file)throw new Error('Ukendt region');const response=await fetch(file,{cache:'no-store'});if(!response.ok)throw new Error('Regional data kunne ikke hentes (HTTP '+response.status+')');const payload=await response.json();if(!payload?.funds||!payload?.meta)throw new Error('Regional datafil er ugyldig');regionCache.set(key,payload);return payload;}

  function resolvedComparisonRegion(){return comparisonRegionChoice==='same'?activeRegion:comparisonRegionChoice;}

  async function dataForRegion(key){
    if(key==='all')return nationalData;
    if(key===activeRegion&&DATA)return DATA;
    if(mergedRegionCache.has(key))return mergedRegionCache.get(key);
    const merged=mergedRegionalData(await loadRegion(key));mergedRegionCache.set(key,merged);return merged;
  }

  async function ensureComparisonData(){
    const key=resolvedComparisonRegion(),token=++comparisonLoadToken;
    if(!comparisonFundCode||key===activeRegion||key==='all'){
      comparisonData=key==='all'?nationalData:DATA;comparisonDataRegion=key;return true;
    }
    updateComparisonControls('Henter '+(REGION_LABELS.get(key)||'sammenligningsdata')+'...');
    try{
      const data=await dataForRegion(key);if(token!==comparisonLoadToken)return false;
      comparisonData=data;comparisonDataRegion=key;updateComparisonControls();return true;
    }catch(error){
      if(token!==comparisonLoadToken)return false;
      comparisonData=null;comparisonDataRegion=null;throw error;
    }
  }

  async function setComparisonSelection(fundCode,regionChoice,redraw=true){
    comparisonFundCode=nationalData?.funds?.[fundCode]?fundCode:'';
    comparisonRegionChoice=regionChoice==='same'||REGION_FILES.has(regionChoice)?regionChoice:'same';
    updateComparisonControls();
    await ensureComparisonData();
    if(redraw&&typeof draw==='function')draw();
    save();
  }

  function handleComparisonError(error,redraw=true){
    console.error(error);updateComparisonControls('Sammenligningen kunne ikke indlæses: '+(error?.message||'ukendt fejl')+'.',true);
    if(redraw&&typeof draw==='function')draw();
  }

  function comparisonDataset(){
    const key=resolvedComparisonRegion();
    if(key===activeRegion)return DATA;
    if(key==='all')return nationalData;
    return comparisonDataRegion===key?comparisonData:null;
  }

  function effectiveFund(source,code,regionKey){
    if(!source)return null;
    if(regionKey!=='all'&&source._regionalJobAvailable===false){
      return{...source,jobindsats:nationalData?.funds?.[code]?.jobindsats||{}};
    }
    return source;
  }

  function effectivePrimaryFund(){
    const code=document.getElementById('fundSelect')?.value,source=DATA?.funds?.[code];
    return effectiveFund(source,code,activeRegion);
  }

  function comparisonPair(){
    if(!comparisonFundCode)return null;
    const regionKey=resolvedComparisonRegion(),dataset=comparisonDataset(),sourceFund=dataset?.funds?.[comparisonFundCode],primaryCode=document.getElementById('fundSelect')?.value;
    if(!sourceFund||(comparisonFundCode===primaryCode&&regionKey===activeRegion))return null;
    return{fundCode:comparisonFundCode,regionKey,sourceFund,drawFund:effectiveFund(sourceFund,comparisonFundCode,regionKey)};
  }

  function moduleForTarget(target){return GEOGRAPHY_MODULES.get(target)||target||'';}
  function moduleData(fundData,module){
    if(!fundData)return null;
    if(module==='members'||module==='profileAge'||module==='unemploymentRate')return fundData[module];
    return fundData.jobindsats?.[module];
  }
  function moduleHasData(fundData,module){
    const value=moduleData(fundData,module);
    if(Array.isArray(value))return value.length>0;
    if(!value||typeof value!=='object')return false;
    if(Array.isArray(value.labels))return value.labels.length>0;
    if(Array.isArray(value.items))return value.items.length>0;
    return Object.keys(value).length>0;
  }
  function fundModuleUsesNational(fundData,regionKey,target){
    const module=moduleForTarget(target),fallback=fundData?._nationalFallbackModules;
    return regionKey!=='all'&&!!module&&Array.isArray(fallback)&&fallback.includes(module);
  }
  function entityLabel(code,item){return code===nationalData?.meta?.totalFundCode?'I alt':(item?.name||'Valgt a-kasse');}
  function actualRegionKey(fundData,regionKey,module){return fundModuleUsesNational(fundData,regionKey,module)?'all':regionKey;}
  function seriesLabel(code,fundData,regionKey,module){return entityLabel(code,fundData)+' · '+(REGION_LABELS.get(actualRegionKey(fundData,regionKey,module))||'Valgt geografi');}
  function primarySeriesLabel(module){const code=document.getElementById('fundSelect')?.value,source=DATA?.funds?.[code];return seriesLabel(code,source,activeRegion,module);}
  function comparisonSeriesLabel(pair,module){return seriesLabel(pair.fundCode,pair.sourceFund,pair.regionKey,module);}

  function selectedRegionalJobsAvailable(){
    if(activeRegion==='all')return true;
    const code=document.getElementById('fundSelect')?.value;
    return DATA?.funds?.[code]?._regionalJobAvailable!==false;
  }

  function updateAvailability(){document.body.classList.toggle('regional-no-jobdata',activeRegion!=='all'&&!selectedRegionalJobsAvailable());}

  function updateUnsupported(){
    document.querySelectorAll('.regional-unsupported').forEach(card=>card.classList.remove('regional-unsupported'));
  }

  function hasValues(values){return Array.isArray(values)&&values.some(v=>v!=null&&Number.isFinite(Number(v)));}

  function alignedPair(regional,national,key){
    const r=last(regional,key);if(!r||!national?.labels?.length||!Array.isArray(national[key]))return null;
    const idx=national.labels.indexOf(r.period);if(idx>=0&&national[key][idx]!=null)return{regional:r,national:{period:r.period,value:national[key][idx]}};
    const n=last(national,key);return n?{regional:r,national:n}:null;
  }

  function installComparisonBridge(){
    if(comparisonBridgeInstalled)return;
    compareCodes=function(){return drawingComparisonPair&&DATA?.funds?.[COMPARISON_CODE]?[COMPARISON_CODE]:[];};
    rawCompareCodes=function(){return drawingComparisonPair&&drawingComparisonPair.fundCode!==nationalData?.meta?.totalFundCode&&DATA?.funds?.[COMPARISON_CODE]?[COMPARISON_CODE]:[];};
    updateCompareSummary=function(){updateComparisonSummary();};
    comparisonBridgeInstalled=true;
  }

  function updateComparisonSummary(){
    const summary=document.getElementById('compareSummary');if(!summary)return;
    let label='Ingen sammenligning';
    if(comparisonFundCode){
      const regionKey=resolvedComparisonRegion(),dataset=comparisonDataset(),item=dataset?.funds?.[comparisonFundCode],primaryCode=document.getElementById('fundSelect')?.value;
      if(!dataset)label='Henter sammenligning...';
      else if(comparisonFundCode===primaryCode&&regionKey===activeRegion)label='Samme som hovedvalget';
      else if(item)label=entityLabel(comparisonFundCode,item)+' · '+(REGION_LABELS.get(regionKey)||'Valgt geografi');
      else label='Sammenligning ikke tilgængelig';
    }
    summary.textContent=label;summary.title=label;
  }

  function clearComparisonUi(){document.querySelectorAll('.comparison-kpi,.comparison-strip,.comparison-context').forEach(el=>el.remove());}

  function appendComparisonContext(block,pair){
    const target=geographyTarget(block),module=moduleForTarget(target),available=moduleHasData(pair.drawFund,module),fallback=fundModuleUsesNational(pair.sourceFund,pair.regionKey,module);
    const context=document.createElement('div');context.className='comparison-context';context.classList.toggle('is-national-fallback',fallback);context.classList.toggle('is-unavailable',!available);
    const caption=document.createElement('span'),value=document.createElement('strong');caption.textContent='Sammenligning:';value.textContent=comparisonSeriesLabel(pair,module);context.append(caption,value);
    if(fallback){const note=document.createElement('span');note.className='comparison-context-note';note.textContent='· ikke regionalt tilgængelig';context.append(note);}
    if(!available){const note=document.createElement('span');note.className='comparison-context-note';note.textContent='· data ikke tilgængelige';context.append(note);}
    const geography=block.querySelector(':scope > .geography-context'),anchor=geography||block.querySelector(':scope > small, :scope > h3');
    if(anchor)anchor.insertAdjacentElement('afterend',context);else block.prepend(context);
    context.setAttribute('aria-label','Sammenligning: '+comparisonSeriesLabel(pair,module)+(fallback?', ikke regionalt tilgængelig':'')+(!available?', data ikke tilgængelige':''));
  }

  function updateComparisonContexts(pair){
    document.querySelectorAll('.comparison-context').forEach(el=>el.remove());if(!pair)return;
    document.querySelectorAll('#dashboard > .kpis > .kpi, #dashboard .card').forEach(block=>appendComparisonContext(block,pair));
  }

  function addComparisonLine(chartKey,module,field,pair){
    const chart=charts?.[chartKey],source=moduleData(pair.drawFund,module);if(!chart||!source?.labels?.length)return;
    const values=mapValues(source,field,chart.data.labels||[]);if(!hasValues(values))return;
    chart.data.datasets.push({label:COMPARISON_SENTINEL,data:values,borderColor:C.b,backgroundColor:C.b,borderDash:[6,4],pointRadius:0,borderWidth:2.2,tension:.18,spanGaps:false});
  }

  function addTalkComparison(pair){
    const chart=charts?.talk,source=moduleData(pair.drawFund,'talkForms');if(!chart||!source?.labels?.length)return;
    const mainLabel=primarySeriesLabel('talkForms'),otherLabel=comparisonSeriesLabel(pair,'talkForms'),defs=[['Fysisk','physical',C.gd],['Telefon','phone',C.b],['Video','video',C.o],['Anden kontakt','other',C.p]];
    chart.data.datasets.forEach((set,index)=>{if(defs[index])set.label=defs[index][0]+' · '+mainLabel;});
    defs.forEach(([label,key,col])=>{const values=mapValues(source,key,chart.data.labels||[]);if(hasValues(values))chart.data.datasets.push({label:label+' · '+otherLabel,data:values,borderColor:col,backgroundColor:col,borderDash:[6,4],pointRadius:0,borderWidth:2,tension:.18,spanGaps:false});});
  }

  function addSanctionTypeComparison(pair){
    const chart=charts?.sty,source=moduleData(pair.drawFund,'sanctions');if(!chart||!source?.labels?.length||!Array.isArray(source.types))return;
    const wanted=chart.data.labels||[],idx=source.labels.length-1,map=new Map(source.types.map(item=>[item.label,Array.isArray(item.values)?item.values[idx]:null])),values=wanted.map(label=>map.has(label)?map.get(label):null);if(!hasValues(values))return;
    chart.data.datasets.push({label:COMPARISON_SENTINEL,data:values,backgroundColor:C.b,borderColor:C.b,borderWidth:1,borderRadius:4});
  }

  function updateChartDatasetLabels(pair){
    const primaryCode=document.getElementById('fundSelect')?.value,primaryName=DATA?.funds?.[primaryCode]?.name;
    Object.entries(charts||{}).forEach(([key,chart])=>{
      const module=moduleForTarget(key);if(!module||!chart?.data?.datasets)return;
      chart.data.datasets.forEach(set=>{if(set.label===COMPARISON_SENTINEL)set.label=comparisonSeriesLabel(pair,module);else if(set.label===primaryName)set.label=primarySeriesLabel(module);});
      chart.update('none');
    });
  }

  function appendStrip(wrap,entries,periodText=''){
    if(!wrap||!entries.length)return;const strip=document.createElement('div');strip.className='comparison-strip';
    entries.forEach(entry=>{const chip=document.createElement('span'),strong=document.createElement('strong');chip.className='comparison-chip';strong.textContent=entry.label+':';chip.append(strong,document.createTextNode(' '+entry.value));strip.append(chip);});
    if(periodText){const when=document.createElement('span');when.className='comparison-period';when.textContent=periodText;strip.append(when);}
    wrap.parentNode.insertBefore(strip,wrap);
  }

  function addSeriesStrip(canvasId,module,primarySeries,comparisonSeries,key,pair,formatter=num){
    const wrap=document.getElementById(canvasId)?.closest('.chart'),values=alignedPair(primarySeries,comparisonSeries,key);if(!wrap||!values)return;
    const same=values.regional.period===values.national.period;
    appendStrip(wrap,[{label:primarySeriesLabel(module),value:formatter(values.regional.value)},{label:comparisonSeriesLabel(pair,module),value:formatter(values.national.value)}],same?period(values.regional.period):period(values.regional.period)+' / '+period(values.national.period));
  }

  function addDirectStrip(canvasId,module,primaryValue,comparisonValue,pair,formatter,periodText=''){
    const wrap=document.getElementById(canvasId)?.closest('.chart');if(!wrap||primaryValue==null||comparisonValue==null)return;
    appendStrip(wrap,[{label:primarySeriesLabel(module),value:formatter(primaryValue)},{label:comparisonSeriesLabel(pair,module),value:formatter(comparisonValue)}],periodText);
  }

  function addComparisonKpis(pair){
    const primary=effectivePrimaryFund(),specs=[['k1','members','values',num],['k2','unemploymentRate','values',pct],['k3','longTerm','persons',num],['k4','dagpenge','persons',num],['k5','graduates','share',pct],['k6','talkForms','total',num]];
    specs.forEach(([id,module,key,formatter])=>{
      const block=document.getElementById(id)?.closest('.kpi'),values=alignedPair(moduleData(primary,module),moduleData(pair.drawFund,module),key);if(!block||!values)return;
      const row=document.createElement('div'),strong=document.createElement('strong');row.className='comparison-kpi';strong.textContent='Sammenligning:';row.append(strong,document.createTextNode(' '+comparisonSeriesLabel(pair,module)+': '+formatter(values.national.value)+' · '+period(values.national.period)));block.append(row);
    });
  }

  function addTotalComparisonStrips(pair){
    const primary=effectivePrimaryFund(),other=pair.drawFund,specs=[
      ['membersRawChart','members','values',num],['longRawChart','longTerm','persons',num],['dagChart','dagpenge','persons',num],['gradCountChart','graduates','persons',num],
      ['exhaustedChart','exhaustedRights','persons',num],['afterlonChart','afterlon','persons',num],['sanctionsTotalChart','sanctions','total',num]
    ];
    specs.forEach(([id,module,key,formatter])=>addSeriesStrip(id,module,moduleData(primary,module),moduleData(other,module),key,pair,formatter));
    addTalkTotalStrip(primary,other,pair);
  }

  function addTalkTotalStrip(primary,other,pair){
    const main=moduleData(primary,'talkForms'),comparison=moduleData(other,'talkForms'),wrap=document.getElementById('talkChart')?.closest('.chart'),latest=last(main,'total');if(!wrap||!latest||!comparison?.labels?.length)return;
    const mainIndex=main.labels.indexOf(latest.period),comparisonIndex=comparison.labels.includes(latest.period)?comparison.labels.indexOf(latest.period):comparison.labels.length-1,comparisonPeriod=comparison.labels[comparisonIndex],defs=[['Fysisk','physical'],['Telefon','phone'],['Video','video'],['Anden kontakt','other']];
    const entries=defs.map(([label,key])=>({label,value:num(main[key]?.[mainIndex])+' / '+num(comparison[key]?.[comparisonIndex])}));
    appendStrip(wrap,entries,'Hovedserie / sammenligning · '+(latest.period===comparisonPeriod?period(latest.period):period(latest.period)+' / '+period(comparisonPeriod)));
  }

  function addSanctionTypeStrip(pair){
    const source=moduleData(pair.drawFund,'sanctions'),wrap=document.getElementById('sanctionsTypeChart')?.closest('.chart');if(!wrap||!source?.labels?.length||!Array.isArray(source.types))return;
    const idx=source.labels.length-1,label=comparisonSeriesLabel(pair,'sanctions'),entries=source.types.map(item=>({label:label+' · '+item.label,value:num(Array.isArray(item.values)?item.values[idx]:null)}));appendStrip(wrap,entries,period(source.labels[idx]));
  }

  function applyComparison(pair){
    clearComparisonUi();updateComparisonSummary();updateComparisonContexts(pair);if(!pair)return;
    const isTotal=pair.fundCode===nationalData?.meta?.totalFundCode;
    if(isTotal){addTotalComparisonStrips(pair);addSanctionTypeStrip(pair);}else{addTalkComparison(pair);addComparisonLine('st','sanctions','total',pair);addSanctionTypeComparison(pair);}
    const primaryDuration=moduleData(effectivePrimaryFund(),'completedDuration'),otherDuration=moduleData(pair.drawFund,'completedDuration');
    const primaryDurationPeriod=primaryDuration?.period||'',otherDurationPeriod=otherDuration?.period||'',durationPeriod=primaryDurationPeriod&&otherDurationPeriod&&primaryDurationPeriod!==otherDurationPeriod?period(primaryDurationPeriod)+' / '+period(otherDurationPeriod):period(primaryDurationPeriod||otherDurationPeriod||'');
    addDirectStrip('completedDurationChart','completedDuration',primaryDuration?.averageWeeks,otherDuration?.averageWeeks,pair,value=>pf.format(value)+' uger',durationPeriod);
    updateChartDatasetLabels(pair);addComparisonKpis(pair);
  }

  function updateRegionalText(){
    document.querySelectorAll('#dashboard > section').forEach(section=>{const p=section.querySelector(':scope > p');if(p&&!p.dataset.nationalText)p.dataset.nationalText=p.textContent;if(activeRegion==='all'&&p?.dataset.nationalText)p.textContent=p.dataset.nationalText;});
  }

  /* DAK_GEOGRAPHY_CONTEXT_20260903 */
  function moduleUsesNational(target){return fundModuleUsesNational(fund(),activeRegion,target);}

  function geographyTarget(block){
    const node=block.matches('.kpi')?block.querySelector(':scope > strong[id]'):block.querySelector('canvas[id]');
    return node?.id||'';
  }

  function updateGeographyContext(){
    document.querySelectorAll('#dashboard > .kpis > .kpi, #dashboard .card').forEach(block=>{
      const fallback=moduleUsesNational(geographyTarget(block)),label=activeRegion==='all'||fallback?'Hele landet':(REGION_LABELS.get(activeRegion)||'Valgt region');
      let context=block.querySelector(':scope > .geography-context');
      if(!context){
        context=document.createElement('div');context.className='geography-context';
        const anchor=block.querySelector(':scope > small, :scope > h3');
        if(anchor)anchor.insertAdjacentElement('afterend',context);else block.prepend(context);
      }
      context.textContent='';context.classList.toggle('is-national-fallback',fallback);
      const caption=document.createElement('span'),value=document.createElement('strong');
      caption.textContent='Geografi:';value.textContent=label;context.append(caption,value);
      if(fallback){const explanation=document.createElement('span');explanation.className='geography-context-note';explanation.textContent='· ikke regionalt tilgængelig';context.append(explanation);}
      context.setAttribute('aria-label','Geografi: '+label+(fallback?', ikke regionalt tilgængelig':''));
    });
  }

  function updateNotice(message,isError=false){
    const note=document.getElementById('regionalNotice');if(!note)return;if(activeRegion==='all'&&!message){note.className='regional-notice';note.textContent='';return;}
    const name=DATA?.meta?.regional?.areaName||REGION_LABELS.get(activeRegion),unsupported=DATA?.meta?.regional?.unsupportedModules||[];
    note.className='regional-notice show';
    if(message){note.innerHTML=message;}
    else if(!selectedRegionalJobsAvailable()){
      note.innerHTML='<strong>Regional visning:</strong> DST-tallene vises for '+name+'. Jobindsats har ingen regionale observationer for den valgte a-kasse, så de pågældende figurer viser i stedet tal for hele landet og er mærket tydeligt.';
    }else{
      note.innerHTML='<strong>Regional visning:</strong> Tallene vises for '+name+' og den valgte a-kasse. Historikken går op til 5 år tilbage.'+(unsupported.includes('exhaustedRights')?' Målingen af opbrugt dagpengeret kan ikke opdeles regionalt i den konkrete Jobindsats-kilde og vises derfor for hele landet med særskilt mærkning.':'');
    }
    note.style.borderColor=isError?'#e3b7b0':'';
  }

  function wrapDraw(){
    if(drawWrapped||typeof draw!=='function')return;
    const baseDraw=draw;
    document.getElementById('fundSelect')?.removeEventListener('change',baseDraw);
    document.getElementById('periodSelect')?.removeEventListener('change',baseDraw);
    draw=function(){
      clearComparisonUi();const pair=comparisonPair();let restore=null,hadComparison=false,previousComparison;
      if(activeRegion!=='all'&&!selectedRegionalJobsAvailable()){
        const code=document.getElementById('fundSelect')?.value,regionalFund=DATA?.funds?.[code],nationalFund=nationalData?.funds?.[code];
        if(regionalFund&&nationalFund){restore=regionalFund.jobindsats;regionalFund.jobindsats=nationalFund.jobindsats||{};}
      }
      if(pair){hadComparison=Object.prototype.hasOwnProperty.call(DATA.funds,COMPARISON_CODE);previousComparison=DATA.funds[COMPARISON_CODE];DATA.funds[COMPARISON_CODE]={...pair.drawFund,name:COMPARISON_SENTINEL};drawingComparisonPair=pair;}
      try{baseDraw();}finally{
        if(pair){if(hadComparison)DATA.funds[COMPARISON_CODE]=previousComparison;else delete DATA.funds[COMPARISON_CODE];drawingComparisonPair=null;}
        if(restore!==null){const code=document.getElementById('fundSelect')?.value;if(DATA?.funds?.[code])DATA.funds[code].jobindsats=restore;}
      }
      updateRegionalText();updateGeographyContext();updateAvailability();updateUnsupported();applyComparison(pair);if(activeRegion!=='all')updateNotice();
    };
    document.getElementById('fundSelect')?.addEventListener('change',draw);
    document.getElementById('periodSelect')?.addEventListener('change',draw);
    drawWrapped=true;
  }

  async function setRegion(key){
    if(!nationalData)return;const select=document.getElementById('regionSelect'),periodSelect=document.getElementById('periodSelect');if(!REGION_FILES.has(key))key='all';
    if(key==='all'){
      activeRegion='all';DATA=nationalData;document.body.classList.remove('regional-no-jobdata');setPeriodLimit(false);if(nationalPeriod&&[...periodSelect.options].some(o=>o.value===String(nationalPeriod)))periodSelect.value=String(nationalPeriod);if(select)select.value='all';updateSameRegionOption();updateNotice();updateUnsupported();try{await ensureComparisonData();}catch(error){handleComparisonError(error,false);}if(typeof draw==='function')draw();save();return;
    }
    if(activeRegion==='all'){nationalPeriod=periodSelect.value;if(Number(periodSelect.value)<=60)regionalPeriod=periodSelect.value;}else if(Number(periodSelect.value)<=60)regionalPeriod=periodSelect.value;
    activeRegion=key;if(select)select.value=key;setPeriodLimit(true);periodSelect.value=Number(regionalPeriod)<=60?String(regionalPeriod):'60';updateNotice('<strong>Henter '+REGION_LABELS.get(key)+'...</strong>');
    const payload=await loadRegion(key);if(document.getElementById('regionSelect')?.value!==key)return;DATA=mergedRegionalData(payload);mergedRegionCache.set(key,DATA);updateSameRegionOption();updateAvailability();updateNotice();try{await ensureComparisonData();}catch(error){handleComparisonError(error,false);}if(typeof draw==='function')draw();save();
  }

  function handleRegionError(error){console.error(error);updateNotice('<strong>Regional visning kunne ikke indlæses.</strong> '+(error?.message||'Ukendt fejl')+'. Landsvisningen er bevaret.',true);activeRegion='all';DATA=nationalData;document.body.classList.remove('regional-no-jobdata');setPeriodLimit(false);const select=document.getElementById('regionSelect');if(select)select.value='all';updateSameRegionOption();updateUnsupported();ensureComparisonData().catch(comparisonError=>handleComparisonError(comparisonError,false)).finally(()=>{if(typeof draw==='function')draw();});}

  function comparisonFromState(state){
    if(Object.prototype.hasOwnProperty.call(state,'comparisonFund'))return{fundCode:nationalData?.funds?.[state.comparisonFund]?state.comparisonFund:'',regionChoice:state.comparisonRegion==='same'||REGION_FILES.has(state.comparisonRegion)?state.comparisonRegion:'same'};
    if(state.nationalReference&&nationalData?.funds?.[state.fund])return{fundCode:state.fund,regionChoice:'all'};
    const legacy=Array.isArray(state.compare)?state.compare.filter(code=>nationalData?.funds?.[code]):[];
    return{fundCode:legacy.find(code=>code!==state.fund)||legacy[0]||'',regionChoice:'same'};
  }

  async function applyState(state){
    if(!state)return;applying=true;const fundSelect=document.getElementById('fundSelect'),periodSelect=document.getElementById('periodSelect');
    if(state.fund&&fundSelect&&[...fundSelect.options].some(option=>option.value===state.fund))fundSelect.value=state.fund;
    if(state.period&&periodSelect&&[...periodSelect.options].some(option=>option.value===String(state.period)))periodSelect.value=String(state.period);
    const choice=comparisonFromState(state);comparisonFundCode=choice.fundCode;comparisonRegionChoice=choice.regionChoice;updateComparisonControls();applyVisibility(state.hidden||[]);
    const region=REGION_FILES.has(state.region)?state.region:'all';if(region!=='all'&&Number(periodSelect.value)<=60)regionalPeriod=periodSelect.value;
    try{await setRegion(region);}catch(error){handleRegionError(error);}
    refreshChecks();updateComparisonControls();applying=false;save();
  }

  function bindSave(){
    document.getElementById('fundSelect')?.addEventListener('change',()=>setTimeout(()=>{updateComparisonControls();save();},0));
    document.getElementById('periodSelect')?.addEventListener('change',()=>setTimeout(()=>{if(activeRegion==='all')nationalPeriod=document.getElementById('periodSelect').value;else regionalPeriod=document.getElementById('periodSelect').value;save();},0));
    document.getElementById('regionSelect')?.addEventListener('change',()=>setTimeout(save,0));
  }
  function ready(){return typeof DATA!=='undefined'&&DATA&&document.getElementById('fundSelect')?.options.length>0&&!document.getElementById('dashboard')?.hidden;}
  async function start(){
    injectStyle();injectRegionControls();if(!ready()){setTimeout(start,80);return;}
    if(!nationalData){nationalData=DATA;nationalPeriod=document.getElementById('periodSelect')?.value||'36';}
    installComparisonBridge();wrapDraw();injectComparisonControls();injectPersonalControls();bindSave();
    const state=sharedState()||storedState();
    if(state)await applyState(state);else{refreshChecks();await ensureComparisonData();if(typeof draw==='function')draw();save();}
  }
  start();
})();
