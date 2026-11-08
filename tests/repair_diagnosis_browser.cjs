/* Disposable Chromium test of Roger's opt-in tenant repair interview.
 * No production data, server or model credentials. Start from repo root:
 *   node tests/repair_diagnosis_browser.cjs
 * Set EXPECT_OLLAMA=1 when a working local Ollama text model is configured.
 * Set EXPECT_VISION=1 in addition when a local vision model is configured.
 */
'use strict';
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');

const base = 'http://127.0.0.1:8921';
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'roger-diagnose-browser-'));
const password = 'disposable-diagnostic-test-password';
const stage = JSON.parse(fs.readFileSync('stage-clone/stage.json','utf8'));
for (const field of ['properties','cases','jobs','approvals','documents','registrations',
  'appointments','invitations','audit_log','parties','tenancies','management_agreements',
  'notifications','property_submissions','rent_ledger_entries','landlord_statements',
  'tasks','compliance_records']) stage[field]=[];
stage.next_case_id=100;
stage.properties=[
  {id:'house-one', title:'Synthetic Kitchen Flat',area:'Leeds',tenant_party_id:'tenant-one'},
  {id:'house-two', title:'Unrelated Flat',area:'York',tenant_party_id:'tenant-other'}
];
stage.parties=[
  {id:'tenant-one',account_id:'account-one',roles:['tenant'],status:'active',display_name:'Resident One'},
  {id:'tenant-other',account_id:'account-other',roles:['tenant'],status:'active',display_name:'Resident Other'}
];
// Two synthetic assured-periodic tenancies exercise the new 2026 policy and inspection UI.
stage.properties[0].lifecycle_status='occupied';
stage.properties[1].lifecycle_status='occupied';
stage.next_inventory_id=1;
stage.tenancies=[
 {id:'tenancy-one',property_id:'house-one',tenant_party_ids:['tenant-one'],
  landlord_party_ids:[],status:'active',tenancy_type:'assured_periodic',
  start_date:'2025-01-01',rent_amount_pence:90000,rent_frequency:'monthly',
  agreement_status:'signed',pet_requests:[],history:[]},
 {id:'tenancy-two',property_id:'house-two',tenant_party_ids:['tenant-other'],
  landlord_party_ids:[],status:'active',tenancy_type:'assured_periodic',
  start_date:'2025-01-01',rent_amount_pence:100000,rent_frequency:'monthly',
  agreement_status:'signed',pet_requests:[],history:[]}
];
const users={users:[],sessions:{}};
for(const [username,role,account_id] of [['tenant-one','tenant','account-one'],
                                         ['tenant-other','tenant','account-other'],
                                         ['agent-one','agent','account-agent']]){
  const salt=crypto.randomBytes(16).toString('hex');
  users.users.push({
    username,role,account_id,display_name:username,
    salt,hash:crypto.scryptSync(password,Buffer.from(salt,'hex'),64,
      {N:16384,r:8,p:1,maxmem:64*1024*1024}).toString('hex')
  });
}
fs.writeFileSync(path.join(root,'stage.json'),JSON.stringify(stage));
fs.writeFileSync(path.join(root,'users.json'),JSON.stringify(users));

const server=spawn('python3',['stage-clone/serve.py'],{
  cwd:process.cwd(),
  env:{
    ...process.env, DATA_DIR:root,BIND_HOST:'127.0.0.1',PORT:'8921',
    ROGER_ENV:'security-lab',ROGER_LAB_HTTP_COOKIES:'1',
    ROGER_ALLOWED_ORIGINS:base,ROGER_STORAGE_BACKEND:'file'
  },
  stdio:['ignore','pipe','pipe']
});
let output='';
for(const stream of [server.stdout,server.stderr])
  stream.on('data',bytes=>output=(output+bytes.toString()).slice(-3000));

