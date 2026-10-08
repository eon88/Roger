# Deploy Roger on the Hostinger VPS

Roger is designed to run as its own Docker container behind the existing Traefik reverse proxy.

## Persistent data

The Docker named volume `roger_data` stores:

- `stage.json` — properties, cases, jobs, approvals, registrations, appointments, documents and audit log.
- `users.json` — password hashes and sessions.
- optional `.env` — API credentials for Jev/OpenRouter.

Rebuilding the image does not overwrite this volume.

## First deployment

Clone the repository on the VPS, then:

```bash
cd Roger
docker compose up -d --build
docker compose ps
docker logs roger
```

On the first start, `docker logs roger` prints the generated passwords for the initial role accounts. Save them.

Test the app directly on the VPS:

```bash
curl -I http://127.0.0.1:8901/
```

## Domain / Traefik

The compose file defaults to:

```text
agency.lifecompass.shop
```

To use a different hostname, create a root `.env` file:

```env
ROGER_HOST=agency.lifecompass.shop
TRAEFIK_CERTRESOLVER=letsencrypt
```

Set `TRAEFIK_CERTRESOLVER` to the resolver name used by the existing Traefik installation.

Create an A record for the chosen hostname pointing to the VPS IP.

## Updating Roger later

```bash
git pull
docker compose up -d --build
```

The application is rebuilt while `roger_data` remains intact.

## Jev / OpenRouter

Roger works without an API key by falling back to keyword triage.

To enable Jev/OpenRouter, place the required key in the persistent data volume's `.env` file. The container reads it through:

```text
HERMES_ENV_FILE=/data/.env
```
