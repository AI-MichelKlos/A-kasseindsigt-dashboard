(function(){
'use strict';
const ROOT='https://ai-michelklos.github.io/A-kasseindsigt-dashboard/';
function encode(value){const bytes=new TextEncoder().encode(JSON.stringify(value));let raw='';bytes.forEach(byte=>raw+=String.fromCharCode(byte));return btoa(raw).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');}
function state(){
  let old={};try{old=JSON.parse(localStorage.getItem('dak-a-kasseindsigt-personal-view-v5')||'{}');}catch(_){}
  return {...old,v:5,region:document.getElementById('regionSelect')?.value||'all',fund:document.getElementById('fundSelect')?.value||'',period:document.getElementById('periodSelect')?.value||'',comparisonFund:document.getElementById('comparisonFundSelect')?.value||'',comparisonRegion:document.getElementById('comparisonRegionSelect')?.value||''};
}
function getLink(id){return ROOT+'share/'+encodeURIComponent(id)+'.html?v=mk20261121&pv='+encodeURIComponent(encode(state()));}
window.__dakShareLinkForFigure=getLink;
function notice(button,message){const old=button.textContent;button.textContent=message;setTimeout(()=>button.textContent=old,2200);}
function attach(){
document.querySelectorAll('#dashboard .card').forEach(card=>{
 const canvas=card.querySelector('canvas[id]'),toolbar=card.querySelector('.chart-toolbar');
 if(!canvas||!toolbar||toolbar.querySelector('.dak-share-linkedin'))return;
 const id=canvas.id, linkedin=document.createElement('button'),copy=document.createElement('button');
 linkedin.type=copy.type='button';linkedin.className='chart-action dak-share-linkedin';copy.className='chart-action dak-share-copy';
 linkedin.textContent='Del på LinkedIn';copy.textContent='Kopiér link';
 linkedin.setAttribute('aria-label','Del '+(card.querySelector('h3')?.textContent||'graf')+' på LinkedIn');
 linkedin.addEventListener('click',()=>{
   const share='https://www.linkedin.com/sharing/share-offsite/?url='+encodeURIComponent(getLink(id));
   window.open(share,'_blank','noopener,noreferrer');
 });
 copy.addEventListener('click',async()=>{
   const url=getLink(id);
   try{await navigator.clipboard.writeText(url);notice(copy,'Link kopieret');}
   catch(_){window.prompt('Kopiér link til grafen',url);}
 });
 toolbar.append(linkedin,copy);
});
}
function deepLink(){
 const id=new URLSearchParams(location.search).get('figure');
 if(!id||!/^[A-Za-z][\w-]{1,90}$/.test(id))return;
 let attempts=0;
 const seek=()=>{
  const canvas=document.getElementById(id);
  if(!canvas){if(++attempts<60)setTimeout(seek,250);return;}
  const section=canvas.closest('#dashboard > section');
  if(section?.hidden)section.hidden=false;
  const reveal=section?.querySelector('.section-reveal');
  if(reveal&&section.dataset.expanded!=='true')reveal.click();
  const card=canvas.closest('.card');
  if(card){card.scrollIntoView({behavior:'smooth',block:'start'});card.classList.add('dak-shared-figure');}
 };
 setTimeout(seek,400);
}
const style=document.createElement('style');
style.textContent='#dashboard .dak-shared-figure{outline:2px solid #6B9E78;outline-offset:3px}#dashboard .dak-share-linkedin{background:#0a66c2;color:#fff;border-color:#0a66c2}#dashboard .dak-share-copy{white-space:nowrap}@media(max-width:600px){#dashboard .chart-toolbar{flex-wrap:wrap}}';
document.head.append(style);
document.addEventListener('DOMContentLoaded',()=>{attach();deepLink();new MutationObserver(attach).observe(document.getElementById('dashboard')||document.body,{childList:true,subtree:true});});
})();