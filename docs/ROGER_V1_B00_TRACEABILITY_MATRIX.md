# Roger v1 B00 — Requirements → code → test → release traceability

**As of:** 10 November 2026 · **Baseline revision:** `14073e5ea80b1ab8629882993fdd4b407c9daa1c`  
**Master contract:** [ROGER_V1_FINAL_SCOPE_FREEZE.md](ROGER_V1_FINAL_SCOPE_FREEZE.md)  
**Work breakdown:** [ROGER_V1_BUNDLED_MASTER_TODO.md](ROGER_V1_BUNDLED_MASTER_TODO.md)  
**Current work:** PR #14, `feature/roger-v1-single-release-20261108`.

This matrix assigns a named accountable *workstream owner* (Roger engineering, supported by the ChatGPT-assisted development workflow) but **does not invent a person or pretend that an independent reviewer has accepted responsibility**. The UK legal/accounting/security review roles are currently unappointed and their release gates remain BLOCKED until a qualified sign-off actually exists.

**Status policy:** ABSENT = no matching implementation; CODED = exists, not sufficient tests; UNIT PASS/BROWSER PASS (subset) = tested components exist; ACCEPTED = the complete frozen requirement, negative paths and external review pass. **There are currently zero ACCEPTED modules**, despite green CI.

## Traceability matrix

