# Roger repair diagnosis experiment — 8 November 2026

**Status:** Isolated experiment; not deployed. Branch: `experiment/roger-repair-diagnostics-20261108`, based on `feature/roger-saas-hostinger-staging-safeguards-20261013`.

## Goal

Learn from the tenant → AI triage → agent → contractor workflow used by modern maintenance products, without copying proprietary source code, then improve Roger after establishing a reliable baseline.

## What is built

- Optional **Help me describe this problem** button in the signed-in Tenant portal.
- Stateless POST `/api/repair-diagnose`, accessible only to a tenant linked to the supplied property or an agent.
- Three symptom questions, safety-screened before optional model inference.
- Rule-only fallback when no AI model is available; clearly labelled as rules in the portal.
- Optional local Ollama text model for customised interview questions and tentative cause.
- Optional **separately configured vision model** for one JPEG, PNG or WebP photo (maximum 1 MB); the result is labelled unverified. If no vision model is available, the interface explicitly says the photo was NOT analysed.
- Tenant reviews and optionally copies the interview report into the normal maintenance form. **Only clicking Send report creates the existing repair case.** Existing attachments remain in the normal report workflow.
- Existing agent, landlord, trades, quote, spending, credential and financial approval controls are unchanged.

## Local setup

In a disposable checkout of the experimental branch, run the existing Roger development setup:

```bash
cd stage-clone
python3 make_users.py   # first run, synthetic accounts only
python3 serve.py
```

Sign in as a tenant with a property link at `http://127.0.0.1:8901/tenant`. Describe a fault and click **Help me describe this problem (experimental)**.

By default **no AI model is contacted**. The interview runs with visible rule-based guidance.

To enable optional local AI, first install/start Ollama and a compatible model. Set these environment variables **before starting the Roger server**:

```bash
export ROGER_OLLAMA_BASE_URL=http://127.0.0.1:11434
export ROGER_REPAIR_TEXT_MODEL=<your-installed-text-model>
export ROGER_REPAIR_VISION_MODEL=<your-installed-vision-model>  # optional
```

For PowerShell, use `$env:ROGER_REPAIR_TEXT_MODEL="name-of-installed-model"`, and similarly for the others. The diagnostic service uses Ollama's `/api/chat`. Images are only supplied to Ollama when `ROGER_REPAIR_VISION_MODEL` is configured. **No cloud API or downloads are required by this feature**, but real AI behaviour depends on your separately installed models.

## Safety and privacy boundaries

- This is not an emergency line. Gas/fire/electrical/flood warnings show explicit advice to leave danger and contact emergency services or the managing agent.
- The text model cannot override the rule-based danger flags. **An unflagged issue is not proven safe.**
- Never instruct residents to repair gas or electrical equipment themselves.
- The assistant provides suggestions, not a legally reliable diagnosis, a verified photograph assessment, or an approval to dispatch contractors.
- The agent remains responsible for decisions, contractor credential checks, spending approvals and sign-off.
- Inputs remain private to the Roger instance and its configured model. By default only loopback/Docker-local Ollama URLs are allowed; sending to a remote model requires a deliberate `ROGER_REPAIR_ALLOW_REMOTE_MODEL=1` setting and your own data-protection review.
- Reports are still manually submitted. Until then interview state exists only in the tenant's browser; the API is stateless.

## Tests and acceptance gates

CI uses the repository's existing Python regression suite plus ten synthetic fault scenarios, role/property isolation, invalid-photo checks, AI-down fallback, a mocked local vision model and inline JavaScript compilation.

**This is not yet full Fixflo/Aidenn parity.** Before using with real customers:

1. Run a populated four-role browser journey on a disposable deployment.
2. Test a real installed text model and vision model with consented synthetic photos.
3. Review false positives/negatives on a larger safety dataset and fit-for-purpose escalation policies.
4. Add rate limits and monitoring for model inference; review user privacy, retention and consent.
5. Verify tenant report → agent review → contractor quote → landlord approval → completion → tenant sign-off and finance in real browser tests.

Do not merge this experiment into the production branch, push to Hostinger or touch customer data without separate acceptance.
