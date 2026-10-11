# Roger: application rollback button

Use [GitHub Actions → Rollback Roger (manual)](https://github.com/eon88/Roger/actions/workflows/rollback-roger.yml), select **main**, click **Run workflow**, and type `ROLLBACK`.

This **changes the live application image**, not the PostgreSQL data or uploaded files.

## Safety rules

- The rollback and normal deploy workflows share the same production deployment lock.
- The script uses the trusted GitHub Actions SSH credentials, not interactive VPS access.
- It selects the most recent eligible deployment snapshot only when that deployment's Docker image exactly matches the currently running Roger image.
- It requires the saved previous Docker image and the original deploy's backup. It refuses to guess a target if either is missing.
- For deployments performed before the success-marker upgrade, tick **Allow old pre-button backups**. It still requires the exact running-image match.
- Before stopping Roger, it prepares a forward-recovery image. After stopping it, it takes a **new** PostgreSQL dump and copies the data volume to a private dated backup.
- It updates only the pinned app image, starts Roger, verifies the image and tests public/login routes and anonymous authorization.
- If it fails, it attempts to restore the pre-rollback app image automatically.
- Database migrations are **not** undone. A rollback to older code after a breaking migration may fail; failed app rollback should restore the newer app, but this does not guarantee database compatibility.

## No deployment is triggered by installing this button

Creation of the workflow and script is not a rollback or a deploy. A human must manually start the workflow and confirm by typing `ROLLBACK`. The script's result and the recovery-backup location appear in GitHub Actions logs.

If the workflow refuses because the previous image or backup is missing, **do not force an arbitrary Docker tag**. Restore from a reviewed release/back-up plan instead.
