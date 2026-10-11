/* Task 01 real browser test: trade -> tenant -> agent -> failed access -> new visit.
 * Entirely synthetic, isolated on 127.0.0.1:8902. Never contacts the live server.
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn } = require('node:child_process');
const assert = require('node:assert/strict');

const base = 'http://127.0.0.1:8902';
const password = 'visit-ci-only-password';
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'roger-visit-ci-'));
const accounts = {};
const users = { users: [], sessions: {} };
const stage = JSON.parse(fs.readFileSync('stage-clone/stage.json','utf8'));
const roles = ['agent','tenant','landlord','trades','other-tenant'];
for (const role of roles) {
  const account_id = 'account-' + role;
  const salt = crypto.randomBytes(16).toString('hex');
  users.users.push({
    username: 'visit-' + role, display_name: 'Visit ' + role,
    role: role === 'other-tenant' ? 'tenant' : role,
    account_id, salt,
    hash: crypto.scryptSync(password, Buffer.from(salt,'hex'),64,
      { N:16384, r:8, p:1, maxmem:64*1024*1024 }).toString('hex')
  });
  accounts[role]=account_id;
}
stage.parties = [
  {id:'party-tenant',roles:['tenant'],status:'active',account_id:accounts.tenant,display_name:'Visit tenant'},
  {id:'party-other',roles:['tenant'],status:'active',account_id:accounts['other-tenant'],display_name:'Other tenant'},
  {id:'party-landlord',roles:['landlord'],status:'active',account_id:accounts.landlord,display_name:'Visit landlord'},
  {id:'party-trade',roles:['trades'],status:'active',account_id:accounts.trades,display_name:'Visit trades'}
];
stage.properties = [
  {id:'property-visit',title:'Test Property',area:'Leeds',beds:2,rent:90000,
    tenant_party_id:'party-tenant',landlord_party_id:'party-landlord'},
  {id:'property-other',title:'Other Property',area:'York',beds:1,rent:65000,
    tenant_party_id:'party-other'}
];
stage.cases = [{id:51,property_id:'property-visit',tenant_party_id:'party-tenant',
  message:'Synthetic leaking tap',status:'dispatched',thread:[],triage:{urgency:0,safety:0}}];
stage.jobs = [{id:'job-visit',case_id:51,property_id:'property-visit',
  message:'Repair leaking tap',status:'assigned',assigned_to:'Visit trades',
  assigned_to_party_id:'party-trade',required_trade:'plumbing',
  requires_prework_quote:true,approved_quote_pence:12000,
  work_authorised_at:'2026-10-01T10:00:00Z'}];
stage.approvals=[];stage.appointments=[];stage.documents=[];
stage.registrations=[{id:'reg-visit',party_id:'party-trade',role:'trades',name:'Visit trades',
  status:'approved',trades:['plumbing'],credentials_checked_at:'2026-10-01T10:00:00Z',
  insurance_expiry:'2099-12-31'}];
stage.audit_log=[];
stage.authority={standing_limit_pence:15000};
fs.writeFileSync(path.join(dir,'stage.json'),JSON.stringify(stage));
fs.writeFileSync(path.join(dir,'users.json'),JSON.stringify(users));

const server=spawn('python3',['stage-clone/serve.py'],{
  cwd:process.cwd(), env:{...process.env, DATA_DIR:dir,PORT:'8902',
    BIND_HOST:'127.0.0.1',ROGER_ENV:'security-lab',
    ROGER_LAB_HTTP_COOKIES:'1',ROGER_ALLOWED_ORIGINS:base},
  stdio:['ignore','pipe','pipe']
});
let serverLog='';
for(const stream of [server.stdout,server.stderr])
  stream.on('data',buf=>{serverLog+=buf.toString().slice(0,1000)});
let browser;
async function ready(){
  for(let i=0;i<75;i++){
    if(server.exitCode!==null)throw Error('Server stopped: '+serverLog);
    try{const r=await fetch(base+'/api/public');if(r.status===200)return;}catch(_){}
    await new Promise(resolve=>setTimeout(resolve,200));
  }
  throw Error('Test server did not start: '+serverLog);
}
async function login(role){
  const ctx=await browser.newContext();
  const page=await ctx.newPage();
  await page.goto(base+'/login');
  await page.locator('#u').fill('visit-'+role);
  await page.locator('#p').fill(password);
  await Promise.all([
    page.waitForURL(base+'/'+(role==='other-tenant'?'tenant':role)),
    page.locator('#go').click()
  ]);
  await page.locator('#main[aria-busy="false"]').waitFor();
  return {page,ctx};
}
async function contains(page,selector,text){
  await page.locator(selector).getByText(text,{exact:false}).first().waitFor({timeout:15000});
}
async function scenario(){
  await ready();
  browser=await chromium.launch({headless:true});
  const trade=await login('trades');
  const tenant=await login('tenant');
  const agent=await login('agent');
  const stranger=await login('other-tenant');
  try{
    assert.equal((await stranger.page.evaluate(async()=>(
      await (await fetch('/api/appointments')).json()).appointments)).length,0);
    assert.equal((await stranger.page.evaluate(async()=>(
      await (await fetch('/api/stage')).json()).jobs)).length,0);

    trade.page.once('dialog',dialog=>dialog.accept('2099-05-20 09:00'));
    await trade.page.getByRole('button',{name:'Propose visit'}).first().click();
    await contains(trade.page,'#my-visits','Waiting for tenant confirmation');
    await tenant.page.reload();
    await tenant.page.locator('#main[aria-busy="false"]').waitFor();
    await tenant.page.locator('#access-appt-1').fill('Please ring the front bell');
    await tenant.page.locator('#consent-appt-1').check();
    await tenant.page.getByRole('button',{name:'Confirm visit'}).click();
    await contains(tenant.page,'#my-appts','confirmed');

    await agent.page.reload();
    await agent.page.locator('#main[aria-busy="false"]').waitFor();
    const link=agent.page.locator('nav a[data-view="appointments"]');
    if(await link.locator('xpath=ancestor::details').count())
      await agent.page.locator('nav details.mvp-more summary').click();
    await link.click();
    await contains(agent.page,'#view-appointments','confirmed');

    await trade.page.reload();
    await trade.page.locator('#main[aria-busy="false"]').waitFor();
    await contains(trade.page,'#my-visits','Please ring the front bell');
    trade.page.once('dialog',dialog=>dialog.accept('Tenant not home'));
    await trade.page.getByRole('button',{name:'No access'}).click();
    await contains(trade.page,'#my-visits','no access');

    const dialogAnswers=['2099-05-21 10:00','After missed access'];
    const answerDialog=dialog=>dialog.accept(dialogAnswers.shift()||'');
    trade.page.on('dialog',answerDialog);
    await trade.page.getByRole('button',{name:'Offer another time'}).click();
    trade.page.off('dialog',answerDialog);
    await contains(trade.page,'#my-visits','proposed');

    await tenant.page.reload();
    await tenant.page.locator('#main[aria-busy="false"]').waitFor();
    await tenant.page.getByRole('button',{name:'Confirm visit'}).click();
    await contains(tenant.page,'#my-appts','confirmed');
    await trade.page.reload();
    await trade.page.locator('#main[aria-busy="false"]').waitFor();
    const visible=await trade.page.locator('#my-visits').innerText();
    assert.ok(!visible.includes('Please ring the front bell'),
      'Old access preference must not survive reproposal or be shown without renewed consent');
    trade.page.once('dialog',dialog=>dialog.accept('Part on order'));
    await trade.page.getByRole('button',{name:'Parts delayed'}).click();
    await contains(trade.page,'#my-visits','parts delay');
    const json=JSON.parse(fs.readFileSync(path.join(dir,'stage.json'),'utf8'));
    assert.equal(json.appointments.length,1);
    assert.equal(json.appointments[0].status,'parts_delay');
    assert.equal(json.jobs[0].status,'assigned',
      'A delayed visit must not close the repair or submit an invoice');
    assert.equal(json.appointments[0].history.filter(h=>h.action==='confirm').length,2);
    console.log('PASS visits: trade proposal → tenant consent → agent visibility → no access → rebook → parts delay');
    console.log('PASS privacy: unrelated tenant denied; access preference withdrawn on reschedule');
  }finally{
    await Promise.all([trade,tenant,agent,stranger].map(x=>x.ctx.close()));
  }
}
scenario().catch(e=>{console.error(e.stack||String(e));process.exitCode=1})
  .finally(async()=>{
    if(browser)await browser.close();
    server.kill();
    fs.rmSync(dir,{recursive:true,force:true});
  });
