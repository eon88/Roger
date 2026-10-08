#!/usr/bin/env python3
"""Create a private, validated archive of Roger's JSON data store."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile
from datetime import datetime, timezone


def create_backup(source_dir, destination_dir, retention_days=14, files_dir=None):
    source = Path(source_dir).resolve()
    destination = Path(destination_dir).resolve()
    if destination == source or source in destination.parents:
        raise ValueError("backup destination must be outside the live data directory")
    files = [source / name for name in ("stage.json", "users.json") if (source / name).is_file()]
    if not files:
        raise FileNotFoundError("no stage.json or users.json found in the data directory")
    for path in files:
        with path.open("r", encoding="utf-8") as f:
            json.load(f)
    file_root = Path(files_dir).resolve() if files_dir else source / "files"
    if file_root.is_symlink():
        raise ValueError("document storage directory cannot be a symlink")
    if file_root.exists() and any(p.is_symlink() for p in file_root.rglob("*")):
        raise ValueError("document storage contains a symlink")
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive_path = destination / ("roger-data-" + stamp + ".tar.gz")
    temp_path = archive_path.with_suffix(".tar.gz.tmp")
    try:
        with tarfile.open(temp_path, "w:gz") as archive:
            for path in files:
                archive.add(path, arcname=path.name, recursive=False)
            if file_root.is_dir():
                archive.add(file_root, arcname="files", recursive=True)
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, archive_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    checksum_path.write_text(digest + "  " + archive_path.name + "\n", encoding="utf-8")
    os.chmod(checksum_path, 0o600)
    cutoff = datetime.now(timezone.utc).timestamp() - max(1, retention_days) * 86400
    for old in destination.glob("roger-data-*.tar.gz*"):
        if old != archive_path and old.stat().st_mtime < cutoff:
            old.unlink()
    return archive_path, checksum_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=os.environ.get("DATA_DIR", str(Path(__file__).resolve().parents[1] / "stage-clone")))
    parser.add_argument("--destination", default=os.environ.get("ROGER_BACKUP_DIR", str(Path(__file__).resolve().parents[1] / "backups")))
    parser.add_argument("--retention-days", type=int, default=14)
    args = parser.parse_args()
    archive, checksum = create_backup(args.source, args.destination, args.retention_days,
                                        os.environ.get("ROGER_FILES_DIR"))
    print(str(archive))
    print(str(checksum))


if __name__ == "__main__":
    main()