| Frozen module | Code-tested status | Current implementation location | Existing tests / evidence source | Known gaps to be closed | Work bundles / gates |
| --- | --- | --- | --- | --- | --- |
| **M01** Agency SaaS/configuration | BROWSER PASS (subset) | `ops/saas/provision_agency.py`, `stage-clone/agency_recovery.py`, `stage-clone/serve.py` | `tests/test_saas_provision.py`, `tests/saas_two_agency_integration.py`, `tests/saas_invite_integration.py` | Agency isolation and account recovery tested; full staff roles, MFA, billing, support and lifecycle open | B02,B03,B22; G01,G08,G11,G12 |
| **M02** Master data/import/export | UNIT PASS (subset) | `stage-clone/serve.py`, `ops/migration/agency_import.py`, `migrations/` | `tests/test_storage.py`, `tests/test_agency_csv_migration.py`, `tests/test_postgres_migration.py` | CSV people/property/tenancy import exists; historical repairs, finance, evidence, export and transactional migrated restore remain | B01,B04; G01,G08,G11 |
| **M03** Landlord onboarding and agreements | BROWSER PASS (subset) | `stage-clone/landlord.html`, `stage-clone/agent.html`, `stage-clone/serve.py` | `tests/test_property_submissions.py`, `tests/test_approval_appointment_security.py`, `tests/full_repair_browser.cjs` | Owner identity/joint owner and full mandate authority/fee/termination integration not accepted | B05; G01,G02 |
| **M04** Rental marketing and applicant journey | BROWSER PASS (subset) | `stage-clone/index.html`, `stage-clone/for-agents.html`, `stage-clone/serve.py` | `tests/test_public_acquisition.py`, `tests/test_prospect_stages.py`, `tests/public_homepage_browser.cjs` | Complete rental viewing→application→referencing→signed tenancy not demonstrated; rental bidding controls need acceptance | B06,B07,B08; G02,G09 |
| **M05** 2026 tenancy lifecycle | BROWSER PASS (subset) | `stage-clone/tenancy_2026.py`, `stage-clone/serve.py`, `stage-clone/tenant.html`, `stage-clone/agent.html` | `tests/test_tenancy_2026.py`, `tests/repair_diagnosis_browser.cjs` | Periodic types, proposed rent and pets exercised; rights-to-rent, legal notices, exceptions, signatures and checkout not accepted | B08,B09; G02,G05,G11 |
| **M06** Money, deposits and owner statements | BROWSER PASS (subset) | `stage-clone/bank_reconciliation.py`, `stage-clone/deposit_controls.py`, `stage-clone/serve.py` | `tests/test_bank_reconciliation.py`, `tests/test_deposit_controls.py`, `tests/test_finance_controls.py`, `tests/test_landlord_rent_privacy.py` | Statement matching manually evidenced; full ledger, owner distribution, deposit return/dispute and regulated client-money review open | B10,B11,B12; G04,G11 |
| **M07** Repairs/contractor workflow | BROWSER PASS (subset) | `stage-clone/repair_case_dossier.py`, `stage-clone/repair_diagnosis.py`, `stage-clone/serve.py` | `tests/test_repair_loop_end_to_end.py`, `tests/full_repair_browser.cjs`, `tests/repair_diagnosis_browser.cjs` | Strong tested core; full exception matrix, safety false-negative benchmark and genuine vision still open | B13,B14,B15; G03,G07 |
| **M08** Inspections, inventories, keys | BROWSER PASS (subset) | `stage-clone/inventory_record.py`, `stage-clone/agent.html`, `stage-clone/tenant.html` | `tests/test_inventory_records.py`, `tests/repair_diagnosis_browser.cjs` | Issue/dispute works; mobile image capture, full condition comparison, schedules and historic evidence review open | B16,B18; G02,G05,G09 |
| **M09** Compliance and complaints | UNIT PASS (subset) | `stage-clone/prs_register.py`, `stage-clone/agent_briefing.py`, `stage-clone/serve.py` | `tests/test_prs_register.py`, `tests/test_contractor_verification.py`, `tests/test_appointment_visit_flow.py` | Registration evidence and warnings work; complete licensing, notices, complaints, policy applicability and external legal review open | B17; G05,G08 |
| **M10** Communications and office workflow | UNIT PASS (subset) | `stage-clone/serve.py`, `stage-clone/agent.html`, `docs/outbound-email-setup.md` | `tests/test_notification_privacy.py`, `tests/test_office_notifications.py`, `tests/test_notification_form_party.py` | Thread/notification portions tested; actual provider delivery/retry/dead-letter and cross-channel audit open | B19,B20; G06,G08 |
| **M11** Agent Desk, AI and reporting | BROWSER PASS (subset) | `stage-clone/agent_briefing.py`, `stage-clone/repair_diagnosis.py`, `stage-clone/agent.html` | `tests/test_v1_operations.py`, `tests/repair_diagnosis_browser.cjs` | Read-only priorities and local text experiment tested; KPI reconciliation, full system search, real vision and AI safety evaluation open | B15,B21; G07,G09 |
| **M12** Commercial launch and operations | UNIT PASS (subset) | `ops/saas/`, `Dockerfile`, `scripts/backup_roger_data.py`, `.github/workflows/` | `tests/test_restore_rehearsal.py`, `tests/test_saas_hostinger_staging.py`, `tests/test_saas_files_backup_restore.py`, `tests/saas_two_agency_integration.py` | Live-like backup, verified offsite restore, VPS load, privacy, commercial terms, billing and release approval still open | B22,B23,B24,B25,B26; G08,G09,G10,G11,G12 |

## Assignments and honest review boundaries

| Requirement | Accountable workstream | External acceptance |
| --- | --- | --- |
| M01 | Roger engineering; external launch operator unassigned | Roger engineering must produce code + QA evidence before acceptance |
| M02 | Roger engineering | Roger engineering must produce code + QA evidence before acceptance |
| M03 | Roger engineering | Roger engineering must produce code + QA evidence before acceptance |
| M04 | Roger engineering | Roger engineering must produce code + QA evidence before acceptance |
| M05 | Roger engineering; UK lettings legal reviewer unappointed | Roger engineering must produce code + QA evidence before acceptance |
| M06 | Roger engineering; independent accounting reviewer unappointed | Pending independent professional review where necessary |
| M07 | Roger engineering; independent safety reviewer unappointed | Roger engineering must produce code + QA evidence before acceptance |
| M08 | Roger engineering | Pending independent professional review where necessary |
| M09 | Roger engineering; independent England compliance adviser unappointed | Pending independent professional review where necessary |
| M10 | Roger engineering | Roger engineering must produce code + QA evidence before acceptance |
| M11 | Roger engineering; AI safety review unappointed | Roger engineering must produce code + QA evidence before acceptance |
| M12 | Roger engineering; live infrastructure/release operator unappointed | Roger engineering must produce code + QA evidence before acceptance |

