/* Task 07: isolated, real browser clicks for the entire four-role repair journey.
 * Temporary fake identities/records only; no production network or payments.
 * Run from repo root: node tests/full_repair_browser.cjs
 * Requires npm playwright + locally installed Chromium.
 */
'use strict';
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawn} = require('node:child_process');
const base = 'http://127.0.0.1:8910';
const password = 'synthetic-full-pilot-password';
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'roger-full-browser-'));
const roles = ['agent','tenant','landlord','trades','other-tenant'];
const users={users:[], sessions:{}}, account={};
for(const role of roles){
  const salt=crypto.randomBytes(16).toString('hex');
  const account_id='account-'+role;
  account[role]=account_id;
  users.users.push({
    username:'pilot-'+role, display_name:role==='trades'?'Pilot Plumbing':'Pilot '+role,
    role:role==='other-tenant'?'tenant':role, account_id, salt,
    hash:crypto.scryptSync(password,Buffer.from(salt,'hex'),64,
      {N:16384,r:8,p:1,maxmem:64*1024*1024}).toString('hex')
  });
}
const stage=JSON.parse(fs.readFileSync('stage-clone/stage.json','utf8'));
for(const key of ['properties','cases','jobs','approvals','documents','registrations','appointments',
  'invitations','audit_log','parties','tenancies','management_agreements','notifications',
  'property_submissions','rent_ledger_entries','landlord_statements','tasks','compliance_records']){
  stage[key]=[];
}
stage.next_case_id=51;
stage.authority={standing_limit_pence:15000,currency:'GBP'};
stage.parties=[
  {id:'tenant-one',account_id:account.tenant,roles:['tenant'],status:'active',display_name:'Pilot tenant'},
  {id:'tenant-two',account_id:account['other-tenant'],roles:['tenant'],status:'active',display_name:'Pilot other-tenant'},
  {id:'owner-one',account_id:account.landlord,roles:['landlord'],status:'active',display_name:'Pilot landlord'},
  {id:'trade-one',account_id:account.trades,roles:['trades'],status:'active',
    display_name:'Pilot Plumbing',source_registration_id:'trade-reg-one'},
];
stage.properties=[
  {id:'home-one',title:'Pilot Home',area:'Leeds',postcode:'LS1 1AA',beds:2,rent:92000,
    tenant_party_id:'tenant-one',landlord_party_id:'owner-one'},
  {id:'home-two',title:'Unrelated Home',area:'York',postcode:'YO1 1AA',beds:1,rent:70000,
    tenant_party_id:'tenant-two'},
];
stage.management_agreements=[{id:'mandate-one',agreement_type:'full_management',
  property_ids:['home-one'],landlord_party_id:'owner-one',status:'active',
  spending_limit_pence:15000,signed_at:'2026-10-01',updated_at:'2026-10-01T10:00:00Z'}];
stage.registrations=[{id:'trade-reg-one',party_id:'trade-one',role:'trades',
  name:'Pilot Plumbing',trades:['plumbing'],status:'approved',prospect_stage:'available',
  insurance_expiry:'2099-12-31',
  contractor_verification:{
    status:'verified',registration_id:'trade-reg-one',party_id:'trade-one',
    checked_at:'2026-10-01T10:00:00Z',checked_by:'synthetic-fixture',
    valid_until:'2099-12-31',
    insurance_document_id:'doc-ins',insurance_document_verified_at:'2026-10-01T10:00:00Z',
    qualification_document_id:'doc-qual',qualification_document_verified_at:'2026-10-01T10:00:00Z',
    external_check_reference:'SYNTHETIC-QUALIFICATION-CHECK',
    insurance_check_reference:'SYNTHETIC-INSURANCE-CHECK',
    service_areas:['LEEDS','LS1'],verified_trades:['plumbing']
  }}];
