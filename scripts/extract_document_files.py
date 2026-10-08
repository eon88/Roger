#!/usr/bin/env python3
"""Move legacy base64 document bodies from stage.json into private file storage."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile


def extract_document_files(stage_path, files_dir, apply=False):
    stage_path = Path(stage_path)
    files_root = Path(files_dir)
    with stage_path.open("r", encoding="utf-8") as handle:
        stage = json.load(handle)
    docs = stage.get("documents", [])
    migrated = 0
    for doc in docs:
        encoded = doc.get("data_b64")
        if not encoded:
            continue
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError("document exceeds current 5 MB limit: " + str(doc.get("id")))
        key = hashlib.sha256(raw).hexdigest()
        folder = files_root / key[:2]
        destination = folder / key
        if apply:
            folder.mkdir(parents=True, mode=0o700, exist_ok=True)
            if not destination.exists():
                fd, temp_name = tempfile.mkstemp(prefix=".roger-file-", dir=folder)
                try:
                    with os.fdopen(fd, "wb") as output:
                        output.write(raw)
                        output.flush()
                        os.fsync(output.fileno())
                    os.chmod(temp_name, 0o600)
                    os.replace(temp_name, destination)
                finally:
                    if os.path.exists(temp_name):
                        os.unlink(temp_name)
            doc["storage_key"] = key
            del doc["data_b64"]
        migrated += 1
    if apply and migrated:
        fd, temp_name = tempfile.mkstemp(prefix=".roger-stage-", dir=stage_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(stage, output, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, stage_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
    return migrated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default=os.path.join(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parents[1] / "stage-clone")), "stage.json"))
    parser.add_argument("--files", default=os.environ.get("ROGER_FILES_DIR", os.path.join(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parents[1] / "stage-clone")), "files")))
    parser.add_argument("--apply", action="store_true", help="write files and remove base64 bodies from stage.json")
    args = parser.parse_args()
    count = extract_document_files(args.stage, args.files, args.apply)
    print(json.dumps({"documents_to_extract": count, "applied": args.apply}))


if __name__ == "__main__":
    main()
