/* Public homepage acceptance: real Chromium, isolated data, no Hostinger access. */
'use strict';
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawn}=require('node:child_process');

const root=fs.mkdtempSync(path.join(os.tmpdir(),'roger-public-redesign-'));
const base='http://127.0.0.1:8922';
const stage=JSON.parse(fs.readFileSync('stage-clone/stage.json','utf8'));
for(const key of ['properties','cases','registrations','jobs','approvals','appointments','documents','tenancies','audit_log','parties'])stage[key]=[];
stage.next_case_id=900;
function save(){fs.writeFileSync(path.join(root,'stage.json'),JSON.stringify(stage));}
save();
fs.writeFileSync(path.join(root,'users.json'),JSON.stringify({users:[],sessions:{}}));
const server=spawn('python3',['stage-clone/serve.py'],{
  cwd:process.cwd(),env:{...process.env,DATA_DIR:root,BIND_HOST:'127.0.0.1',PORT:'8922',
    ROGER_STORAGE_BACKEND:'file',ROGER_ENV:'security-lab',ROGER_LAB_HTTP_COOKIES:'1',
    ROGER_ALLOWED_ORIGINS:base},stdio:['ignore','pipe','pipe']});
let stderr='';
for(const stream of [server.stdout,server.stderr])stream.on('data',b=>{
  stderr=(stderr+b.toString()).slice(-2000);
});
const output='browser-results';
fs.mkdirSync(output,{recursive:true});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function ready(){
  for(let attempt=0;attempt<80;attempt++){
    if(server.exitCode!==null)throw new Error('server stopped '+stderr);
    try{if((await fetch(base+'/api/public')).ok)return;}catch(_){}
    await sleep(150);
  }
  throw new Error('server did not start '+stderr);
}
async function run(){
  await ready();
  const browser=await chromium.launch({headless:true});
  let page,context;
  try{
    context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1});
    page=await context.newPage();
    const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base+'/',{waitUntil:'domcontentloaded'});
    await page.locator('#propertyCount').getByText('0 homes available').waitFor();
    assert.match(await page.locator('#empty').innerText(),/No homes advertised right now/);
    assert.equal(await page.locator('#cards .card').count(),0);
    assert.match(await page.locator('h1').innerText(),/A place to call home/);
    assert.equal(await page.getByText('One operating desk.').count(),0);
    console.log('PASS honest empty listings, new branding and property-first layout');

    // Reload with two valid listings; never show unadvertised or occupied ones.
    const live=JSON.parse(fs.readFileSync(path.join(root,'stage.json'),'utf8'));
    live.properties=[
      {id:'pilot-flat',title:'Light-filled two-bed flat',area:'Leeds',beds:2,rent:125000,
       lifecycle_status:'advertised',
       public_listing:{title:'Light-filled two-bed flat',area:'Leeds',beds:2,rent:125000,
         availableFrom:'November 2026',description:'Two bedrooms, bright living room and a shared garden.'}},
      {id:'pilot-studio',title:'Compact studio',area:'Bristol',beds:1,rent:82000,
       lifecycle_status:'advertised',
       public_listing:{title:'Compact studio',area:'Bristol',beds:1,rent:82000,
         description:'Central studio near parks and transport.'}},
      {id:'pilot-secret',title:'Not advertised',area:'Leeds',beds:4,rent:50000,
       lifecycle_status:'onboarding',
       public_listing:{title:'Not advertised',area:'Leeds',beds:4,rent:50000,description:'Private draft.'}},
      {id:'pilot-occupied',title:'Occupied flat',area:'Leeds',beds:3,rent:140000,
       lifecycle_status:'advertised',
       public_listing:{title:'Occupied flat',area:'Leeds',beds:3,rent:140000,description:'Should not show.'}}
    ];
    live.tenancies=[{id:'existing-tenant',property_id:'pilot-occupied',status:'active'}];
    fs.writeFileSync(path.join(root,'stage.json'),JSON.stringify(live));
    await page.reload();
    await page.locator('#cards .card').first().waitFor();
    assert.equal(await page.locator('#cards .card').count(),2);
    assert.equal(await page.getByText('Not advertised').count(),0);
    assert.equal(await page.getByText('Occupied flat').count(),0);
    assert.equal(await page.locator('#cards img').count(),0,'cannot pretend a sample is a real listing photo');
    assert.equal(await page.getByText('Deposit £').count(),0,'cannot invent a deposit');
    await page.screenshot({path:path.join(output,'roger-redesigned-desktop.png'),fullPage:true});
    console.log('PASS published-only property cards and honest missing-photo/deposit treatment');

    await page.locator('#searchBox').fill('Leeds');
    await page.locator('#bedsFilter').selectOption('2');
    assert.equal(await page.locator('#cards .card').count(),1);
    assert.match(await page.locator('#cards .card').innerText(),/Light-filled two-bed flat/);
    await page.locator('#rentFilter').selectOption('100000');
    assert.equal(await page.locator('#cards .card').count(),0);
    await page.locator('#clearFilters').click();
    assert.equal(await page.locator('#cards .card').count(),2);
    await page.locator('#searchBox').fill('Bristol');
    await page.locator('#searchAction').click();
    assert.equal(await page.locator('#cards .card').count(),1);
    await page.locator('#clearFilters').click();
    console.log('PASS location, bedroom, monthly price and clear search controls');

    await page.locator('#cards .card').first().getByRole('button',{name:/View property/}).click();
    await page.locator('#detailModal.open').waitFor();
    assert.equal(await page.locator('#modalTitle').innerText(),'Light-filled two-bed flat');
    assert.equal(await page.locator('#modalNoPhoto').isVisible(),true);
    assert.equal(await page.locator('#modalImage').isVisible(),false);
    await page.getByRole('button',{name:'Request viewing'}).click();
    await page.locator('#viewingForm [name=name]').fill('Pilot Viewer');
    await page.locator('#viewingForm [name=email]').fill('viewer@example.test');
    await page.locator('#viewingForm [name=time]').fill('Saturday afternoon');
    await page.locator('#viewingForm button[type=submit]').click();
    await page.locator('#viewingForm .result').getByText(/Thank you/).waitFor();
    let written=JSON.parse(fs.readFileSync(path.join(root,'stage.json'),'utf8'));
    assert.equal(written.cases.length,1);
    assert.equal(written.cases[0].property_id,'pilot-flat');
    assert.match(written.cases[0].message,/Saturday afternoon/);
    console.log('PASS real property modal and viewing request delivered to Roger cases');

    await page.locator('#closeButton').click();
    assert.equal(await page.locator('#exampleCards .example-card').count(),6);
    assert.equal(await page.locator('#exampleCards button').count(),0,'fictional properties cannot offer viewings');
    assert.match(await page.locator('#exampleCards').innerText(),/FICTIONAL EXAMPLE/);
    console.log('PASS six visibly fictional sample listings, separate from real property API');

    // One guided enquiry form creates three distinct backend lead types.
    await page.locator('#prospectName').fill('Pilot Home Hunter');
    await page.locator('#prospectEmail').fill('renter@example.test');
    await page.locator('#prospectArea').fill('Leeds');
    await page.locator('#prospectBeds').selectOption('2');
    await page.locator('#prospectMaxRent').fill('1300');
    await page.locator('#prospectMessage').fill('Moving soon');
    await page.locator('#prospectForm [name=consent]').check();
    await page.locator('#prospectSubmit').click();
    await page.locator('#prospectResult').getByText(/Thank you/).waitFor();
    let saved=JSON.parse(fs.readFileSync(path.join(root,'stage.json'),'utf8'));
    assert.equal(saved.cases.length,2);
    assert.equal(saved.cases[1].requirements.bedrooms,'2');
    assert.equal(saved.cases[1].prospect_stage,'enquiry');

    await page.locator('#prospectKind').selectOption('landlord');
    assert.equal(await page.locator('#landlordFields').isVisible(),true);
    assert.equal(await page.locator('#tenantFields').isVisible(),false);
    await page.locator('#prospectName').fill('Pilot Owner');
    await page.locator('#prospectEmail').fill('owner@example.test');
    await page.locator('#prospectArea').fill('Leeds');
    await page.locator('#prospectService').selectOption('management');
    await page.locator('#prospectMessage').fill('I need full management');
    await page.locator('#prospectForm [name=consent]').check();
    await page.locator('#prospectSubmit').click();
    await page.locator('#prospectResult').getByText(/Thank you/).waitFor();

    await page.locator('#prospectKind').selectOption('trades');
    assert.equal(await page.locator('#tradesFields').isVisible(),true);
    await page.locator('#prospectName').fill('Pilot Electrician');
    await page.locator('#prospectEmail').fill('trade@example.test');
    await page.locator('#prospectArea').fill('Leeds');
    await page.locator('#prospectTrade').selectOption('electrical');
    await page.locator('#prospectMessage').fill('Insurance available on request');
    await page.locator('#prospectForm [name=consent]').check();
    await page.locator('#prospectSubmit').click();
    await page.locator('#prospectResult').getByText(/Thank you/).waitFor();
    saved=JSON.parse(fs.readFileSync(path.join(root,'stage.json'),'utf8'));
    assert.deepEqual(saved.registrations.map(r=>r.role),['landlord','trades']);
    assert.equal(saved.registrations[0].prospect_stage,'lead');
    assert.equal(saved.registrations[1].prospect_stage,'applicant');
    assert.equal(saved.registrations[1].status,'pending');
    assert.equal(saved.registrations[1].verification_required,true);
    console.log('PASS full tenant, landlord, trade intake flows and safe initial stages');

    await page.locator('#newsletterName').fill('Newsletter Reader');
    await page.locator('#newsletterEmail').fill('reader@example.test');
    await page.locator('#newsletterAudience').selectOption('landlord');
    await page.locator('#newsletterForm [name=marketing_consent]').check();
    await page.locator('#newsletterSubmit').click();
    await page.locator('#newsletterResult').getByText(/Interest recorded/).waitFor();
    saved=JSON.parse(fs.readFileSync(path.join(root,'stage.json'),'utf8'));
    assert.equal(saved.newsletter_subscriptions.length,1);
    assert.equal(saved.newsletter_subscriptions[0].audience,'landlord');
    assert.equal(saved.newsletter_subscriptions[0].status,'pending_confirmation');
    assert.ok(saved.newsletter_subscriptions[0].consented_at);
    console.log('PASS niche newsletter interest, independent marketing consent and no sending claim');

    // Small viewport: fully navigable, without horizontal overflow or script errors.
    await page.setViewportSize({width:390,height:844});
    await page.reload();
    await page.locator('#menuToggle').click();
    assert.equal(await page.locator('#menuToggle').getAttribute('aria-expanded'),'true');
    await page.locator('#siteNav').getByRole('link',{name:'For landlords'}).click();
    assert.equal(await page.locator('#menuToggle').getAttribute('aria-expanded'),'false');
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+2);
    assert.equal(overflow,false,'mobile page must not horizontally overflow');
    await page.screenshot({path:path.join(output,'roger-redesigned-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    console.log('PASS mobile navigation, no horizontal overflow, no page errors');
    console.log('REDESIGNED PUBLIC WEBSITE BROWSER TEST PASSED');
  }catch(e){
    if(page)await page.screenshot({path:path.join(output,'roger-redesign-error.png'),fullPage:true}).catch(()=>{});
    throw e;
  }finally{
    if(context)await context.close().catch(()=>{});
    await browser.close().catch(()=>{});
  }
}
run().catch(e=>{console.error(e.stack||String(e));process.exitCode=1;})
  .finally(()=>{server.kill();fs.rmSync(root,{recursive:true,force:true})});
