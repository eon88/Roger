#!/usr/bin/env python3
"""Generate one isolated Roger agency stack. Does not deploy or change DNS.

Run this on a trusted server only. Output contains credentials; never commit it.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "migrations" / "001_postgres_stage_schema.sql"
COLLECTIONS = (
    "properties", "parties", "cases", "registrations", "jobs",
    "approvals", "audit_log", "appointments", "invitations",
    "documents", "tenancies", "management_agreements",
    "rent_ledger_entries", "landlord_statements", "notifications",
    "tasks", "compliance_records", "property_submissions",
    "newsletter_subscriptions",
)
RESERVED = {"admin", "www", "api", "mail", "root", "support", "roger"}
SLUG = re.compile(r"^[a-z][a-z0-9-]{1,28}[a-z0-9]$")
HOST = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
IMAGE = re.compile(r"^roger-saas:[0-9a-f]{12,40}$|^roger-saas@sha256:[0-9a-f]{64}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
AGENCY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &.,'()-]{1,98}[A-Za-z0-9)]$")


def validate(slug, name, admin_email, port, image, base_domain):
    if not SLUG.fullmatch(slug) or "--" in slug or slug in RESERVED:
        raise ValueError("invalid or reserved agency slug")
    if not AGENCY_NAME.fullmatch(name):
        raise ValueError("agency name must be 3-100 ordinary printable characters")
    if not EMAIL.fullmatch(admin_email) or len(admin_email) > 254:
        raise ValueError("invalid agency administrator email")
    if not isinstance(port, int) or not 20000 <= port <= 49999:
        raise ValueError("choose a unique loopback port between 20000 and 49999")
    if not IMAGE.fullmatch(image):
        raise ValueError("image must be roger-saas:<tested commit> or immutable digest")
    if not HOST.fullmatch(base_domain) or ".." in base_domain or "." not in base_domain or len(base_domain) > 150:
        raise ValueError("invalid base DNS domain")


def empty_stage(slug):
    stage = {key: [] for key in COLLECTIONS}
    stage.update({
        "agency_id": slug, "authority": {"standing_limit_pence": 0, "currency": "GBP"},
        "next_case_id": 1, "next_party_id": 1,
    })
    return stage


def single_admin(admin_email):
    password = secrets.token_urlsafe(30)
    salt = secrets.token_hex(16)
    pw_hash = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                             n=2**14, r=8, p=1).hex()
    return {
        "users": [{
            "username": "agency-admin", "role": "agent",
            "display_name": "Agency Administrator", "email": admin_email,
            "account_id": "account-" + secrets.token_hex(16),
            "salt": salt, "hash": pw_hash,
            "password_change_required": True,
        }],
        "sessions": {},
    }, password


def sql_literal(data):
    return "'" + json.dumps(data, separators=(",", ":"), ensure_ascii=True).replace("'", "''") + "'"


def compose_text(slug, hostname, port):
    project = "roger-" + slug
    tick = chr(96)
    return f"""name: {project}