stage.documents=[
  {id:'doc-ins',party_id:'trade-one',document_type:'trades_document',
    status:'verified',verified_at:'2026-10-01T10:00:00Z',
    expiry_date:'2099-12-31',storage_key:'synthetic-insurance-proof',access_roles:['agent','trades']},
  {id:'doc-qual',party_id:'trade-one',document_type:'trades_document',
    status:'verified',verified_at:'2026-10-01T10:00:00Z',
    expiry_date:'2099-12-31',storage_key:'synthetic-trade-proof',access_roles:['agent','trades']}
];
fs.writeFileSync(path.join(root,'users.json'),JSON.stringify(users));
fs.writeFileSync(path.join(root,'stage.json'),JSON.stringify(stage));
const server=spawn('python3',['stage-clone/serve.py'],{
  cwd:process.cwd(),
  env:{...process.env,DATA_DIR:root,BIND_HOST:'127.0.0.1',PORT:'8910',
    ROGER_ENV:'security-lab',ROGER_LAB_HTTP_COOKIES:'1',ROGER_ALLOWED_ORIGINS:base,
    ROGER_STORAGE_BACKEND:'file'},
  stdio:['ignore','pipe','pipe']
});
let output='';
for(const stream of [server.stdout,server.stderr])
  stream.on('data',b=>output=(output+b.toString()).slice(-2500));
