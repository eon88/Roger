"use strict";
const status = document.getElementById("status");
const form = document.getElementById("registration");
const error = document.getElementById("error");
const match = location.hash.match(/^#token=([A-Za-z0-9_-]{30,128})$/);
const token = match ? match[1] : null;
// Remove the bearer token from the visible URL and browser history.
if (token) history.replaceState(null, "", "/invite");
async function post(route, body) {
  const r = await fetch(route, {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body),
    cache:"no-store", credentials:"same-origin"
  });
  return {ok:r.ok, body:await r.json()};
}
async function init() {
  if (!token) { status.textContent="This invitation link is missing or invalid."; return; }
  try {
    const r = await post("/api/invite/validate", {token});
    if (!r.ok || !r.body.valid) {
      status.textContent="This invitation is invalid, expired or has already been used. Ask the agency for a new one.";
      return;
    }
    status.textContent="Invitation verified. Please choose your login details.";
    document.getElementById("role").textContent="Portal role: " + r.body.role;
    if (typeof r.body.agency === "string") document.getElementById("brand").textContent=r.body.agency+" portal";
    form.hidden=false;
  } catch (_) {
    status.textContent="Could not verify the invitation. Try again or contact the agency.";
  }
}
form.addEventListener("submit", async event => {
  event.preventDefault(); error.textContent="";
  const username=document.getElementById("username").value;
  const password=document.getElementById("password").value;
  if(password!==document.getElementById("confirm").value){
    error.textContent="Passwords do not match."; return;
  }
  const submit=document.getElementById("accept"); submit.disabled=true;
  try {
    const r=await post("/api/invite/accept",{token,username,password});
    if(!r.ok){error.textContent=r.body.error||"Could not create account.";return;}
    form.hidden=true;
    status.textContent="Your login has been created. Sign in using your new username and password.";
    const link=document.createElement("a");
    link.href="/login";link.textContent="Go to secure sign in";
    status.append(" ",link);
  } catch (_) { error.textContent="Could not contact the portal."; }
  finally {submit.disabled=false;}
});
init();
