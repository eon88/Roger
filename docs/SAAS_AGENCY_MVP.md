# Roger SaaS: individual estate-agency subscriptions

## Phase 1 implementation

For the first paying-agency pilots, Roger runs a SEPARATE application and
PostgreSQL database for every letting agency. A single shared data table or
shared Postgres snapshot is specifically NOT supported; the original Roger
database is still single-agency and some relational projections rebuild
themselves after writes.

The provisioner at ops/saas/provision_agency.py generates one private directory
per agency containing a fresh Docker Compose stack, database bootstrapping
script, per-agency secrets, admin credentials and status manifest. It DOES NOT
create a cloud instance, change DNS or publish anything.

Each customer has:
- A separate branded subdomain, e.g. oaklettings.agents.lifecompass.shop
- Their own app container, PostgreSQL container, DB password and files volume
- A unique Traefik route and diagnostic loopback port
- Their own agency identifier in database snapshots and business records
- One freshly generated agent administrator credential
- Zero demo tenants, landlords, trades, cases or developer accounts
- Their own prospects, listings, repairs and invoice records
- A safe public identity endpoint and branded homepage and sign-in screen

## Technical acceptance

GitHub Actions uses two disposable Docker stacks: Oak Lettings and Birch
Lettings. It exercises login, per-agency DB queries, agency brand, separate
tenant/landlord enquiries, attempts to reuse sessions across agencies, and
denial of starting the app against a foreign agency ID.

The CI job never accesses Hostinger. All synthetic test databases and volumes
are deleted at the end. The existing four-role browser suite still runs.

## How a customer would actually rent Roger

1. A letting agent visits Roger's existing "For letting agents" webpage and
   submits a demo request.
2. The Roger platform operator gives a demonstration, agrees a limited pilot
   licence, monthly price, portfolio size, service areas, data-processing terms
   and support arrangements. Do not claim automated booking or payments.
3. Verify the agency owner and desired subdomain; assign a unique port and
   create the bundle on a secure host using provision_agency.py.
4. Inspect the agency-specific Docker image, private credentials and compose
   configuration; configure DNS and HTTPS. Provision only with explicit
   permission, then verify login and access denial.
5. Privately hand the business owner the one-time admin credentials. On first
   login, Roger now blocks normal portal access until the admin replaces that
   temporary password with a unique password of at least 14 characters.
   All previous sessions for that account are revoked after the change, and
   the admin must sign in again. Delete the plaintext handoff file securely.
   Then enter the verified agency contact and privacy details and onboard staff. Initial username is agency-admin.
6. Each agency runs its own daily portal. Roger's operator manages software
   updates, per-agency backups, billing and technical support.
7. On cancellation, follow a documented notice, export, access suspension and
   deletion policy. Never delete a database merely due to a failed payment.

Pricing should be assessed against actual hosting/support costs. A monthly
base subscription plus a property-volume band is a reasonable proposal, NOT
an active billing plan or currently advertised rate.

## Prepare an agency (never run these against live Roger without approval)

Use this illustrative command from the repository root on a trusted server
with a private existing parent directory:

    python3 ops/saas/provision_agency.py \
      --slug oaklettings --name "Oak Lettings" \
      --admin-email owner@example.com --port 29101 \
      --image roger-saas:1234567890ab \
      --output /srv/roger-agencies/oaklettings

The image reference must match an actual tested build of the SaaS branch; the
above value is an EXAMPLE and cannot be assumed to exist. The output directory
contains one-time password and DB secrets: NEVER commit or upload it. The SQL
file is readable to the PostgreSQL container user only through a 0700 host
directory. The generated Docker Compose creates new named volumes and must
never be run with volume-recreation flags against a real customer's records.

Platform URL and DNS are NOT automatically configured. Wildcard DNS, SSL
resolution and Hostinger Traefik networking must be verified on a staging
machine before launching a genuine agency. Running multiple PostgreSQL
containers needs more RAM/CPU than the current one-agency MVP; capacity tests
are mandatory before any commercial scale.

## First-login password security (development branch)

Newly provisioned agency administrators are marked
`password_change_required=true`. The sign-in response routes them to
`/change-password`. The server refuses the normal authenticated portal pages
and business APIs until they change the password; knowing a temporary password
alone does not unlock the business functions. Changing a password verifies the
current secret, requires at least 14 characters, uses a new scrypt salt and
invalidates all sessions on the account. Login is required again.

This does not yet offer self-service password recovery, invitations, MFA or
email-based provisioning. Losing the admin password requires a carefully
controlled operator recovery procedure, not ad hoc database modification.

## Operator-assisted administrator recovery (development only)

Only after the agency owner has been independently verified, a trusted Roger
operator with privileged access to THAT agency app container may generate one
new temporary password. The process verifies the selected agency against the
database, rotates the administrator's scrypt secret, revokes all existing admin
sessions and requires first-login rotation again. Passwords are **never printed
to the Docker or CI logs** and are written only to a new 0600 file within an
existing operator-owned 0700 directory. Do not keep that file after handoff.

Illustration from the agency's own secure host, with a known agency project
folder and **without touching live Roger**:

    docker compose -f /srv/roger-agencies/oaklettings/compose.yaml \
      --env-file /srv/roger-agencies/oaklettings/.env \
      exec -T app mkdir -m 700 /data/private-recovery
    docker compose -f /srv/roger-agencies/oaklettings/compose.yaml \
      --env-file /srv/roger-agencies/oaklettings/.env \
      exec -T app python /app/agency_recovery.py \
        --agency oaklettings --output /data/private-recovery/admin-once.txt

This is a sensitive manual operator procedure, not a public password-reset
endpoint or an automated email workflow. The operator must securely retrieve
the file, hand the temporary password to the verified owner, remove the file
and record the support action. No paid customer should depend on this without
a reviewed support and identity-check policy.

## What is still required before paid launch

- Secure invitation, forced first-login password rotation, password recovery,
  multi-factor authentication and staff provisioning.
- A central operator dashboard for creating, activating, upgrading and
  suspending subscriptions; a tested actual billing/payment integration.
- An explicit per-agency verified contact/privacy/site configuration.
- Automated encrypted off-server backup, tested per-agency restore, monitoring
  and storage lifecycle, plus deletion/export procedures.
- Real outbound email delivery where claimed, opt-in confirmation, unsubscribe
  and delivery failure handling.
- UK data-protection and processor/controller agreements, service contract,
  availability and support policy, security review, penetration tests.
- Production capacity assessment and a disposable Hostinger rehearsal with
  separate accounts, real TLS and DNS, and full browser/workflow acceptance.

These are outstanding production gates. Phase 1 is a working isolation pilot,
not yet a general-availability SaaS or real subscription billing service.

Do not merge into main or deploy to agency.lifecompass.shop automatically.
