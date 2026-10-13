#!/usr/bin/env python3
"""READ-ONLY host capacity gate before disposable Roger SaaS staging.

Does not create, stop, inspect environment secrets, or modify any container.
Thresholds are for an isolated two-agency rehearsal, NOT paid production.
"""
import os
from pathlib import Path
import subprocess
import sys

GIB = 1024 ** 3
MIN_AVAILABLE_MEM = int(1.75 * GIB)
MIN_AVAILABLE_DISK = 12 * GIB
MAX_LOAD_PER_CORE = 0.65
STAGING_CONTAINER_PREFIX = "roger-stg-"


def assess(available_mem, available_disk, load_one, cores, names, healthy):
    problems = []
    warnings = []
    if available_mem < MIN_AVAILABLE_MEM:
        problems.append("Not enough available RAM (minimum 1.75 GiB).")
    if available_disk < MIN_AVAILABLE_DISK:
        problems.append("Not enough available disk (minimum 12 GiB).")
    if not cores or load_one / cores > MAX_LOAD_PER_CORE:
        problems.append("CPU is too busy; try outside a busy period.")
    active = sorted(n for n in names if n.startswith(STAGING_CONTAINER_PREFIX))
    if active:
        problems.append("Existing staging containers found; never overwrite: " + ", ".join(active))
    for name in ("roger", "roger-postgres"):
        if healthy.get(name) != "healthy":
            problems.append("Live " + name + " is not healthy; abort staging.")
    warnings.append("No swap means unexpected Hermes/Ollama RAM spikes can still exhaust memory.")
    warnings.append("This is a momentary check, not a proof of capacity under load.")
    return problems, warnings


def meminfo():
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if ":" in line:
            key, raw = line.split(":", 1)
            parts = raw.strip().split()
            if parts and parts[0].isdigit():
                values[key] = int(parts[0]) * 1024
    return values


def docker_stdout(*args):
    result = subprocess.run(["docker", *args], check=True, capture_output=True,
                            text=True, timeout=12)
    return result.stdout.strip()


def main():
    if sys.platform != "linux":
        raise SystemExit("This preflight is for Linux VPS only.")
    memory = meminfo()
    available = memory.get("MemAvailable", 0)
    disk = os.statvfs("/")
    disk_available = disk.f_bavail * disk.f_frsize
    load_one = os.getloadavg()[0]
    cores = os.cpu_count() or 1

    try:
        names = set(docker_stdout("ps", "-a", "--format", "{{.Names}}").splitlines())
        healthy = {name: docker_stdout("inspect", "--format",
                   "{{.State.Health.Status}}", name)
                   for name in ("roger", "roger-postgres")}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        raise SystemExit("FAIL: could not read Docker status; no staging permitted.")

    problems, warnings = assess(available, disk_available, load_one,
                                cores, names, healthy)
    print("Roger SaaS read-only Hostinger staging preflight")
    print("Available RAM: %.2f GiB" % (available / GIB))
    print("Available disk: %.2f GiB" % (disk_available / GIB))
    print("1-minute CPU load: %.2f on %s logical CPU(s)" % (load_one, cores))
    print("Existing staging containers:", sum(n.startswith(STAGING_CONTAINER_PREFIX)
                                               for n in names))
    for note in warnings:
        print("CAUTION:", note)
    if problems:
        for item in problems:
            print("FAIL:", item)
        print("NO-GO. Live services were not modified.")
        return 1
    print("GO for a short synthetic-only rehearsal with staging resource limits.")
    print("This script did NOT start or modify any containers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
