#!/usr/bin/env python3
"""Validate or import Roger's JSON snapshots into the PostgreSQL bridge schema."""
import argparse
import json
import os
from pathlib import Path


COLLECTIONS = {
    "parties": ("roger_parties", "id"),
    "properties": ("roger_properties", "id"),
    "tenancies": ("roger_tenancies", "id"),
    "cases": ("roger_cases", "id"),
    "jobs": ("roger_jobs", "id"),
    "documents": ("roger_documents", "id"),
}


def read_json(path, required=False):
    if not path.exists():
        if required:
            raise FileNotFoundError(str(path))
        return {}
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(path.name + " must contain a JSON object")
    return value


def validate_stage(stage):
    warnings = []
    ids = {}
    for collection, (_, id_field) in COLLECTIONS.items():
        records = stage.get(collection, [])
        if not isinstance(records, list):
            raise ValueError(collection + " must be a list")
        seen = set()
        for record in records:
            if not isinstance(record, dict) or record.get(id_field) is None:
                raise ValueError(collection + " contains a record without an ID")
            key = str(record[id_field])
            if key in seen:
                raise ValueError(collection + " contains duplicate ID " + key)
            seen.add(key)
        ids[collection] = seen
    property_ids = ids["properties"]
    party_ids = ids["parties"]
    for tenancy in stage.get("tenancies", []):
        if tenancy.get("property_id") and str(tenancy["property_id"]) not in property_ids:
            warnings.append("tenancy " + str(tenancy["id"]) + " references an unknown property")
        tenant_ids = tenancy.get("tenant_party_ids") or []
        landlord_ids = tenancy.get("landlord_party_ids") or []
        if not isinstance(tenant_ids, list) or not isinstance(landlord_ids, list):
            warnings.append("tenancy " + str(tenancy["id"]) + " has malformed Party links")
            continue
        for party_id in tenant_ids + landlord_ids:
            if str(party_id) not in party_ids:
                warnings.append("tenancy " + str(tenancy["id"]) + " references an unknown Party")
    for collection in ("cases", "jobs", "documents"):
        for record in stage.get(collection, []):
            property_id = record.get("property_id")
            if property_id and str(property_id) not in property_ids:
                warnings.append(collection + " " + str(record["id"]) + " references an unknown property")
    return warnings


def check_source(data_dir):
    root = Path(data_dir)
    stage = read_json(root / "stage.json", required=True)
    users = read_json(root / "users.json", required=True)
    warnings = validate_stage(stage)
    counts = {name: len(stage.get(name, [])) for name in COLLECTIONS}
    return stage, users, counts, warnings


def migrate(source_dir, database_url):
    if not database_url:
        raise ValueError("DATABASE_URL is required for PostgreSQL import")
    stage, users, counts, warnings = check_source(source_dir)
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError('Install psycopg with: pip install "psycopg[binary]>=3.2,<4"') from exc
    schema_path = Path(__file__).resolve().parents[1] / "migrations" / "001_postgres_stage_schema.sql"
    statements = [part.strip() for part in schema_path.read_text(encoding="utf-8").split(";") if part.strip()]
    with psycopg.connect(database_url) as connection:
        for statement in statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO roger_stage_snapshot(singleton_id,payload) VALUES (1,%s::jsonb) "
            "ON CONFLICT(singleton_id) DO UPDATE SET payload=EXCLUDED.payload, imported_at=now()",
            (json.dumps(stage),),
        )
        connection.execute(
            "INSERT INTO roger_users_snapshot(singleton_id,payload) VALUES (1,%s::jsonb) "
            "ON CONFLICT(singleton_id) DO UPDATE SET payload=EXCLUDED.payload, imported_at=now()",
            (json.dumps(users),),
        )
        for collection, (table, id_field) in COLLECTIONS.items():
            connection.execute("TRUNCATE TABLE " + table)
            for record in stage.get(collection, []):
                record_id = str(record[id_field])
                if table in ("roger_tenancies", "roger_cases", "roger_jobs", "roger_documents"):
                    connection.execute(
                        "INSERT INTO " + table + "(id,property_id,case_id,payload) VALUES (%s,%s,%s,%s::jsonb)",
                        (record_id, str(record.get("property_id")) if record.get("property_id") is not None else None, str(record.get("case_id")) if record.get("case_id") is not None else None, json.dumps(record)),
                    ) if table in ("roger_jobs", "roger_documents") else connection.execute(
                        "INSERT INTO " + table + "(id,property_id,payload) VALUES (%s,%s,%s::jsonb)",
                        (record_id, str(record.get("property_id")) if record.get("property_id") is not None else None, json.dumps(record)),
                    )
                else:
                    connection.execute(
                        "INSERT INTO " + table + "(id,payload) VALUES (%s,%s::jsonb)",
                        (record_id, json.dumps(record)),
                    )
    return counts, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=os.environ.get("DATA_DIR", str(Path(__file__).resolve().parents[1] / "stage-clone")))
    parser.add_argument("--check-only", action="store_true", help="validate IDs/links without connecting to PostgreSQL")
    args = parser.parse_args()
    if args.check_only:
        stage, users, counts, warnings = check_source(args.source)
    else:
        counts, warnings = migrate(args.source, os.environ.get("DATABASE_URL", ""))
    print(json.dumps({"imported": counts, "warnings": warnings}, indent=2))


if __name__ == "__main__":
    main()
