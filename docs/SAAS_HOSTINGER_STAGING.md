# Roger: first Hostinger SaaS staging rehearsal (NOT live deployment)

Status: PREPARATION. Safe capacity and Compose configuration can be checked
without starting new applications. This plan must not be run as a bulk paste
or with customer records. No commands in the preparation section change
Hostinger production.

## Known VPS snapshot (13 October 2026)

- Hostinger KVM 1, one vCPU and 3.8 GiB total memory
- 2.1 GiB MemAvailable, 0 swap, 29 GiB available root disk
- 1-minute load 0.02 at the time measured
- Live Roger + its PostgreSQL, Hermes, Ollama, Project Universe, Traefik, and
  temporary Roger development containers were running
- These numbers are a quiet-time snapshot; they do not prove paid-customer
  capacity. Ollama model loading and Hermes spikes can use much more memory.

## Isolation rules

1. Keep live `roger`, `roger-postgres`, `/docker/roger`,
   `/docker/roger-postgres` and `agency.lifecompass.shop` untouched.
2. Stage only with agency IDs `stg-oak` and `stg-birch`.
   Generated container names are namespaced under `roger-stg-oak-` and
   `roger-stg-birch-`. Never reuse a live agency ID or volume.
3. Stage only under a NEW `/root/roger-staging` directory with synthetic
   users/properties, separate DB credentials and never a copied live database.
4. Use `ops/saas/staging-limits.yaml` as a SECOND Compose file on every
   staging action. Staging app: 192 MiB RAM, 0.20 CPU, 64 PIDs; staging
   PostgreSQL: 256 MiB, 0.12 CPU, 64 PIDs. Both agencies together:
   max 896 MiB RAM across these four containers and 0.64 CPU in quotas.
   Quotas do not protect against resource use during image builds or from
   other processes, and the host has no swap.
5. The staging override disables Traefik discovery. App ports bind only to
   `127.0.0.1:29101` and `127.0.0.1:29102`. NO DNS or public TLS routes.
6. No auto restart for staging. Never run unrestricted
   `docker compose down -v`, `docker system prune`, or any action with a
   wildcard encompassing live Roger. Never store secrets in GitHub logs.
7. Each run requires a healthy live Roger and PostgreSQL, at least 1.75 GiB
   available RAM, at least 12 GiB available disk, and a quiet CPU.
   Those thresholds indicate permission to attempt a controlled rehearsal,
   not that the deployment is guaranteed safe.

## Preparation (READ-ONLY; first allowed commands on VPS)

From a checked out COPY of the reviewed staging branch (not a production
checkout), run:

    python3 ops/saas/staging_preflight.py

If GO, separately generate two agency bundles with
`ops/saas/provision_agency.py` using *fresh* private directories and pinned
`roger-saas:<actual-tested-commit>` image. Provisioning writes new files
and new random credentials, but does not create containers or DNS.
Do not use the example image reference as an assumed real image.

Inspect each generated Compose configuration with:

    docker compose -f /root/roger-staging/stg-oak/compose.yaml \
      -f /path/to/checkout/ops/saas/staging-limits.yaml \
      --env-file /root/roger-staging/stg-oak/.env config --quiet

Repeat for `stg-birch`. Also inspect the full rendered Compose configuration
privately to verify app port, labels, memory, CPUs, project names, storage paths
and database credentials without printing it to public logs.
**Do not launch staging until the actual tested image is available locally,
the preflight has passed again, and the generated configuration has been
reviewed.** Initial image acquisition/build needs its own capacity budget.

## Controlled launch and acceptance (AFTER operator go-ahead only)

- Start `stg-oak` first, with BOTH Compose files and `--env-file`,
  a bounded `--wait --wait-timeout 180`, and observe `docker stats`.
  Stop if live Roger becomes unhealthy, the host reports significant
  memory pressure, or a service repeatedly crashes.
- Once stable, launch `stg-birch` with its separate configuration. Never
  run a bare Compose `up` without the staging override.
- Repeat the already-automated two-agency isolation, one-time invitation,
  first-login password rotation, admin recovery and four-role workflows
  using synthetic identities. Confirm no public Traefik routers.
- Run a bounded multi-user concurrency check; Roger currently uses
  a single-threaded Python HTTP server, so observe latency and failed
  requests rather than assuming safe production throughput.
- Create and inspect a PostgreSQL custom-format dump and the agency's
  uploaded-file snapshot without including `.env`, initial credentials,
  or RAM-backed recovery handoffs in a public artifact. Restore to a
  THIRD disposable database, not back over either running database.
  Explicitly verify restored tenant/property records and login behavior.
- Test short periods of simulated traffic while tracking host RAM, disk,
  load, Docker OOM kills and live Roger response times. Keep Hermes/Ollama
  normal usage visible; a tiny idle benchmark is insufficient.
- Stop staging only by exact staged project names, retaining test volumes
  until backup/restore signoff. Removing staged volumes must be a separate
  explicit decision after confirming IDs and synthetic-only records.
- Report measured peak RSS/CPU, request latency, response errors,
  database restore times, and peak disk usage before suggesting VPS sizing.

## Outstanding launch blockers

A quiet 4 GiB VPS may run two tiny staging agencies, but it has just one
CPU and no swap. Do not sell based on that experiment alone. Customer
operations still require external encrypted backups, verified restores,
monitoring/alerting, recovery ownership, confidentiality/data processing
agreements, a load-capable request server, stronger user lifecycle,
subscription billing and a production security review. The existing
production SSH deployment workflow is NOT repurposed to run code from a
draft feature branch; it carries privileged host access.
