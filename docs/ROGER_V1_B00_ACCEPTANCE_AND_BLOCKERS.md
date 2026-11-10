# Roger v1 — B00 acceptance policy and prioritised work queue

**Date:** 10 November 2026 · **Release line:** PR #14 · **Product:** lettings and property management only.  
**Owner of coding, source inspection, synthetic testing and issue triage:** Roger engineering (ChatGPT-assisted implementation workflow).  
**External release sign-off (not yet assigned):** qualified England property-law reviewer, accounting reviewer, security/privacy reviewer and live deployment operator.

## Standard bundle result template

Copy this into the bundle's evidence section at the end of each implementation pass:

```text
Bundle ID:
Scope / tasks attempted:
Input commit SHA:
Output commit SHA:
Change summary:
Unit suite: PASS / FAIL / NOT RUN — URL, test count
Four-role browser: PASS / FAIL / NOT RUN — URL
Two-agency SaaS: PASS / FAIL / NOT RUN — URL
Mandatory aggregate v1 gate: PASS / FAIL / NOT RUN — URL
Manual or regulated review: PASS / BLOCKED / NOT APPLICABLE — reviewer + dated evidence
Security / privacy negative tests:
Reproducible rollback or data migration proof:
New or unresolved issues: severity, reproduction steps, expected vs actual, assigned bundle
Status: OPEN / PARTIAL / CODED / UNIT PASS / BROWSER PASS / ACCEPTED / BLOCKED
Production touched: NO (must remain NO until B26)
```

**PASS:** The exact tests pass against the named commit, including negative/permission cases.  
**FAIL:** An expected assertion, integration or required check fails. Fix it and rerun.  
**BLOCKED:** Code cannot finish acceptance without legitimate external dependencies (legal or financial review, real provider account, target-host restore evidence). Declare the dependency; don't invent a pass.  
**NOT RUN:** There is no evidence. Never interpret absence of a failed workflow as a pass.

## Severity and triage

- **P0 release blocker:** potential cross-agency privacy leak, lost/corrupted data, wrong accounting, unlawful automatic action, broken tenant safety, or failed mandatory aggregate gate. Stop acceptance and fix first.
- **P1 acceptance blocker:** one of the 12 contracted modules cannot complete its agreed realistic user journey or nontrivial error/negative path.
- **P2 usability/deferred:** low-risk styling, copy, optional performance refinement or nonessential polish with no legal/data/cross-agency effect; may defer only with a clear release note.
- **Non-bug design dependency:** external access or qualified review is not automatically a code defect, but it can still block release.

## Prioritised known gaps (NOT assertions that undocumented code is broken)

| Ref | Priority | Issue to resolve | Bundle | Evidence/next verification |
| --- | --- | --- | --- | --- |
| B00-SEC-01 | P0 gate dependency | Enforce full CI pass and prevent accidental merge/deploy; the repo ruleset list was empty when queried. | B00, B26 | Aggregate CI + admin-enforced status protection still needs verification; don't call GitHub settings protected without proof. |
| B01-DATA-01 | P0 acceptance risk | Historical/parallel record updates, schema and cross-entity integrity not accepted. | B01, B04 | Migration, concurrency, restored clone and cross-agency fixtures. |
| B08-LET-01 | P1 | End-to-end applicant → referencing → legally valid tenancy conversion missing. | B07–B09 | Full browser journey on canonical records and denied/withdrawn branches. |
| B11-FIN-01 | P0 regulated release dependency | Rent, deposit returns, landlord statement and external financial reconciliation are not accepted as production accounting. | B10–B12, B23 | Exact-pence fixtures, accountant validation and disclosure review. |
| B14-OPS-01 | P1 | Complete repair job exception paths remain unaccepted, despite tested happy paths. | B13–B14 | Quote rejection, unsafe trade, missed visit, reopen, variation and invoice denial. |
| B15-AI-01 | P0 AI/safety gate | Actual vision-model image inference and broader fault-risk benchmark not demonstrated. | B15 | Genuine model + model-down + photo attack + safety false-negative tests. |
| B16-INV-01 | P1 | Full check-in vs checkout comparison and evidence revision/phone-photo journey not accepted. | B16, B18 | E2E inventory comparison and access control. |
| B19-MSG-01 | P1 | Actual provider-backed email and durable retry/dead-letter handling not demonstrated. | B19–B20 | Test provider, delivery and duplicate rejection, privacy and bounces. |
| B23-LEG-01 | P0 external sign-off | Qualified tenancy, landlord, deposits and client-money review not recorded. | B23 | Reviewer credentials, written outcomes, legal configuration effective dates. |
| B24-UX-01 | P1 | All role/mobile journeys and accessibility not accepted end-to-end. | B24 | Android-width / desktop browser suite and accessibility report. |
| B26-OPS-01 | P0 | Hostinger-like backup, offsite recovery, capacity and rollback not proved with a current production-compatible snapshot. | B25–B26 | Verified isolated restore and rollback rehearsal with hashes; **no live operation until release**. |

The queue is intentionally limited to evidence-backed risks and contracted gaps. These rows are not invented production incidents.

## B00 development and CI policy

The baseline is the immutable commit `14073e5ea80b1ab8629882993fdd4b407c9daa1c`. The B00 fixture, code/tests and the new aggregate gate are subsequent **development commits**, not a new customer version.

- All GitHub Actions remain `contents: read` with no deployment, writable token or SSH/production operation. A source policy script now fails on forbidden workflow capabilities.
- `v1-acceptance-gate.yml` requires Python, Chromium and two isolated PostgreSQL SaaS agency suites to pass on the same source SHA; failure/skipped work returns an overall failing gate.
- The reusable synthetic two-agency fixture adds parties, two homes, two tenancies, a contractor, repair and invoice, rent payment, deposit and document metadata in each agency; no login accounts or actual files are created from this fixture.
- A CI check or a draft PR alone cannot substitute for an **admin-enforced GitHub repository rule**. If branch protections cannot be read or set with the available tool, leave hard-enforcement evidence unresolved and add it to the B26 release gate.
- No production merge/install/migration/deployment in B00.

## Bundle acceptance sign-off

B00 can be called **ACCEPTED** only when all six B00 subtasks have evidence, including aggregate green CI on the same revision and a verified, non-deploying development workflow. If an unverified repository ruleset is required to enforce branch protection, record that specifically as BLOCKED and do not falsely claim hard protection.

**Next technical bundle:** B01 — authoritative data model and workflow integrity.
