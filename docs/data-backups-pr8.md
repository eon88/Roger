# Data backup runbook

Roger stores its current data in `stage.json` and `users.json` under `DATA_DIR`. Uploaded document bytes are embedded in the stage snapshot, so the archive includes them.

Create a private validated snapshot:

```bash
DATA_DIR=/path/to/roger-data ROGER_BACKUP_DIR=/path/to/private-backups \
  python scripts/backup_roger_data.py --retention-days 14
```

The script validates both JSON files before writing, creates a compressed archive plus SHA-256 checksum, uses mode `0600`, and removes archives older than the retention window. Keep the backup destination outside the live data directory and on storage with access controls and its own backup policy.

To inspect an archive:

```bash
sha256sum -c roger-data-<timestamp>.tar.gz.sha256
tar -tzf roger-data-<timestamp>.tar.gz
```

For a restore, stop the Roger process, preserve a copy of the current data directory, verify the checksum, extract the archive into a new empty data directory, then point `DATA_DIR` at it and verify login, cases, and document access before reopening service. Do not restore over a running process.

This is an operator-run backup. Scheduling, offsite replication, and automated restore drills still need deployment infrastructure.
