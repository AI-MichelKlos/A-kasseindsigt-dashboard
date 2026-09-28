(function(){
  'use strict';
  const root=document.getElementById('dak-resultat');
  const byId=id=>root.querySelector('#'+id);
  const COLORS=['#315f48','#c0622a','#4a6fa5','#8e4f9e','#b5874a','#1a7a6e','#c0392b','#2471a3','#7d6608','#117a65','#6e2f7a','#1e5799','#7a3b00','#4a235a','#1a5276','#784212','#0e6655','#6c3483','#1b4f72','#922b21','#1d6a3a','#596579'];
  const months=['jan.','feb.','mar.','apr.','maj','jun.','jul.','aug.','sep.','okt.','nov.','dec.'];
  const label=p=>{const m=/^(\d{4})M(\d{2})$/.exec(p);return m?`${months[Number(m[2])-1]} ${m[1]}`:p};
  const pct=v=>Number.isFinite(v)?new Intl.NumberFormat('da-DK',{maximumFractionDigits:1,minimumFractionDigits:1}).format(v)+' %':'Ingen tal';
  let data,charts={},selected=new Set(['TOTAL']);
  const message=byId('message');
  function error(text){message.hidden=false;message.textContent=text;}
  function keys(){return Object.keys(data.funds).sort((a,b)=>a==='TOTAL'?-1:b==='TOTAL'?1:data.funds[a].short.localeCompare(data.funds[b].short,'da'));}
  function color(code){return COLORS[keys().indexOf(code)%COLORS.length];}
  function selection(){return keys().filter(code=>selected.has(code));}
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
    const series=data.series[which], selectedCodes=selection();
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
      const count=document.createElement('small');const n=last?data.counts?.[which]?.[code]?.[last]:null;
      count.textContent=Number.isFinite(n)?`Nyledige: ${new Intl.NumberFormat('da-DK').format(n)}`:'Antal ikke oplyst';
      card.append(name,value,count);list.append(card);
    }
    const ctx=byId(prefix+'-chart');
    if(charts[which])charts[which].destroy();
    charts[which]=new Chart(ctx,{
      type:'line',data:{labels:periods.map(label),datasets:selectedCodes.map(code=>({label:data.funds[code].short,data:periods.map(p=>Number.isFinite(series[code]?.[p])?series[code][p]:null),borderColor:color(code),backgroundColor:color(code),borderWidth:2.7,pointRadius:periods.length>30?2:3,pointHoverRadius:6,spanGaps:false,tension:.16}))},
      options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{position:'top',labels:{boxWidth:18,usePointStyle:true,font:{size:13}}},tooltip:{callbacks:{title:items=>items[0]?`Nyledige ${periods[items[0].dataIndex]} · status ${shift(periods[items[0].dataIndex],which==='three'?3:6)}`:'',label:item=>`${item.dataset.label}: ${pct(item.parsed.y)}`}}},scales:{x:{type:'category',grid:{display:false},ticks:{color:'#52656a',maxRotation:45,callback:function(value,index){const p=periods[index];return (index%Math.max(1,Math.ceil(periods.length/12))===0||index===periods.length-1)?label(p):''}}},y:{beginAtZero:true,min:0,max:100,title:{display:true,text:'Andel i job eller uddannelse, pct.'},ticks:{callback:v=>v+' %'},grid:{color:'#e8ebe8'}}}}
    });
  }
  function shift(period,offset){const m=/^(\d{4})M(\d{2})$/.exec(period);if(!m)return period;const d=new Date(Date.UTC(Number(m[1]),Number(m[2])-1+offset,1));return `${d.getUTCFullYear()}M${String(d.getUTCMonth()+1).padStart(2,'0')}`;}
  function render(){renderFunds();renderChart('three');renderChart('six');}
  function csv(){
    const header=['Nyledighedsmåned','Opgørelsesmåned','Nedslag','A-kasse','Andel i job eller uddannelse (pct.)'];
    const rows=[header];
    for(const which of ['three','six'])for(const code of selection())for(const [p,v] of Object.entries(data.series[which][code]||{}).sort())rows.push([p,shift(p,which==='three'?3:6),which==='three'?'3 måneder':'6 måneder',data.funds[code].name,Number.isFinite(v)?String(v).replace('.',','):'']);
    const esc=x=>'"'+String(x).replaceAll('"','""')+'"';
    const blob=new Blob(['\ufeff',rows.map(row=>row.map(esc).join(';')).join('\r\n')],{type:'text/csv;charset=utf-8'});
    const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='nyledighed-job-uddannelse.csv';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);
  }
  byId('all').addEventListener('click',()=>{selected=new Set(Object.keys(data.funds));render();});
  byId('reset').addEventListener('click',()=>{selected=new Set(['TOTAL']);render();});
  byId('span').addEventListener('change',()=>data&&render());
  byId('csv').addEventListener('click',()=>data&&csv());
  Promise.all([
    fetch('../data/rm01ak.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Datafil mangler');return r.json();}),
    fetch('../status/rm01ak.json',{cache:'no-store'}).then(r=>r.ok?r.json():{state:'unverified'}).catch(()=>({state:'unverified'}))
  ]).then(([payload,status])=>{
    if(payload.meta?.state!=='ok'||!payload.funds?.TOTAL||!payload.series?.three?.TOTAL||!payload.series?.six?.TOTAL)throw Error('Datakilden er endnu ikke verificeret');
    if(typeof Chart==='undefined')throw Error('Grafbiblioteket kunne ikke indlæses');
    data=payload;
    byId('freshness').textContent=`Jobindsats.dk · seneste statusmåned ${label(payload.meta.latestStatusMonth)} · hentet ${new Date(payload.meta.fetchedAt).toLocaleDateString('da-DK')}`;
    if(status.state!=='ok')error('Seneste automatiske kildekontrol er ikke gennemført. De viste tal er fra den sidst verificerede datafil.');
    render();
  }).catch(e=>{byId('freshness').textContent='Data afventer kontrol';error(`Dashboardet viser endnu ikke tal: ${e.message}. Se den originale måling hos Jobindsats.dk via kildelinket nedenfor.`);});
})();
