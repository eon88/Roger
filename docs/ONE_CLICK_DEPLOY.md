# Roger: deploy from GitHub in one click

The button is **Actions → Deploy Roger (manual) → Run workflow** in the [Roger repository](https://github.com/eon88/Roger/actions/workflows/deploy-roger.yml).

The workflow lives on the **default branch `main`** (required for GitHub's manual Run workflow button). It deploys the latest commit from **`feature/roger-fast-mvp-20261011`**, without merging this feature branch into `main`.

It **does not deploy on push**.

## One-time setup: give GitHub Actions SSH access to the VPS

Sign into the Hostinger VPS as root and run:

```bash
set -e
umask 077
mkdir -p /root/.ssh
chmod 700 /root/.ssh

# Preserve any existing key.
if [ ! -e /root/.ssh/roger-github-actions ]; then
  ssh-keygen -q -t ed25519 -a 64 -N '' \
    -C 'roger-github-actions-deploy' \
    -f /root/.ssh/roger-github-actions
fi

touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
grep -qxF "$(cat /root/.ssh/roger-github-actions.pub)" \
  /root/.ssh/authorized_keys || \
  cat /root/.ssh/roger-github-actions.pub >> /root/.ssh/authorized_keys

echo "SSH deploy key installed."
```

Next open [Roger → Settings → Secrets and variables → Actions](https://github.com/eon88/Roger/settings/secrets/actions) and add **three repository secrets**:

| Secret name | Value |
| --- | --- |
| `ROGER_SSH_HOST` | `srv1991335.hstgr.cloud` (or the reachable VPS public IP) |
| `ROGER_SSH_PRIVATE_KEY` | **Preferred:** the single-line Base64 output of `base64 -w0 /root/.ssh/roger-github-actions; echo` run on your VPS. The workflow also accepts a correctly pasted multiline OpenSSH private key. |
| `ROGER_SSH_KNOWN_HOSTS` | One line obtained *on the VPS* by running `printf '%s ' 'srv1991335.hstgr.cloud'; cat /etc/ssh/ssh_host_ed25519_key.pub` |

**Important:** The hostname at the start of the known-hosts line must exactly match the `ROGER_SSH_HOST` secret. If using the IP for `ROGER_SSH_HOST`, use that same IP instead of the hostname when constructing the known-hosts line.

**The Base64 output is the private key in encoded form, not encryption.** Never paste either format into chat, commit it to GitHub, or share it in an issue. Store it only as the GitHub repository Actions secret. Anyone who can modify the deployment workflow on `main` or run unreviewed code with access to these secrets has root-level power on the VPS. Restrict repository write access and consider replacing root SSH access with a dedicated, restricted deployment identity later.

## Deploy

1. Open [Actions → Deploy Roger (manual)](https://github.com/eon88/Roger/actions/workflows/deploy-roger.yml).
2. Click **Run workflow**, select **main**, and click the confirmation **Run workflow** button.
3. Watch the job. A green check means the code was built, the app was restarted and basic health checks passed.
4. Open [agency.lifecompass.shop](https://agency.lifecompass.shop) and check the Agent and Landlord portals.

## What the workflow does

- Checks out the reviewed deployment script from `main` and the app from `feature/roger-fast-mvp-20261011`.
- Produces an immutable source archive tagged with the exact app commit SHA.
- Transfers it using an SSH private key and pinned host key (not password authentication).
- Builds the image on the Hostinger VPS using the uploaded source; it does **not** rebuild the stale checkout in `/docker/roger`.
- Acquires a lock to reject simultaneous deployments.
- Retains the previous app image/Compose override; pauses Roger briefly to take PostgreSQL and `/data` backups, then switches the Compose image pin.
- Checks container health, `/api/public`, unauthenticated protection and the login endpoint.
- If deployment fails after stopping Roger, restores the previous Compose override and restarts the earlier image. It **does not automatically restore the database**, to avoid discarding writes. The PostgreSQL dump is kept for manual recovery.

Backups are retained under `/root/roger-backups/gha-deploy-...`. Review disk usage periodically.

### Scope and limitations

This is a manual deployment workflow, **not** a PR merge, database migration, or scheduled release. It expects the existing VPS containers `roger` and `roger-postgres`, the existing `/docker/roger` Compose files, and PostgreSQL connection environment file `/docker/roger-postgres/roger-db.env`. These were created during the October 2026 Roger migration.

The workflow requires the one-time GitHub Secrets setup above; it will fail early and will not touch the server if any secret is missing. A green automated health check does not replace a short human check of the affected user workflow. Changes to this workflow should be reviewed carefully because they grant production deployment access.