let browser;
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function ready(){
  for(let i=0;i<90;i++){
    if(server.exitCode!==null) throw new Error('Roger test server stopped: '+output);
    try {if((await fetch(base+'/api/public')).status===200)return;}catch(_) {}
    await sleep(200);
  }
  throw new Error('Roger test server did not start: '+output);
}
async function login(username){
  const context=await browser.newContext();
  const page=await context.newPage();
  const errors=[];
  page.on('pageerror',err=>errors.push(err.message));
  await page.goto(base+'/login');
  await page.locator('#u').fill(username);
  await page.locator('#p').fill(password);
  const role=username==='agent-one'?'agent':'tenant';
  await Promise.all([
    page.waitForURL(base+'/'+role,{timeout:20000}),
    page.locator('#go').click()
  ]);
  await page.locator('#main[aria-busy="false"]').waitFor({timeout:20000});
  return {context,page,errors};
}
async function getCases(page){
  return page.evaluate(async ()=>{
    const r=await fetch('/api/stage');
    assertBrowser(r.ok, 'stage must be available');
    const data=await r.json();
    return data.cases;
    function assertBrowser(ok,msg){if(!ok)throw new Error(msg);}
  });
}
async function diagnoseByApi(page,payload){
  return page.evaluate(async body=>{
    const r=await fetch('/api/repair-diagnose',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)
    });
    return {status:r.status,data:await r.json()};
  },payload);
}
async function run(){
  await ready();
  browser=await chromium.launch({headless:true});
  const resident=await login('tenant-one');
  const tenant=resident.page;
  try{
    await tenant.locator('#pet-request-tenancy-one').fill('One indoor cat');
    await tenant.locator('#tenancy-info button[data-tenancy-id="tenancy-one"]').click();
    await tenant.getByText('pending_agent_review').first().waitFor({timeout:15000});
    assert.equal(await tenant.locator('#pet-request-tenancy-two').count(),0);
    console.log('PASS: tenant can request a pet for their own tenancy only');
    assert.equal(await tenant.locator('#repair-interview').isVisible(),false);
    await tenant.locator('#issue-msg').fill('Water is leaking under the kitchen sink');
    await tenant.locator('#issue-email').fill('synthetic-resident@example.invalid');
    await tenant.getByRole('button',{name:'Help me describe this problem (experimental)'}).click();
    await tenant.waitForFunction(()=>{
      const q=document.getElementById('repair-question');
      const engine=document.getElementById('repair-engine');
      return q && q.textContent.trim() &&
        !q.textContent.includes('Reviewing your description') &&
        engine && engine.textContent.trim();
    },null,{timeout:45000});
    console.log('Interview first question:',(await tenant.locator('#repair-question').innerText()).slice(0,150));
    const engine=await tenant.locator('#repair-engine').innerText();
    if(process.env.EXPECT_OLLAMA==='1'){
      assert.match(engine,/Local AI suggestions/);
    }else{
      assert.match(engine,/Guided rules/);
    }
    assert.equal((await getCases(tenant)).length,0);
    console.log('PASS: interview is opt-in and creates no repair case');
    // Model questions are unpredictable; answer three rounds and confirm there is a report.
    for(let i=0;i<3;i++){
      if(await tenant.locator('#repair-answer-field').isVisible()){
        await tenant.locator('#repair-answer').fill('Synthetic observation number '+(i+1));
        await tenant.locator('#repair-next').click();
        await tenant.locator('#repair-question').waitFor({state:'visible'});
        await tenant.waitForFunction(()=>{
          const answer=document.getElementById('repair-answer');
          const question=document.getElementById('repair-question');
          return answer && answer.value==='' && question &&
            !question.textContent.includes('Reviewing your description');
        },null,{timeout:20000});
      }
    }
    await tenant.getByRole('button',{name:'Use interview in my report'}).click();
    const report=await tenant.locator('#issue-msg').inputValue();
    assert.match(report,/Tenant's initial description:/);
    assert.match(report,/Synthetic observation number 3/);
    assert.equal((await getCases(tenant)).length,0);
    await tenant.locator('#report-btn').click();
    await tenant.waitForFunction(async ()=>{
      const r=await fetch('/api/stage');
      if(!r.ok)return false;
      return (await r.json()).cases?.length===1;
    },null,{timeout:20000});
    const cases=await getCases(tenant);
    assert.match(cases[0].message,/Tenant's initial description:/);
    assert.equal(cases[0].property_id,'house-one');
    assert.equal(cases[0].diagnostic_dossier.schema,'roger-repair-interview-v1');
    assert.equal(cases[0].diagnostic_dossier.answers.length,3);
    assert.equal(cases[0].diagnostic_dossier.source,'tenant_submitted_unverified');
    console.log('PASS: three questions → review → explicit Send report → one saved case');

    await tenant.locator('#issue-msg').fill('I smell gas in the kitchen');
    await tenant.getByRole('button',{name:'Help me describe this problem (experimental)'}).click();
    await tenant.locator('#repair-warning').waitFor({state:'visible',timeout:25000});
    assert.match(await tenant.locator('#repair-warning').innerText(),/0800 111 999/);
    assert.equal(await tenant.locator('#repair-answer-field').isVisible(),false);
    assert.equal((await getCases(tenant)).length,1);
    console.log('PASS: suspected gas leak stops interview and displays emergency instructions');

    const separate=await login('tenant-other');
    try{
      const denied=await diagnoseByApi(separate.page,{
        property_id:'house-one',description:'water leaking'
      });
      assert.equal(denied.status,403);
      assert.match(denied.data.error,/not your property/);
      const briefingDenied=await separate.page.evaluate(async()=>(
        await fetch('/api/agent/briefing')).status);
      assert.equal(briefingDenied,403);
      const inventoryDenied=await separate.page.evaluate(async()=>{
        const response=await fetch('/api/inventories');
        return (await response.json()).inventories.length;
      });
      assert.equal(inventoryDenied,0);
      const crossDeposits=await separate.page.evaluate(async()=>{
        const response=await fetch('/api/deposits');
        return (await response.json()).deposits.length;
      });
      assert.equal(crossDeposits,0);
      console.log('PASS: different tenant cannot diagnose an unrelated property or access Agent Desk briefing');
    }finally{await separate.context.close();}

    const agent=await login('agent-one');
    try{
      const stage=await agent.page.evaluate(async()=> (await(await fetch('/api/stage')).json()));
      assert.equal(stage.cases.length,1);
      assert.match(stage.cases[0].message,/Synthetic observation number 3/);
      assert.equal(stage.cases[0].diagnostic_dossier.answers.length,3);
      const summary=await agent.page.evaluate(async()=>{
        const r=await fetch('/api/agent/briefing');
        if(!r.ok)throw new Error('Agent briefing endpoint: '+r.status);
        return r.json();
      });
      assert.equal(summary.engine,'deterministic-rules');
      assert.equal(summary.read_only,true);
      assert(summary.cards.some(card=>card.key==='case:100'));
      await agent.page.locator('#view-overview').getByText('Operational priorities').first().waitFor();
      await agent.page.locator('nav a[data-view="cases"]').click();
      await agent.page.locator('#case-100').getByText('Tenant diagnostic interview · unverified').waitFor();
      // Human-reviewed pet response and real rent notice record on Agent Desk.
      await agent.page.locator('details.mvp-more > summary').click();
      await agent.page.locator('nav a[data-view="people"]').click();
      await agent.page.locator('#tenancy-one details.msgs > summary').click();
      await agent.page.locator('#tenancy-one .pet-reason').fill('Agent reviewed the request and recorded consent.');
      await agent.page.locator('#tenancy-one').getByRole('button',{name:'Approve pet'}).click();
      await agent.page.waitForFunction(async()=>{
        const r=await fetch('/api/stage');
        if(!r.ok)return false;
        const t=(await r.json()).tenancies?.find(x=>x.id==='tenancy-one');
        return t?.pet_requests?.[0]?.status==='approved';
      },null,{timeout:15000});
      await agent.page.locator('#tenancy-one details.msgs > summary').click();
      await agent.page.locator('#tenancy-one .rent-change-amount').fill('950');
      await agent.page.locator('#tenancy-one .rent-change-notice').fill('2026-08-01');
      await agent.page.locator('#tenancy-one .rent-change-effective').fill('2026-10-01');
      await agent.page.locator('#tenancy-one').getByRole('button',{name:'Record proposed rent increase'}).click();
      await agent.page.waitForFunction(async()=>{
        const r=await fetch('/api/stage');
        if(!r.ok)return false;
        const t=(await r.json()).tenancies?.find(x=>x.id==='tenancy-one');
        return t?.pending_rent_increase?.proposed_rent_pence===95000;
      },null,{timeout:15000});
      console.log('PASS: agent can review pet request and record a Section 13 rent proposal');

      // Agent drafts, records room condition, then issues an immutable inspection.
      await agent.page.locator('details.mvp-more > summary').click();
      await agent.page.locator('nav a[data-view="inventories"]').click();
      await agent.page.locator('#inventory-tenancy').selectOption('tenancy-one');
      await agent.page.locator('#inventory-kind').selectOption('check_in');
      await agent.page.locator('#inventory-date').fill('2026-11-08');
      await agent.page.getByRole('button',{name:'Create inspection'}).click();
      await agent.page.locator('#inventory-inventory-1').waitFor({timeout:15000});
      await agent.page.locator('#inventory-inventory-1 .room-label').fill('Kitchen');
      await agent.page.locator('#inventory-inventory-1 .room-condition').fill('Walls in good condition');
      await agent.page.locator('#inventory-inventory-1').getByRole('button',{name:'Record room condition'}).click();
      await agent.page.locator('#inventory-inventory-1').getByText('Walls in good condition').waitFor({timeout:15000});
      agent.page.once('dialog',d=>d.accept());
      await agent.page.locator('#inventory-inventory-1').getByRole('button',{name:'Issue inventory to tenant'}).click();
      await agent.page.waitForFunction(async()=>{
        const r=await fetch('/api/inventories');
        if(!r.ok)return false;
        return (await r.json()).inventories?.find(x=>x.id==='inventory-1')?.status==='issued';
      },null,{timeout:15000});
      console.log('PASS: agent created and issued a dated property condition inventory');
      // Funds are never moved; an agent merely records an unverified deposit receipt.
      await agent.page.evaluate(()=>window.scrollTo(0,0));
      await agent.page.locator('nav a[data-view="money"]').click({force:true});
      await agent.page.locator('#dep-tenancy').selectOption('tenancy-one');
      await agent.page.locator('#dep-kind').selectOption('tenancy');
      await agent.page.locator('#dep-amount').fill('900');
      await agent.page.locator('#dep-date').fill('2026-11-01');
      await agent.page.getByRole('button',{name:'Record receipt (unverified)'}).click();
      await agent.page.waitForFunction(async()=>{
        const r=await fetch('/api/deposits');
        return r.ok && (await r.json()).deposits?.some(d=>
          d.tenancy_id==='tenancy-one'&&d.amount_pence===90000&&d.status==='received_unverified');
      },null,{timeout:15000});
      const auditAfterDeposit=await agent.page.evaluate(async()=>{
        const r=await fetch('/api/stage'),d=await r.json();
        return {deposits:(d.deposit_records||[]).length,
                tail:(d.audit_log||[]).slice(-5).map(x=>x.action)};
      });
      console.log('Synthetic stage immediately after deposit action:',JSON.stringify(auditAfterDeposit));
      assert(auditAfterDeposit.tail.includes('deposit_receipt_recorded_unverified'),
             'Deposit receipt must be committed and audited before proceeding');
      console.log('PASS: agent recorded a distinct unverified tenancy deposit with protection deadline');

      console.log('PASS: Agent Desk briefing and structured diagnostic evidence are visible with correct permissions');
    }finally{await agent.context.close();}

    const auditLogin=await login('agent-one');
    try{
      const summary=await auditLogin.page.evaluate(async()=>{
        const r=await fetch('/api/deposits');
        return (await r.json()).deposits.map(x=>({id:x.id,tenancy_id:x.tenancy_id}));
      });
      console.log('Synthetic agent deposit records after separate login:',JSON.stringify(summary));
      const stateDebug=await auditLogin.page.evaluate(async()=>{
        const r=await fetch('/api/stage'),d=await r.json();
        return {deposits:d.deposit_records||[],events:(d.audit_log||[]).slice(-8).map(x=>x.action)};
      });
      console.log('Synthetic stage deposit persistence and latest event types:',JSON.stringify(stateDebug));
    }finally{await auditLogin.context.close();}
    const depositBeforeInventory=await tenant.evaluate(async()=>{
      const r=await fetch('/api/deposits');
      return r.ok?(await r.json()).deposits:[];
    });
    console.log('Synthetic tenant deposit count before inventory acknowledgement:',depositBeforeInventory.length);
    await tenant.reload({waitUntil:'domcontentloaded'});
    await tenant.locator('#main[aria-busy="false"]').waitFor({timeout:15000});
    await tenant.locator('#tenant-inventory-inventory-1').getByText('Walls in good condition').waitFor({timeout:15000});
    await tenant.locator('#tenant-inventory-inventory-1 .inspection-feedback').fill('There is a scratch near the sink.');
    await tenant.locator('#tenant-inventory-inventory-1').getByRole('button',{name:'Dispute an item'}).click();
    await tenant.locator('#tenant-inventory-inventory-1').getByText('Disputed').first().waitFor({timeout:15000});
    const policy=await tenant.evaluate(async()=> (await(await fetch('/api/tenancy-policy')).json()));
    const deposits=await tenant.evaluate(async()=> (await(await fetch('/api/deposits')).json()));
    console.log('Synthetic tenant policy/deposit scoping:',JSON.stringify({tenancies:policy.tenancies.map(t=>t.id),deposits:deposits.deposits.map(d=>({id:d.id,tenancy_id:d.tenancy_id}))}));
    assert.equal(deposits.deposits.length,1);
    assert.equal(deposits.deposits[0].amount_pence,90000);
    assert.equal(deposits.deposits[0].status,'received_unverified');
    await tenant.locator('#tenant-deposits').getByText('£900.00').waitFor({timeout:15000});
    assert.equal(policy.tenancies.length,1);
    assert.equal(policy.tenancies[0].pet_requests[0].status,'approved');
    assert(policy.tenancies[0].pending_rent_increase);
    console.log('PASS: tenant sees approved pet, proposed rent, issued inventory and can dispute it');

    // A real small PNG; no AI visual inference without a configured vision model.
    const png=Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg==',
      'base64');
    await tenant.locator('#issue-msg').fill('Kitchen tap dripping near the pipe');
    await tenant.locator('#issue-files').setInputFiles({
      name:'synthetic-pipe.png',mimeType:'image/png',buffer:png
    });
    await tenant.getByRole('button',{name:'Help me describe this problem (experimental)'}).click();
    await tenant.locator('#repair-engine').getByText(/photo/).waitFor({timeout:25000});
    const imgStatus=await tenant.locator('#repair-engine').innerText();
    if(process.env.EXPECT_VISION==='1'){
      assert.match(imgStatus,/photo analysed by local AI/);
      console.log('PASS: local vision model returned a result for an image');
    }else{
      assert.match(imgStatus,/photo not analysed/);
      console.log('PASS: image not analysed is disclosed honestly without vision');
    }
    if(resident.errors.length)throw new Error('Tenant browser JavaScript errors: '+resident.errors.join('; '));
    console.log('REPAIR DIAGNOSIS CHROMIUM TEST PASSED');
  }catch(error){
    fs.mkdirSync('browser-results',{recursive:true});
    await tenant.screenshot({path:'browser-results/repair-diagnosis-failure.png',fullPage:true}).catch(()=>{});
    throw error;
  }finally{await resident.context.close();}
}
run().catch(e=>{console.error(e.stack||e);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();
  server.kill('SIGTERM');
  fs.rmSync(root,{recursive:true,force:true});
});
