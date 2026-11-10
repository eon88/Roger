# Roger v1 — B00 immutable baseline and code inventory

**Captured:** 10 November 2026 · **Baseline commit:** `14073e5ea80b1ab8629882993fdd4b407c9daa1c`  
**Source:** [GitHub immutable commit](https://github.com/eon88/Roger/tree/14073e5ea80b1ab8629882993fdd4b407c9daa1c)  
**Active development branch:** `feature/roger-v1-single-release-20261108`  
**Release PR:** https://github.com/eon88/Roger/pull/14 (draft; no deployment)

## What "baseline" means

This is a permanent comparison point, **not** a release candidate or production snapshot. The cited SHA will not change even when the feature branch progresses. The code was inspected through the private GitHub connector. No credentials, customer data or Hostinger files were read.

**Repository tree at baseline:** 148 tracked blobs; 58 Python/JavaScript test scripts; 4 GitHub workflows; 62 distinct literal `/api/...` route strings in `stage-clone/serve.py`. A literal route is **NOT** proof that an operation works end to end.

## Portals and public pages

- `stage-clone/index.html` — public rental website
- `stage-clone/agent.html` — agent work dashboard
- `stage-clone/landlord.html` — landlord portal
- `stage-clone/tenant.html` — tenant portal
- `stage-clone/trades.html` — contractor portal
- `stage-clone/for-agents.html` — letting-agent acquisition page

## Shared server and domain modules

- `stage-clone/serve.py` — HTTP routes, authentication, record operations, agency-bound read/write and file/PostgreSQL persistence.
- `stage-clone/agency_recovery.py` — isolated agency admin account recovery.
- `stage-clone/repair_diagnosis.py`, `repair_case_dossier.py` — opt-in tenant diagnosis and validated reported evidence.
- `stage-clone/tenancy_2026.py` — assured periodic tenancy, rent notice and pet request rules.
- `stage-clone/inventory_record.py` — inspection, keys/meters, room condition and tenant replies.
- `stage-clone/bank_reconciliation.py` — agent-reconciled external statement evidence, **not bank-verified funds**.
- `stage-clone/deposit_controls.py` — holding/tenancy deposit states, documented evidence and due dates.
- `stage-clone/prs_register.py` — region-based registration review dates, no government-service API.
- `stage-clone/agent_briefing.py` — read-only rules-based priorities, **not autonomous AI**.
- `ops/migration/agency_import.py` — offline preview/apply for limited people/property/tenancy CSVs.
- `ops/saas/provision_agency.py` — two independent app/PostgreSQL stacks and local private provision manifests.

## API inventory (server literals only)

01. `/api/access-revoke`
02. `/api/agency-info`
03. `/api/agent-demo`
04. `/api/agent/briefing`
05. `/api/agent/property-submission`
06. `/api/appointment`
07. `/api/appointment-action`
08. `/api/appointments`
09. `/api/bank-reconciliation-action`
10. `/api/bank-reconciliation-preview`
11. `/api/case-action`
12. `/api/change-password`
13. `/api/compliance`
14. `/api/compliance-action`
15. `/api/contractor-verification`
16. `/api/deposit-action`
17. `/api/deposits`
18. `/api/document`
19. `/api/document-action`
20. `/api/documents`
21. `/api/email-reply`
22. `/api/email-sync`
23. `/api/enquiry`
24. `/api/inventories`
25. `/api/inventory-action`
26. `/api/invitation`
27. `/api/invitation-action`
28. `/api/invite/accept`
29. `/api/invite/validate`
30. `/api/job-action`
31. `/api/landlord-action`
32. `/api/landlord-statement-action`
33. `/api/landlord-statements`
34. `/api/landlord/property-submission`
35. `/api/landlord/rent-ledger`
36. `/api/management-agreement-action`
37. `/api/newsletter`
38. `/api/newsletter-action`
39. `/api/newsletter-subscriptions`
40. `/api/notification-action`
41. `/api/notifications`
42. `/api/office-settings`
43. `/api/party-action`
44. `/api/property-action`
45. `/api/property-registration-action`
46. `/api/prospect-action`
47. `/api/prospect-intake`
48. `/api/public`
49. `/api/public-site`
50. `/api/registration-action`
51. `/api/rent-ledger`
52. `/api/rent-ledger-action`
53. `/api/repair-diagnose`
54. `/api/stage`
55. `/api/task-action`
56. `/api/tasks`
57. `/api/tenancy-action`
58. `/api/tenancy-policy`
59. `/api/tenancy-policy-action`
60. `/api/tenant/issue`
61. `/api/trades-pool`
62. `/api/whoami`

**Next steps for B01/B02:** produce a server-side verb/role/record-scope matrix for every route and add negative tests, because the API inventory above includes route literals but does not prove method coverage or permission enforcement.

## Test inventory (58 files)

- `tests/full_repair_browser.cjs`
- `tests/public_homepage_browser.cjs`
- `tests/repair_diagnosis_browser.cjs`
- `tests/saas_invite_integration.py`
- `tests/saas_two_agency_integration.py`
- `tests/test_agency_csv_migration.py`
- `tests/test_agency_invitations.py`
- `tests/test_agent_repair_triage.py`
- `tests/test_appointment_visit_flow.py`
- `tests/test_approval_appointment_security.py`
- `tests/test_backup.py`
- `tests/test_bank_reconciliation.py`
- `tests/test_case_control.py`
- `tests/test_case_permissions.py`
- `tests/test_contractor_verification.py`
- `tests/test_csrf_origin.py`
- `tests/test_deposit_controls.py`
- `tests/test_document_read_privacy.py`
- `tests/test_finance_controls.py`
- `tests/test_homepage_fixes.py`
- `tests/test_inventory_records.py`
- `tests/test_job_permissions.py`
- `tests/test_landlord_rent_privacy.py`
- `tests/test_logout_method_security.py`
- `tests/test_notification_form_party.py`
- `tests/test_notification_privacy.py`
- `tests/test_office_notifications.py`
- `tests/test_portal_contact_safety.py`
- `tests/test_portal_party_ui.py`
- `tests/test_postgres_migration.py`
- `tests/test_postgres_storage.py`
- `tests/test_prework_spend_control.py`
- `tests/test_property_submissions.py`
- `tests/test_prospect_stages.py`
- `tests/test_prs_register.py`
- `tests/test_public_acquisition.py`
- `tests/test_repair_diagnosis.py`
- `tests/test_repair_loop_end_to_end.py`
- `tests/test_repair_ui_contract.py`
- `tests/test_request_body_limits.py`
- `tests/test_restore_rehearsal.py`
- `tests/test_saas_files_backup_restore.py`
- `tests/test_saas_hostinger_staging.py`
- `tests/test_saas_password_recovery.py`
- `tests/test_saas_password_rotation.py`
- `tests/test_saas_provision.py`
- `tests/test_saas_restore_safety.py`
- `tests/test_saas_staging_concurrency.py`
- `tests/test_saas_staging_document.py`
- `tests/test_session_security.py`
- `tests/test_static_security.py`
- `tests/test_storage.py`
- `tests/test_storage_concurrency.py`
- `tests/test_tenancy_2026.py`
- `tests/test_tenant_ownership.py`
- `tests/test_trades_read_privacy.py`
- `tests/test_v1_operations.py`
- `tests/visit_browser_smoke.cjs`

## Baseline GitHub workflows

- `.github/workflows/browser-smoke.yml`
- `.github/workflows/repair-ollama-browser.yml`
- `.github/workflows/saas-two-agency-pilot.yml`
- `.github/workflows/tests.yml`

At baseline, the ordinary Python, four-role Chromium, and isolated two-agency workflows passed for the same SHA:

- [Python regression](https://github.com/eon88/Roger/actions/runs/42534435383)
- [Four-role Chromium](https://github.com/eon88/Roger/actions/runs/42534435444)
- [Two independent agency stacks](https://github.com/eon88/Roger/actions/runs/42534435415)

The last verified regression count is **503 tests**, not 503 production-acceptance checks. Genuine vision, historical agency data migration, 2026-rule external legal review, provider-backed messaging, and production-like backup/rollback remained open at the baseline.

## Synthetic-data constraints

- `stage-clone/stage.json` contains example/demo records. It is not a production snapshot or a reliable fixture for SaaS agency isolation.
- `tests/repair_diagnosis_browser.cjs` builds synthetic tenant/agent data in a temporary local directory.
- `tests/saas_two_agency_integration.py` starts from empty independent Oak and Birch databases.
- **New B00 work:** `tests/fixtures/v1_two_agency_data.py` generates deterministic, separately tagged people, rental properties, tenancies, trade job with invoice metadata, rent ledger, deposit and document metadata. CI seeds and verifies both independent PostgreSQL instances without creating credentials or actual document bytes.

## Release-safety findings

- No production deploy jobs existed in the four baseline workflows; they used read-only GitHub tokens.
- `tests.yml` ran on pushes; the browser and SaaS workflows used different filters, so there was not yet a **single required green check** covering all three on each v1 development change.
- The branch remains in draft PR #14, **not merged**. GitHub rulesets returned an empty list when reviewed for B00, so administrator-enforced branch protection could not be confirmed. A new aggregate source-policy/unit/browser/SaaS CI check can fail closed but is **not** a replacement for repository ruleset protection before actual merge.
- This document does not authorise a deployment or imply verification of a real off-site production backup.

**Immutable B00 baseline SHA: `14073e5ea80b1ab8629882993fdd4b407c9daa1c`.**