## 12 non-negotiable release gates

| Gate | Owner of the evidence | What must pass; mapping |
| --- | --- | --- |
| G01 Connected data, portals and permissions | Roger engineering + QA | M01–M03, M07, M10; one authoritative record and no duplicate/foreign references |
| G02 Lettings lifecycle | Roger engineering + QA | M03–M05, M08; full applicant-to-occupied-to-checkout browser journey |
| G03 Repairs exception lifecycle | Roger engineering + QA | M07; all 4-role happy, negative and timeout paths |
| G04 Money and deposits | Roger engineering + independent accountant (unappointed) | M06; exact-pence reconciliation and owner accounting |
| G05 Jurisdictional compliance | Roger engineering + UK property lawyer (unappointed) | M05,M08,M09; rule dates, evidence, warnings and legal boundaries |
| G06 Reliable automation | Roger engineering + QA | M10; actual email provider sends, retries, dead letters and no duplicates |
| G07 Grounded AI and genuine image tests | Roger engineering + independent safety review (unappointed) | M07,M11; real text+vision, safety benchmarks, provenance, fallback |
| G08 Security and privacy | Roger engineering + independent security/privacy reviewer (unappointed) | M01,M02,M05,M09,M10,M12; agency/record denial, secure documents and GDPR flows |
| G09 All-role desktop and phone UX | Roger engineering + QA | M04,M05,M07,M08,M11; complete real browser journeys and accessibility |
| G10 Production-like restore, monitoring and load | Roger engineering + live release operator (unappointed) | M12; independent restored clone, verified rollback, capacity |
| G11 Commercial and legal readiness | Roger engineering + qualified advisers (unappointed) | M01,M02,M05,M06,M12; billing/support/export/legal disclosures |
| G12 One approved final release | Roger release operator (unappointed) | M12, B25–B26; full gate evidence, backup, rollback, deployment once |

## Evidence anchors from pre-B00 baseline

- [503 Python regression tests](https://github.com/eon88/Roger/actions/runs/42534435383) on immutable baseline.
- [Chromium four-role browser acceptance](https://github.com/eon88/Roger/actions/runs/42534435444) on same baseline.
- [Two-agency SaaS isolated container check](https://github.com/eon88/Roger/actions/runs/42534435415) on same baseline.
- [Real Ollama *text* interview, experimental CI](https://github.com/eon88/Roger/actions/runs/42523781359); **not proof of actual image diagnosis**.
- B00 now introduces an aggregate CI gate that must pass *all* three suites on the **same commit**, plus static policy and fixture checks. Its actual run URL and revision must be entered after the run completes.

## Explicitly UNDEMONSTRATED, not quietly assumed working

- Real vision inference + fault-safety false negative review.
- Complete reference provider consent and rental application → signed periodic tenancy flow.
- Historic multi-agency import/export for contracts, repair evidence, finance and attachments.
- Verified outgoing email provider with retry/bounce/dead-letter handling.
- Full deposit returns/disputes and client-money accounting certification.
- Full inventory condition comparison, inspection scheduling, safe file download and signature integration.
- Cross-service security assessment, lawful retention, legal/compliance review.
- Operational SaaS subscription lifecycle, real host load, encrypted backup restore and final rollback.

No module can be promoted to ACCEPTED without documenting a matching CI commit **and** evidence for its missing paths.

**Decision at B00 start: 12 tracked modules, zero fully accepted, one development branch, zero production deployments.**