services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: roger
      POSTGRES_DB: roger
      POSTGRES_PASSWORD: DOLLAR{{ROGER_DATABASE_PASSWORD:?missing}}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./bootstrap.sql:/docker-entrypoint-initdb.d/010-roger.sql:ro
    networks: [private]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U roger -d roger"]
      interval: 10s
      timeout: 5s
      retries: 10
  app:
    image: DOLLAR{{ROGER_IMAGE:?missing}}
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      ROGER_SAAS_MODE: "1"
      ROGER_STORAGE_BACKEND: postgres
      ROGER_AGENCY_ID: "{slug}"
      ROGER_AGENCY_NAME: DOLLAR{{ROGER_AGENCY_NAME:?missing}}
      ROGER_PUBLIC_BASE_URL: "https://{hostname}"
      ROGER_ALLOWED_ORIGINS: "https://{hostname}"
      DATABASE_URL: "postgresql://roger:DOLLAR{{ROGER_DATABASE_PASSWORD:?missing}}@postgres:5432/roger"
      DATA_DIR: /data
      BIND_HOST: 0.0.0.0
      PORT: "8901"
    volumes: [agency_files:/data]
    # An ephemeral RAM-backed directory for manual credential recovery.
    # Unlike /data this is never persisted to the agency files volume.
    tmpfs:
      - /run/roger-recovery:mode=0700,size=1048576
    networks: [private, public]
    ports: ["127.0.0.1:{port}:8901"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8901/api/public', timeout=5).read()"]
      interval: 15s
      timeout: 6s
      retries: 8
      start_period: 20s
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network={project}_public"
      - "traefik.http.routers.{project}.rule=Host({tick}{hostname}{tick})"
      - "traefik.http.routers.{project}.entrypoints=websecure"
      - "traefik.http.routers.{project}.tls=true"
      - "traefik.http.routers.{project}.tls.certresolver=letsencrypt"
      - "traefik.http.routers.{project}.service={project}"
      - "traefik.http.services.{project}.loadbalancer.server.port=8901"
networks:
  private:
    internal: true
  public:
    name: {project}_public
volumes:
  postgres_data:
  agency_files:
"""


def provision(slug, name, admin_email, port, image, base_domain, output):
    validate(slug, name, admin_email, port, image, base_domain)
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError("refusing to overwrite an existing agency directory")
    if not SCHEMA.is_file() or not output.parent.is_dir():
        raise ValueError("schema and parent directory must already exist")
    hostname = slug + "." + base_domain
    stage = empty_stage(slug)
    users, password = single_admin(admin_email)
    bootstrap = (
        SCHEMA.read_text().rstrip() + "\n"
        + "INSERT INTO roger_stage_snapshot(singleton_id,payload) VALUES (1,"
        + sql_literal(stage) + "::jsonb);\n"
        + "INSERT INTO roger_users_snapshot(singleton_id,payload) VALUES (1,"
        + sql_literal(users) + "::jsonb);\n"
    )
    os.umask(0o077)
    output.mkdir(mode=0o700)
    def write(filename, data):
        file = output / filename
        with file.open("x", encoding="utf-8") as handle:
            handle.write(data)
        file.chmod(0o600)
    write("compose.yaml", compose_text(slug, hostname, port).replace("DOLLAR{", chr(36) + "{"))
    write("bootstrap.sql", bootstrap)
    # The postgres container runs its init scripts as its own non-root UID.
    # SQL contains ONLY scrypt password hashes, not plaintext credentials.
    # The enclosing agency directory remains 0700 on the host.
    (output / "bootstrap.sql").chmod(0o644)
    write(".env", (
        "ROGER_IMAGE=" + image + "\n"
        + "ROGER_DATABASE_PASSWORD=" + secrets.token_urlsafe(42) + "\n"
        + "ROGER_AGENCY_NAME=" + name + "\n"
    ))
    write("initial-admin-credentials.txt", (
        "HOST=https://" + hostname + "\nUSERNAME=agency-admin\n"
        + "PASSWORD=" + password + "\nADMIN_EMAIL=" + admin_email + "\n"
        + "Delete this file after first-login handoff and password rotation.\n"
    ))
    write("agency.json", json.dumps({
        "agency_id": slug, "name": name, "hostname": hostname,
        "port": port, "image": image, "status": "prepared-not-deployed",
        "billing": "manual-trial-not-active",
    }, indent=2) + "\n")
    return {"agency_id": slug, "hostname": hostname, "directory": str(output),
            "status": "prepared-not-deployed"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--slug", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--admin-email", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--image", required=True)
    p.add_argument("--base-domain", default="agents.lifecompass.shop")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    result = provision(a.slug, a.name, a.admin_email, a.port, a.image,
                       a.base_domain, a.output)
    print(json.dumps(result, indent=2))
    print("Credentials stored in private initial-admin-credentials.txt, not logged.")


if __name__ == "__main__":
    main()
