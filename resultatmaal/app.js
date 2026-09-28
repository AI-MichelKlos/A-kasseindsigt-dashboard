(function(){
  'use strict';
  const root=document.getElementById('dak-resultat');
  const byId=id=>root.querySelector('#'+id);
  const COLORS=['#315f48','#c0622a','#4a6fa5','#8e4f9e','#b5874a','#1a7a6e','#c0392b','#2471a3','#7d6608','#117a65','#6e2f7a','#1e5799','#7a3b00','#4a235a','#1a5276','#784212','#0e6655','#6c3483','#1b4f72','#922b21','#1d6a3a','#596579'];
  const months=['jan.','feb.','mar.','apr.','maj','jun.','jul.','aug.','sep.','okt.','nov.','dec.'];
  const label=p=>{const m=/^(\d{4})M(\d{2})$/.exec(p);return m?`${months[Number(m[2])-1]} ${m[1]}`:p};
  const pct=v=>Number.isFinite(v)?new Intl.NumberFormat('da-DK',{maximumFractionDigits:1,minimumFractionDigits:1}).format(v)+' %':'Ingen tal';
  const num=v=>Number.isFinite(v)?new Intl.NumberFormat('da-DK').format(v):'Ingen tal';
  const diff=v=>Number.isFinite(v)?`${v>0?'+':''}${new Intl.NumberFormat('da-DK',{maximumFractionDigits:1,minimumFractionDigits:1}).format(v)} procentpoint`:'Ingen tal';
  const STATUS=[['job','Job','#4a90c4'],['education','Uddannelse','#9270af'],['onBenefit','Fortsat på dagpenge','#6b9e78'],['otherBenefit','Anden ydelse','#e7a352'],['selfSupport','Selvforsørgelse mv.','#b9c4be']];
  const METRICS=[...STATUS,['combined','Job eller uddannelse','#315f48']];
  const incoming=new URL(location.href).searchParams;
  let data,view,charts={},selected=new Set(['TOTAL']),chosenMetrics=new Set(['job']);
  const message=byId('message');
  function error(text){message.hidden=false;message.textContent=text;}
  function bindTooltipDismissal(canvas){
    let timer;
    const dismiss=()=>{
      const chart=Chart.getChart(canvas);
      if(!chart?.tooltip)return;
      chart.tooltip.setActiveElements([],{x:0,y:0});
      chart.setActiveElements([]);
      chart.update('none');
    };
    const schedule=()=>{clearTimeout(timer);timer=setTimeout(dismiss,900);};
    canvas.addEventListener('pointerdown',()=>clearTimeout(timer));
    canvas.addEventListener('pointerup',schedule);
    canvas.addEventListener('touchend',schedule);
    canvas.addEventListener('pointercancel',dismiss);
    canvas.addEventListener('pointerleave',dismiss);
  }
  function keys(){return Object.keys(data.funds).sort((a,b)=>a==='TOTAL'?-1:b==='TOTAL'?1:data.funds[a].short.localeCompare(data.funds[b].short,'da'));}
  function color(code){return COLORS[keys().indexOf(code)%COLORS.length];}
  function selection(){return keys().filter(code=>selected.has(code));}
  function updateLink(){
    const url=new URL(location.href),params=url.searchParams;
    params.set('funds',selection().join(','));params.set('group',byId('group').value);
    if(byId('category').disabled)params.delete('category');else params.set('category',byId('category').value);
    params.set('report',byId('report-month').value);params.set('cohort',byId('cohort').value);params.set('span',byId('span').value);
    params.set('metrics',METRICS.filter(([key])=>chosenMetrics.has(key)).map(([key])=>key).join(','));
    params.set('horizon',byId('trend-horizon').value);params.set('status',byId('status-horizon').value);
    history.replaceState(null,'',url);
    if(!byId('share-box').hidden)byId('share-link').value=url.href;
  }
  function renderMetrics(){
    const box=byId('metrics');box.replaceChildren();
    for(const [key,name] of METRICS){
      const label=document.createElement('label');label.className='metric-option';
      const input=document.createElement('input');input.type='checkbox';input.value=key;input.checked=chosenMetrics.has(key);
      input.addEventListener('change',()=>{
        if(input.checked)chosenMetrics.add(key);else if(chosenMetrics.size>1)chosenMetrics.delete(key);else input.checked=true;
        render();
      });
      label.append(input,document.createTextNode(name));box.append(label);
    }
  }
  function renderTrend(){
    const which=byId('trend-horizon').value,offset=which==='three'?3:6;
    const all=Object.keys(view.series[which].TOTAL).map(p=>shift(p,offset)).sort(),limit=Number(byId('span').value),periods=limit?all.slice(-limit):all;
    byId('trend-context').textContent=`Opgørelse ${label(periods[0])} til ${label(periods.at(-1))} · nyledige ${offset} måneder før`;
    const codes=selection(),metrics=METRICS.filter(([key])=>chosenMetrics.has(key));
    const datasets=codes.flatMap(code=>metrics.map(([key,name,metricColor],index)=>({
      label:`${data.funds[code].short} · ${name}`,
      data:periods.map(month=>{const p=shift(month,-offset),value=key==='combined'?view.series[which][code]?.[p]:view.statusShares[which][code]?.[p]?.[key];return Number.isFinite(value)?value:null;}),
      borderColor:codes.length===1?metricColor:color(code),backgroundColor:codes.length===1?metricColor:color(code),
      borderDash:index===0?[]:[4+index*2,3],borderWidth:2.6,pointRadius:periods.length>30?1.5:2.5,pointHoverRadius:6,spanGaps:false,tension:.14
    })));
    if(charts.trend)charts.trend.destroy();
    charts.trend=new Chart(byId('trend-chart'),{
      type:'line',data:{labels:periods.map(label),datasets},
      options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'nearest',intersect:false},plugins:{legend:{position:'top',labels:{boxWidth:20,font:{size:12}}},tooltip:{callbacks:{title:items=>items[0]?`Opgjort ${label(periods[items[0].dataIndex])} · nyledige ${label(shift(periods[items[0].dataIndex],-offset))}`:'',label:item=>`${item.dataset.label}: ${pct(item.parsed.y)}`}}},scales:{x:{type:'category',grid:{display:false},ticks:{maxRotation:45,callback:(_,index)=>index%Math.max(1,Math.ceil(periods.length/12))===0||index===periods.length-1?label(periods[index]):''}},y:{beginAtZero:true,min:0,max:100,title:{display:true,text:'Andel af nyledige, pct.'},ticks:{callback:v=>v+' %'}}}}
    });
  }
  function renderFunds(){
    const box=byId('funds');box.replaceChildren();
    for(const code of keys()){
      const fund=data.funds[code], item=document.createElement('label');item.className='fund';item.title=fund.name;
      const input=document.createElement('input');input.type='checkbox';input.value=code;input.checked=selected.has(code);
      input.addEventListener('change',()=>{
        if(input.checked)selected.add(code);else if(selected.size>1)selected.delete(code);else input.checked=true;
        render();
      });
      item.append(input,document.createTextNode(fund.short));box.append(item);
    }
  }
  function renderChart(which){
    const series=view.series[which], selectedCodes=selection();
    const allPeriods=[...new Set(Object.values(series).flatMap(rows=>Object.keys(rows)))].sort();
    const count=Number(byId('span').value);
    const periods=count?allPeriods.slice(-count):allPeriods;
    const latest=allPeriods.at(-1);
    const prefix=which==='three'?'three':'six';
    byId(prefix+'-latest').textContent=latest?`Nyeste nyledighed: ${label(latest)} · Statusmåned: ${label(shift(latest,which==='three'?3:6))}`:'Ingen opgjorte måneder';
    const list=byId(prefix+'-values');list.replaceChildren();
    for(const code of selectedCodes){
      const r=series[code]||{}, last=[...allPeriods].reverse().find(p=>Number.isFinite(r[p]));
      const card=document.createElement('div');card.className='value';card.style.setProperty('--color',color(code));
      const name=document.createElement('span');name.textContent=data.funds[code].short+(last&&last!==latest?` · ${label(last)}`:'');
      const value=document.createElement('strong');value.textContent=last?pct(r[last]):'Ingen tal';
      const count=document.createElement('small');const n=last?view.counts?.[which]?.[code]?.[last]:null;
      count.textContent=Number.isFinite(n)?`Nyledige: ${new Intl.NumberFormat('da-DK').format(n)}`:'Antal ikke oplyst';
      card.append(name,value,count);list.append(card);
    }
    const ctx=byId(prefix+'-chart');
    if(charts[which])charts[which].destroy();
    charts[which]=new Chart(ctx,{
      type:'line',data:{labels:periods.map(label),datasets:selectedCodes.map(code=>({label:data.funds[code].short,data:periods.map(p=>Number.isFinite(series[code]?.[p])?series[code][p]:null),borderColor:color(code),backgroundColor:color(code),borderWidth:2.7,pointRadius:periods.length>30?2:3,pointHoverRadius:6,spanGaps:false,tension:.16}))},
      options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'nearest',intersect:false},plugins:{legend:{position:'top',labels:{boxWidth:18,usePointStyle:true,font:{size:13}}},tooltip:{callbacks:{title:items=>items[0]?`Nyledige ${label(periods[items[0].dataIndex])} · status ${label(shift(periods[items[0].dataIndex],which==='three'?3:6))}`:'',label:item=>`${item.dataset.label}: ${pct(item.parsed.y)}`}}},scales:{x:{type:'category',grid:{display:false},ticks:{color:'#52656a',maxRotation:45,callback:function(value,index){const p=periods[index];return (index%Math.max(1,Math.ceil(periods.length/12))===0||index===periods.length-1)?label(p):''}}},y:{beginAtZero:true,min:0,max:100,title:{display:true,text:'Andel i job eller uddannelse, pct.'},ticks:{callback:v=>v+' %'},grid:{color:'#e8ebe8'}}}}
    });
  }
  function shift(period,offset){const m=/^(\d{4})M(\d{2})$/.exec(period);if(!m)return period;const d=new Date(Date.UTC(Number(m[1]),Number(m[2])-1+offset,1));return `${d.getUTCFullYear()}M${String(d.getUTCMonth()+1).padStart(2,'0')}`;}
  function addRow(body,values){const tr=document.createElement('tr');values.forEach(value=>{const td=document.createElement('td');td.textContent=value;tr.append(td);});body.append(tr);}
  function commonMonths(){return Object.keys(view.series.three.TOTAL).filter(p=>Object.hasOwn(view.series.six.TOTAL,p)).sort();}
  function commonReportMonths(){
    const three=new Set(Object.keys(view.series.three.TOTAL).map(p=>shift(p,3)));
    return Object.keys(view.series.six.TOTAL).map(p=>shift(p,6)).filter(p=>three.has(p)).sort();
  }
  function renderReport(){
    const month=byId('report-month').value,codes=selection();
    const three=shift(month,-3),six=shift(month,-6);
    byId('report-context').replaceChildren();
    const strong=document.createElement('strong');strong.textContent=`Opgørelse ${label(month)}: `;
    byId('report-context').append(strong,document.createTextNode(`3 måneder efter nyledighed i ${label(three)}. 6 måneder efter nyledighed i ${label(six)}. Det er to forskellige grupper.`));
    const body=byId('report-table').querySelector('tbody');body.replaceChildren();
    for(const [which,horizon,p] of [['three','3 måneder',three],['six','6 måneder',six]])for(const code of codes){
      addRow(body,[horizon,data.funds[code].short,label(month),label(p),pct(view.series[which][code]?.[p]),num(view.counts[which][code]?.[p])]);
    }
    const box=byId('report-chart').parentElement;box.style.height=`${Math.max(190,110+codes.length*35)}px`;
    if(charts.report)charts.report.destroy();
    charts.report=new Chart(byId('report-chart'),{
      type:'bar',data:{labels:codes.map(code=>data.funds[code].short),datasets:[
        {label:`3 måneder · nyledige ${label(three)}`,data:codes.map(code=>view.series.three[code]?.[three]??null),backgroundColor:'#6B9E78'},
        {label:`6 måneder · nyledige ${label(six)}`,data:codes.map(code=>view.series.six[code]?.[six]??null),backgroundColor:'#4A90C4'}
      ]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top'},tooltip:{callbacks:{label:item=>`${item.dataset.label}: ${pct(item.parsed.x)}`}}},scales:{x:{beginAtZero:true,min:0,max:100,title:{display:true,text:'Andel i job eller uddannelse, pct.'},ticks:{callback:v=>v+' %'},grid:{color:'#e8ebe8'}},y:{grid:{display:false}}}}
    });
  }
  function renderReportTrend(){
    const all=[...new Set(['three','six'].flatMap(which=>Object.keys(view.series[which].TOTAL).map(p=>shift(p,which==='three'?3:6))))].sort();
    const limit=Number(byId('span').value),periods=limit?all.slice(-limit):all,codes=selection();
    const datasets=codes.flatMap(code=>[['three',3,'3 måneder','#6B9E78'],['six',6,'6 måneder','#4A90C4']].map(([which,offset,horizon,horizonColor])=>({
      label:`${data.funds[code].short} · ${horizon}`,
      data:periods.map(month=>{const value=view.series[which][code]?.[shift(month,-offset)];return Number.isFinite(value)?value:null;}),
      borderColor:codes.length===1?horizonColor:color(code),backgroundColor:codes.length===1?horizonColor:color(code),borderDash:offset===3?[]:[7,4],borderWidth:2.7,pointRadius:periods.length>30?2:3,pointHoverRadius:6,spanGaps:false,tension:.16
    })));
    if(charts.reportTrend)charts.reportTrend.destroy();
    charts.reportTrend=new Chart(byId('report-trend-chart'),{
      type:'line',data:{labels:periods.map(label),datasets},
      options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'nearest',intersect:false},plugins:{legend:{position:'top'},tooltip:{callbacks:{title:items=>items[0]?`Opgjort ${label(periods[items[0].dataIndex])}`:'',label:item=>{const offset=item.dataset.label.endsWith('3 måneder')?3:6;return `${item.dataset.label} · nyledige ${label(shift(periods[item.dataIndex],-offset))}: ${pct(item.parsed.y)}`;}}}},scales:{x:{type:'category',grid:{display:false},ticks:{maxRotation:45,callback:(_,index)=>index%Math.max(1,Math.ceil(periods.length/12))===0||index===periods.length-1?label(periods[index]):''}},y:{beginAtZero:true,min:0,max:100,title:{display:true,text:'Andel i job eller uddannelse, pct.'},ticks:{callback:v=>v+' %'}}}}
    });
  }
  function renderCohort(){
    const p=byId('cohort').value,codes=selection();
    byId('cohort-context').textContent=`Nyledige ${label(p)} · status efter 3 måneder: ${label(shift(p,3))} · efter 6 måneder: ${label(shift(p,6))}`;
    const body=byId('cohort-table').querySelector('tbody');body.replaceChildren();
    for(const code of codes){
      const a=view.series.three[code]?.[p],b=view.series.six[code]?.[p];
      addRow(body,[data.funds[code].short,pct(a),pct(b),num(view.counts.three[code]?.[p]),num(view.counts.six[code]?.[p])]);
    }
    const box=byId('cohort-chart').parentElement;box.style.height=`${Math.max(190,110+codes.length*35)}px`;
    if(charts.cohort)charts.cohort.destroy();
    charts.cohort=new Chart(byId('cohort-chart'),{
      type:'bar',data:{labels:codes.map(code=>data.funds[code].short),datasets:[
        {label:'Efter 3 måneder',data:codes.map(code=>view.series.three[code]?.[p]??null),backgroundColor:'#6B9E78'},
        {label:'Efter 6 måneder',data:codes.map(code=>view.series.six[code]?.[p]??null),backgroundColor:'#4A90C4'}
      ]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top'},tooltip:{callbacks:{label:item=>`${item.dataset.label}: ${pct(item.parsed.x)}`}}},scales:{x:{beginAtZero:true,min:0,max:100,title:{display:true,text:'Andel i job eller uddannelse, pct.'},ticks:{callback:v=>v+' %'},grid:{color:'#e8ebe8'}},y:{grid:{display:false}}}}
    });
  }
  function renderStatus(){
    const which=byId('status-horizon').value,month=byId('report-month').value,codes=selection(),offset=which==='three'?3:6,p=shift(month,-offset);
    byId('status-context').textContent=`Opgjort ${label(month)} · nyledige ${label(p)}`;
    const body=byId('status-table').querySelector('tbody');body.replaceChildren();
    const complete=[];
    for(const code of codes){
      const shares=view.statusShares[which][code]?.[p]||{};
      addRow(body,[data.funds[code].short,...STATUS.map(([key])=>pct(shares[key]))]);
      if(STATUS.every(([key])=>Number.isFinite(shares[key])))complete.push(code);
    }
    const box=byId('status-chart').parentElement;box.style.display=complete.length?'block':'none';box.style.height=`${Math.max(190,110+complete.length*35)}px`;
    if(charts.status)charts.status.destroy();
    if(!complete.length)return;
    charts.status=new Chart(byId('status-chart'),{
      type:'bar',data:{labels:complete.map(code=>data.funds[code].short),datasets:STATUS.map(([key,name,color])=>({label:name,data:complete.map(code=>view.statusShares[which][code][p][key]),backgroundColor:color}))},
      options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top',labels:{boxWidth:15}},tooltip:{callbacks:{label:item=>`${item.dataset.label}: ${pct(item.parsed.x)}`}}},scales:{x:{stacked:true,beginAtZero:true,min:0,max:100,ticks:{callback:v=>v+' %'},grid:{color:'#e8ebe8'}},y:{stacked:true,grid:{display:false}}}}
    });
  }
  function renderYear(){
    const body=byId('year-table').querySelector('tbody');body.replaceChildren();
    for(const [which,name] of [['three','3 måneder'],['six','6 måneder']]){
      const latest=Object.keys(view.series[which].TOTAL).sort().at(-1),yearBefore=latest.replace(/^\d{4}/,String(Number(latest.slice(0,4))-1));
      for(const code of selection()){
        const a=view.series[which][code]?.[latest],b=view.series[which][code]?.[yearBefore];
        addRow(body,[name,data.funds[code].short,label(latest),pct(a),pct(b),diff(Number.isFinite(a)&&Number.isFinite(b)?Math.round((a-b)*10)/10:null)]);
      }
    }
  }
  function average(which,code,periods){
    let weighted=0,count=0;
    for(const p of periods){
      const share=view.series[which][code]?.[p],n=view.counts[which][code]?.[p];
      if(!Number.isFinite(share)||!Number.isFinite(n)||n<=0)return null;
      weighted+=share*n;count+=n;
    }
    return {share:weighted/count,count};
  }
  function renderAverage(){
    const body=byId('average-table').querySelector('tbody');body.replaceChildren();
    const periods=commonMonths().slice(-12);
    for(const [which,name] of [['three','3 måneder'],['six','6 måneder']]){
      const total=periods.length===12?average(which,'TOTAL',periods):null;
      for(const code of selection()){
        const result=periods.length===12?average(which,code,periods):null;
        addRow(body,[name,data.funds[code].short,pct(result?.share),diff(result&&total?result.share-total.share:null),num(result?.count)]);
      }
    }
    byId('average-context').textContent=periods.length===12?`Nyledige ${label(periods[0])} til ${label(periods.at(-1))} · samme startmåneder for begge nedslag`:'12 fælles startmåneder er endnu ikke tilgængelige';
  }
  function render(){renderFunds();renderMetrics();renderReport();renderReportTrend();renderTrend();renderStatus();renderCohort();renderAverage();if(byId('extra-details').open){renderChart('three');renderChart('six');renderYear();}updateLink();}
  function renderCategories(preferred){
    const group=byId('group').value,select=byId('category');select.replaceChildren();
    const categories=data.subgroups?.[group]?.categories||[];
    select.disabled=!categories.length;
    for(const item of categories){const option=document.createElement('option');option.value=item.id;option.textContent=item.label;select.append(option);}
    const suggested={age:'25-29 år',origin:'Personer med dansk oprindelse',region:'Region Hovedstaden'}[group];
    const initial=categories.find(item=>item.label===suggested);
    if(initial)select.value=initial.id;
    if(preferred&&categories.some(item=>item.id===preferred))select.value=preferred;
    view=categories.length?data.subgroups[group].slices[select.value]:data;
    render();
  }
  function csv(){
    const header=['Opdeling','Gruppe','Nyledighedsmåned','Opgørelsesmåned','Nedslag','A-kasse','Antal nyledige','Andel i job eller uddannelse (pct.)',...STATUS.map(([,name])=>name+' (pct.)')];
    const rows=[header];
    const raw=v=>Number.isFinite(v)?String(v).replace('.',','):'';
    for(const which of ['three','six'])for(const code of selection())for(const [p,v] of Object.entries(view.series[which][code]||{}).sort()){
      const shares=view.statusShares[which][code]?.[p]||{};
      rows.push([byId('group').selectedOptions[0].textContent,byId('category').disabled?'Alle':byId('category').selectedOptions[0].textContent,p,shift(p,which==='three'?3:6),which==='three'?'3 måneder':'6 måneder',data.funds[code].name,raw(view.counts[which][code]?.[p]),raw(v),...STATUS.map(([key])=>raw(shares[key]))]);
    }
    const esc=x=>'"'+String(x).replaceAll('"','""')+'"';
    const blob=new Blob(['\ufeff',rows.map(row=>row.map(esc).join(';')).join('\r\n')],{type:'text/csv;charset=utf-8'});
    const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='nyledighed-job-uddannelse.csv';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);
  }
  byId('all').addEventListener('click',()=>{selected=new Set(Object.keys(data.funds));render();});
  byId('reset').addEventListener('click',()=>{selected=new Set(['TOTAL']);render();});
  byId('span').addEventListener('change',()=>data&&render());
  byId('group').addEventListener('change',()=>data&&renderCategories());
  byId('category').addEventListener('change',()=>{if(data){view=data.subgroups[byId('group').value].slices[byId('category').value];render();}});
  byId('report-month').addEventListener('change',()=>{if(data){renderReport();renderStatus();updateLink();}});
  byId('cohort').addEventListener('change',()=>data&&render());
  byId('trend-horizon').addEventListener('change',()=>data&&render());
  byId('status-horizon').addEventListener('change',()=>{if(data){renderStatus();updateLink();}});
  byId('extra-details').addEventListener('toggle',()=>{if(data&&byId('extra-details').open){renderChart('three');renderChart('six');renderYear();}});
  byId('csv').addEventListener('click',()=>data&&csv());
  byId('share').addEventListener('click',async()=>{
    if(!data)return;
    updateLink();const box=byId('share-box'),input=byId('share-link');box.hidden=false;input.value=location.href;
    try{await navigator.clipboard.writeText(input.value);byId('share-status').textContent='Link kopieret';}
    catch{input.focus();input.select();byId('share-status').textContent='Markér og kopiér linket';}
  });
  Promise.all([
    fetch('../data/rm01ak.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Datafil mangler');return r.json();}),
    fetch('../status/rm01ak.json',{cache:'no-store'}).then(r=>r.ok?r.json():{state:'unverified'}).catch(()=>({state:'unverified'}))
  ]).then(([payload,status])=>{
    if(payload.meta?.state!=='ok'||!payload.funds?.TOTAL||!payload.series?.three?.TOTAL||!payload.series?.six?.TOTAL||!payload.statusShares?.three?.TOTAL||!payload.statusShares?.six?.TOTAL)throw Error('De nye datakategorier er endnu ikke verificeret');
    if(typeof Chart==='undefined')throw Error('Grafbiblioteket kunne ikke indlæses');
    Chart.defaults.events=['mousemove','mouseout','touchstart','touchmove'];
    Chart.defaults.plugins.tooltip.mode='nearest';
    Chart.defaults.plugins.tooltip.intersect=false;
    Chart.defaults.plugins.tooltip.position='nearest';
    Chart.defaults.plugins.tooltip.animation={duration:90};
    Chart.defaults.plugins.tooltip.backgroundColor='rgba(15,43,54,.87)';
    root.querySelectorAll('canvas').forEach(bindTooltipDismissal);
    data=payload;view=data;
    if(payload.subgroups)for(const [key,group] of Object.entries(payload.subgroups)){
      if(!group.categories?.length||!group.categories.every(c=>group.slices?.[c.id]?.series?.three?.TOTAL))throw Error(`Manglende data for ${key}`);
      const option=document.createElement('option');option.value=key;option.textContent=group.label;byId('group').append(option);
    }
    const options=byId('cohort');
    for(const p of Object.keys(data.series.three.TOTAL).filter(p=>Object.hasOwn(data.series.six.TOTAL,p)).sort().reverse()){
      const option=document.createElement('option');option.value=p;option.textContent=label(p);options.append(option);
    }
    const reports=byId('report-month');
    for(const month of commonReportMonths().reverse()){
      const option=document.createElement('option');option.value=month;option.textContent=label(month);reports.append(option);
    }
    if(!reports.options.length||!options.options.length)throw Error('Ingen fælles måneder for de to nedslag');
    const funds=incoming.get('funds')?.split(',').filter(code=>Object.hasOwn(data.funds,code));
    if(funds?.length)selected=new Set(funds);
    const span=incoming.get('span');if(['0','12','24'].includes(span))byId('span').value=span;
    const metrics=incoming.get('metrics')?.split(',').filter(key=>METRICS.some(([id])=>id===key));
    if(metrics?.length)chosenMetrics=new Set(metrics);
    const cohort=incoming.get('cohort');if([...options.options].some(option=>option.value===cohort))options.value=cohort;
    const report=incoming.get('report');if([...reports.options].some(option=>option.value===report))reports.value=report;
    if(['three','six'].includes(incoming.get('horizon')))byId('trend-horizon').value=incoming.get('horizon');
    if(['three','six'].includes(incoming.get('status')))byId('status-horizon').value=incoming.get('status');
    const group=incoming.get('group');
    if(data.subgroups?.[group]){byId('group').value=group;const select=byId('category');
      for(const item of data.subgroups[group].categories){const option=document.createElement('option');option.value=item.id;option.textContent=item.label;select.append(option);}
      select.disabled=false;const preferred=incoming.get('category');
      const suggested={age:'25-29 år',origin:'Personer med dansk oprindelse',region:'Region Hovedstaden'}[group];
      const fallback=data.subgroups[group].categories.find(item=>item.label===suggested);
      select.value=data.subgroups[group].categories.some(item=>item.id===preferred)?preferred:(fallback?.id||select.value);
      view=data.subgroups[group].slices[select.value];
    }
    byId('freshness').textContent=`Jobindsats.dk · seneste statusmåned ${label(payload.meta.latestStatusMonth)} · hentet ${new Date(payload.meta.fetchedAt).toLocaleDateString('da-DK')}`;
    if(status.state!=='ok')error('Seneste automatiske kildekontrol er ikke gennemført. De viste tal er fra den sidst verificerede datafil.');
    render();
  }).catch(e=>{byId('freshness').textContent='Data afventer kontrol';error(`Dashboardet viser endnu ikke tal: ${e.message}. Se den originale måling hos Jobindsats.dk via kildelinket nedenfor.`);});
})();