let browser,portals={};
async function ready(){
  for(let i=0;i<100;i++){
    if(server.exitCode!==null)throw new Error('server stopped: '+output);
    try{if((await fetch(base+'/api/public')).status===200)return;}catch(_){}
    await new Promise(r=>setTimeout(r,200));
  }
  throw new Error('test server never became ready: '+output);
}
async function login(role){
  const context=await browser.newContext();
  const page=await context.newPage();
  page.setDefaultTimeout(12000);
  const jsErrors=[];
  page.on('pageerror',e=>jsErrors.push(e.message));
  await page.goto(base+'/login');
  await page.locator('#u').fill('pilot-'+role);
  await page.locator('#p').fill(password);
  const target=role==='other-tenant'?'tenant':role;
  await Promise.all([page.waitForURL(base+'/'+target),page.locator('#go').click()]);
  await page.locator('#main[aria-busy="false"]').waitFor();
  return {context,page,jsErrors};
}
async function read(page,api='/api/stage'){
  return page.evaluate(async route=>{
    const r=await fetch(route);
    if(!r.ok)throw new Error(route+' failed '+r.status);
    return r.json();
  },api);
}
async function checkDenied(page,api,body,status=403){
  const result=await page.evaluate(async args=>{
    const r=await fetch(args.api,{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(args.body)});
    return {status:r.status,data:await r.json()};
  },{api,body});
  assert.equal(result.status,status,JSON.stringify(result));
}
async function eventually(page,fn,label){
  let last;
  for(let i=0;i<65;i++){
    last=await read(page);
    if(fn(last))return last;
    await new Promise(r=>setTimeout(r,200));
  }
  throw new Error('State never reached: '+label+'; last='+JSON.stringify(last).slice(0,1800));
}
async function refresh(p){
  await p.reload();
  await p.locator('#main[aria-busy="false"]').waitFor();
}
async function agentView(name){
  const page=portals.agent.page;
  const link=page.locator('nav a[data-view="'+name+'"]');
  if(await link.locator('xpath=ancestor::details').count()){
    const details=page.locator('nav details.mvp-more');
    if(!await details.evaluate(node=>node.open))await details.locator('summary').click();
  }
  await link.click();
  await page.locator('#view-'+name).waitFor({state:'visible'});
}
async function answer(page,values,action){
  const pending=values.slice();
  const responder=d=>{
    if(!pending.length)throw new Error('Unexpected prompt: '+d.message());
    d.accept(pending.shift());
  };
  page.on('dialog',responder);
  try{await action();}finally{page.off('dialog',responder);}
  assert.equal(pending.length,0,'Some expected prompts were not shown');
}
async function scenario(){
  await ready();
  browser=await chromium.launch({headless:true});
  try{
    for(const role of roles)portals[role]=await login(role);
    const tenant=portals.tenant.page,other=portals['other-tenant'].page,
      agent=portals.agent.page,landlord=portals.landlord.page,trade=portals.trades.page;
    // A. Real tenant types and submits, not an agent pretending to be tenant.
    await tenant.locator('#issue-msg').fill('Water leaking under the kitchen sink');
    await tenant.locator('#report-btn').click();
    await eventually(tenant,s=>s.cases?.length===1,'tenant issue submission');
    const first=await read(tenant),cid=first.cases[0].id;
    assert.equal(first.cases[0].status,'reported');
    assert.equal(first.jobs.length,0,'tenant report must not auto-dispatch');
    const foreign=await read(other);
    assert.equal(foreign.cases.length,0);
    assert.equal(foreign.jobs.length,0);
    await checkDenied(other,'/api/case-action',{id:cid,action:'reply',text:'attack',to:['agent']});
    console.log('PASS tenant report + unrelated tenant read/write denial');

    // B. Agent reviews, opens a job, chooses a vetted local trade.
    await refresh(agent);await agentView('cases');
    await answer(agent,['Repair requires a verified plumber','plumbing'],async()=>{
      await agent.locator('#case-'+cid).getByRole('button',{name:/Review.*open repair job/}).click();
    });
    const dispatch=await eventually(agent,s=>s.jobs?.length===1,'agent created job');
    const jid=dispatch.jobs[0].id;
    assert.equal(dispatch.jobs[0].status,'triaged');
    await refresh(agent);await agentView('jobs');
    await agent.locator('#pool-'+jid).selectOption('trade-one');
    await agent.locator('#job-'+jid).getByRole('button',{name:'Request quote before work'}).click();
    await eventually(agent,s=>s.jobs[0].status==='quote_requested','quote requested');
    await checkDenied(other,'/api/job-action',{id:jid,action:'start'});
    console.log('PASS agent review + vetted trade dispatch + denied premature start');

    // C. Trade submits itemised, VAT-aware price; agent reviews it.
    await refresh(trade);
    await trade.locator('#ql-'+jid).fill('250');
    await trade.locator('#qp-'+jid).fill('0');
    await trade.locator('#qvat-'+jid).selectOption('2000');
    await trade.locator('#qn-'+jid).fill('Repair pipe behind sink, labour');
    await trade.locator('#foryou-jobs').getByRole('button',{name:'Send itemised quote'}).click();
    await eventually(trade,s=>s.jobs[0].status==='quoted','trade quote');
    await refresh(agent);await agentView('jobs');
    await agent.locator('#job-'+jid).getByRole('button',{name:'Approve',exact:true}).click();
    await eventually(agent,s=>s.jobs[0].status==='awaiting_prework_approval','landlord gate');
    await checkDenied(trade,'/api/job-action',{id:jid,action:'start'},409);
    console.log('PASS quoted net + VAT; trade blocked while landlord decision pending');

    // D. Landlord approves exact quote above standing authority.
    await refresh(landlord);
    await landlord.locator('#my-approvals').getByRole('button',{name:'Approve',exact:true}).first().click();
    await eventually(landlord,s=>s.jobs[0].status==='assigned','landlord quote approval');
    console.log('PASS landlord pre-work approval via own portal');

    // E. Assigned trade offers visit; resident accepts consented access.
    await refresh(trade);
    await answer(trade,['2099-05-20 09:00'],async()=>{
      await trade.locator('#foryou-jobs').getByRole('button',{name:'Propose visit'}).click();
    });
    await eventually(trade,s=>s.jobs[0].status==='assigned','visit proposed with authorised job');
    await refresh(tenant);
    await tenant.locator('#my-appts').getByRole('button',{name:'Confirm visit'}).waitFor();
    const appointments=await read(tenant,'/api/appointments');
    const appointment=appointments.appointments[0];
    assert.equal(appointment.status,'proposed');
    await tenant.locator('#access-'+appointment.id).fill('Please ring the bell');
    await tenant.locator('#consent-'+appointment.id).check();
    await tenant.locator('#my-appts').getByRole('button',{name:'Confirm visit'}).click();
    await eventually(tenant,async()=>true,'tenant confirmation'); // confirmed by appointment API below
    const confirmed=await read(tenant,'/api/appointments');
    assert.equal(confirmed.appointments[0].status,'confirmed');
    await refresh(trade);
    assert.match(await trade.locator('#my-visits').innerText(),/ring the bell/);
    console.log('PASS contractor proposed visit + tenant explicitly confirmed access');

    // F. Work starts, contractor asks for an extra; landlord approves new limit.
    await trade.locator('#foryou-jobs').getByRole('button',{name:'Start job'}).click();
    await eventually(trade,s=>s.jobs[0].status==='in_progress','work started');
    await refresh(trade);
    await trade.locator('#var-'+jid).fill('50');
    await trade.locator('#vnote-'+jid).fill('Extra isolation valve');
    await trade.locator('#vvat-'+jid).selectOption('0');
    await trade.locator('#my-jobs').getByRole('button',{name:'Request approval for extra work'}).click();
    await eventually(trade,s=>!!s.jobs[0].pending_variation,'variation submitted');
    await checkDenied(trade,'/api/job-action',{id:jid,action:'complete',invoice_pence:35000},409);
    await refresh(agent);await agentView('jobs');
    await agent.locator('#job-'+jid).getByRole('button',{name:'Review extra-work cost'}).click();
    await eventually(agent,s=>s.jobs[0].pending_variation?.status==='pending_landlord','variation landlord gate');
    await refresh(landlord);
    await landlord.locator('#my-approvals').getByRole('button',{name:'Approve',exact:true}).first().click();
    await eventually(landlord,s=>s.jobs[0].approved_quote_pence===35000,'extra scope approved');
    console.log('PASS extra work cannot bypass exact landlord approval');

    // G. Tradesman submits numbered invoice after work, tenant confirms fix.
    await refresh(trade);
    await trade.locator('#invnum-'+jid).fill('PILOT-2026-001');
    await trade.locator('#inv-'+jid).fill('350');
    await trade.locator('#invat-'+jid).selectOption('0');
    await trade.locator('#my-jobs').getByRole('button',{name:'Job done — submit invoice'}).click();
    await eventually(trade,s=>s.jobs[0].status==='invoice_submitted','invoice submitted');
    await refresh(tenant);
    await tenant.locator('#my-cases').getByRole('button',{name:'This is fixed'}).click();
    await eventually(tenant,s=>s.cases[0].status==='closed','tenant confirmed resolution');
    console.log('PASS supplier invoice and tenant confirmation; no payment yet');

    // H. Agent approves invoice, records two actual EXTERNAL references and a credit.
    await refresh(agent);await agentView('jobs');
    await agent.locator('#job-'+jid).getByRole('button',{name:'Approve invoice'}).click();
    await eventually(agent,s=>s.jobs[0].status==='invoice_approved','invoice approval');
    const date=new Date().toISOString().slice(0,10);
    await refresh(agent);await agentView('jobs');
    await answer(agent,['100','PILOT-BANK-001',date],async()=>{
      await agent.locator('#job-'+jid).getByRole('button',{name:'Record verified external payment'}).click();
    });
    await eventually(agent,s=>s.jobs[0].status==='partially_paid','part payment');
    await refresh(agent);await agentView('jobs');
    await answer(agent,['PILOT-CREDIT-001','Accepted price reduction','50'],async()=>{
      await agent.locator('#job-'+jid).getByRole('button',{name:'Record supplier credit note'}).click();
    });
    await eventually(agent,s=>s.jobs[0].balance_due_pence===20000,'credit reduced balance');
    await refresh(agent);await agentView('jobs');
    await answer(agent,['200','PILOT-BANK-002',date],async()=>{
      await agent.locator('#job-'+jid).getByRole('button',{name:'Record verified external payment'}).click();
    });
    const final=await eventually(agent,s=>s.jobs[0].status==='paid','fully externally settled');
    assert.equal(final.jobs[0].balance_due_pence,0);
    assert.equal(final.jobs[0].payments.length,2);
    assert.equal(final.jobs[0].credit_notes.length,1);
    assert.equal(final.jobs[0].payments.reduce((n,p)=>n+p.amount_pence,0),30000);
    assert.equal(final.jobs[0].credit_notes[0].amount_pence,5000);
    assert.equal(final.cases[0].status,'closed');
    await refresh(landlord);
    const visible=await landlord.locator('#statement').innerText();
    assert.match(visible,/300/,'landlord amount must reflect payments, not invoice plus credit');
    await refresh(other);
    assert.equal((await read(other)).jobs.length,0);
    for(const [name,portal] of Object.entries(portals))
      assert.deepEqual(portal.jsErrors,[],name+' JavaScript errors');
    console.log('PASS invoice approval + two external payments + supplier credit + landlord totals + privacy');
    console.log('FULL FOUR-ROLE REPAIR BROWSER JOURNEY PASSED');
  }catch(err){
    const dir='browser-results';
    fs.mkdirSync(dir,{recursive:true});
    for(const [name,p] of Object.entries(portals))
      await p.page.screenshot({path:path.join(dir,'repair-'+name+'-failure.png'),fullPage:true}).catch(()=>{});
    throw err;
  }finally{
    for(const p of Object.values(portals))await p.context.close().catch(()=>{});
    await browser.close();
  }
}
scenario().catch(e=>{console.error(e.stack||String(e));process.exitCode=1})
  .finally(()=>{server.kill();fs.rmSync(root,{recursive:true,force:true})});
