const { chromium } = require('playwright');
const sharp = require('sharp');
const fs = require('fs');
const path = require('path');
const https = require('https');
const ROOT = path.resolve(__dirname, '..');
const share = path.join(ROOT, 'share');
const out = path.join(ROOT, 'assets', 'share-previews');
fs.mkdirSync(out, { recursive: true });
const escapeXml = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const cards = fs.readdirSync(share).filter(name => /^[A-Za-z][\w-]*Chart\.html$/.test(name));
(async () => {
 const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
 const page = await browser.newPage({viewport:{width:1440,height:900},deviceScaleFactor:1});
 let produced=0;
 for(const filename of cards){
  const id=filename.replace(/\.html$/,'');
  const file=path.join(share,filename);
  const html=fs.readFileSync(file,'utf8');
  const title=(html.match(/<title>(.*?) \| A-kasseindsigt<\/title>/)||[])[1]||id;
  try {
   await page.goto('http://127.0.0.1:8765/index.html?figure='+encodeURIComponent(id),{waitUntil:'domcontentloaded',timeout:30000});
   await page.locator('#dashboard').waitFor({state:'visible',timeout:35000});
   const canvas=page.locator('#'+id);
   await canvas.waitFor({state:'attached',timeout:8000});
   const section=canvas.locator('xpath=ancestor::section[1]');
   await section.evaluate(el => {if(el.dataset.expanded!=='true')el.querySelector('.section-reveal')?.click();el.scrollIntoView({block:'center'});});
   await page.waitForFunction(id=>{
      const el=document.getElementById(id);
      const chart=window.Chart?.getChart(el);
      return !!(el&&chart&&chart.data&&chart.data.datasets?.length);
   },id,{timeout:15000});
   await page.waitForTimeout(500);
   const chartPng=await canvas.screenshot({timeout:15000});
   const chartImage=await sharp(chartPng).resize(1100,390,{fit:'contain',background:'#ffffff'}).png().toBuffer();
   const svg=`<svg width="1200" height="630" xmlns="http://www.w3.org/2000/svg">
   <rect width="1200" height="630" fill="#f7f1ea"/><rect x="28" y="28" width="1144" height="574" rx="18" fill="#ffffff"/>
   <rect x="28" y="28" width="1144" height="9" rx="3" fill="#6B9E78"/>
   <text x="60" y="82" fill="#2B211B" font-family="Arial" font-size="27" font-weight="bold">${escapeXml(title.length>62?title.slice(0,59)+'...':title)}</text>
   <text x="60" y="116" fill="#6f6258" font-family="Arial" font-size="17">A-kasseindsigt | Michel Klos</text>
   <text x="60" y="568" fill="#6f6258" font-family="Arial" font-size="16">Udforsk den interaktive graf og sammenlign a-kasser</text>
   </svg>`;
   const dest=path.join(out,id+'.png');
   await sharp(Buffer.from(svg)).composite([{input:chartImage,left:50,top:145}]).png().toFile(dest);
   const imageUrl='https://ai-michelklos.github.io/A-kasseindsigt-dashboard/assets/share-previews/'+id+'.png';
   fs.writeFileSync(file,html.replace(/https:\/\/ai-michelklos\.github\.io\/arbejdsmarked\/og-image\.png/g,imageUrl));
   console.log('Generated',id);produced++;
  }catch(error){
   console.warn('Chart unavailable for',id,error.message.split('\n')[0]);
   const svg=`<svg width="1200" height="630" xmlns="http://www.w3.org/2000/svg"><rect width="1200" height="630" fill="#f7f1ea"/><rect x="30" y="30" width="1140" height="570" rx="18" fill="#fff"/><rect x="30" y="30" width="1140" height="12" fill="#6B9E78"/><text x="70" y="165" fill="#2B211B" font-family="Arial" font-size="35" font-weight="bold">${escapeXml(title.length>54?title.slice(0,51)+'...':title)}</text><text x="70" y="245" fill="#6f6258" font-family="Arial" font-size="25">A-kasseindsigt | Michel Klos</text><text x="70" y="510" fill="#4a3428" font-family="Arial" font-size="24">Se grafen, vælg a-kasse og sammenlign de nyeste tal</text></svg>`;
   await sharp(Buffer.from(svg)).png().toFile(path.join(out,id+'.png'));
   const imageUrl='https://ai-michelklos.github.io/A-kasseindsigt-dashboard/assets/share-previews/'+id+'.png';
   fs.writeFileSync(file,html.replace(/https:\/\/ai-michelklos\.github\.io\/arbejdsmarked\/og-image\.png/g,imageUrl));
   produced++;
  }
 }
 await browser.close();
 if(produced===0)process.exitCode=1;
 console.log('Generated',produced,'of',cards.length);
})();