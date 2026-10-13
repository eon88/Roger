#!/usr/bin/env python3
"""Bounded read-only concurrency smoke test of TWO disposable Roger staging agencies.

Four independent synthetic admin sessions (two per agency), three concurrent
GET /api/stage rounds. No live Roger HTTP requests or business-data writes.
This is deliberately NOT a production capacity benchmark.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median
import json
import math
import os
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path("/root/roger-staging")
AGENCIES = (("stg-oak", 29101), ("stg-birch", 29102))
CONTAINERS = (
    "roger", "roger-postgres",
    "roger-stg-oak-app-1", "roger-stg-oak-postgres-1",
    "roger-stg-birch-app-1", "roger-stg-birch-postgres-1",
)
USERS_PER_AGENCY = 2
ROUNDS = 3
SESSION_COUNT = len(AGENCIES) * USERS_PER_AGENCY
MEMORY_MIN_BEFORE = 1536 * 1024 * 1024
MEMORY_MIN_DURING = 1280 * 1024 * 1024
REQUEST_TIMEOUT = 6


def available_memory():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("unable to check available memory")


def healthy_containers():
    for name in CONTAINERS:
        try:
            response = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Health.Status}}", name],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, check=True, timeout=8)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            raise RuntimeError("required container not accessible: " + name) from None
        if response.stdout.strip() != "healthy":
            raise RuntimeError("container unhealthy: " + name)


def agency_manifest(slug, port):
    folder = ROOT / slug
    if folder.is_symlink() or not folder.is_dir():
        raise RuntimeError("expected private agency directory missing")
    manifest = json.loads((folder / "agency.json").read_text())
    if manifest.get("agency_id") != slug or manifest.get("port") != port:
        raise RuntimeError("staging identity/port mismatch: " + slug)
    if not str(manifest.get("hostname", "")).startswith(slug + "."):
        raise RuntimeError("staging hostname mismatch: " + slug)
    return manifest


def api(base, path, *, cookie=None, payload=None, origin=None):
    if not base.startswith("http://127.0.0.1:"):
        raise ValueError("only loopback staging URLs are permitted")
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if origin:
        headers["Origin"] = "https://" + origin
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(base + path, data=body, headers=headers,
                  method="POST" if body is not None else "GET")
    start = time.perf_counter()
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            result = json.loads(response.read())
            elapsed = time.perf_counter() - start
            return response.status, result, response.headers.get("Set-Cookie", ""), elapsed
    except HTTPError as exc:
        raise RuntimeError("staging returned HTTP " + str(exc.code) + " for " + path) from None
    except (URLError, TimeoutError):
        raise RuntimeError("staging request failed or timed out: " + path) from None


def preflight():
    if available_memory() < MEMORY_MIN_BEFORE:
        raise RuntimeError("under 1.5 GiB memory available: load test not started")
    if os.getloadavg()[0] > 0.75 * (os.cpu_count() or 1):
        raise RuntimeError("server load too high: load test not started")
    healthy_containers()
    manifests = []
    for slug, port in AGENCIES:
        manifests.append(agency_manifest(slug, port))
    return manifests


def independent_sessions(manifests):
    sessions = []
    for manifest in manifests:
        slug = manifest["agency_id"]
        base = "http://127.0.0.1:" + str(manifest["port"])
        for _ in range(USERS_PER_AGENCY):
            status, login, set_cookie, _ = api(
                base, "/login", origin=manifest["hostname"],
                payload={"username": "agency-admin",
                         "password": "new-unique-agency-password-" + slug})
            if status != 200 or login.get("role") != "agent" or login.get("password_change_required"):
                raise RuntimeError("synthetic staging login not in expected test state: " + slug)
            cookie = set_cookie.split(";", 1)[0]
            if not cookie or "=" not in cookie:
                raise RuntimeError("staging login gave no session cookie")
            status, stage, _, _ = api(base, "/api/stage", cookie=cookie)
            if status != 200 or stage.get("agency_id") != slug:
                raise RuntimeError("staging isolation mismatch: " + slug)
            sessions.append((slug, base, cookie))
    if len(sessions) != SESSION_COUNT:
        raise RuntimeError("wrong synthetic session count")
    return sessions


def simultaneous_rounds(sessions):
    barrier = threading.Barrier(SESSION_COUNT)
    def worker(session):
        slug, base, cookie = session
        samples = []
        for round_index in range(ROUNDS):
            if available_memory() < MEMORY_MIN_DURING:
                raise RuntimeError("available memory fell below 1.25 GiB; stopped")
            try:
                barrier.wait(timeout=14)
            except threading.BrokenBarrierError:
                raise RuntimeError("simultaneous request coordination failed") from None
            status, body, _, elapsed = api(base, "/api/stage", cookie=cookie)
            if status != 200 or body.get("agency_id") != slug:
                raise RuntimeError("agency isolation or HTTP failure: " + slug)
            samples.append((slug, elapsed))
            if round_index + 1 < ROUNDS:
                time.sleep(1.5)
        return samples

    with ThreadPoolExecutor(max_workers=SESSION_COUNT) as pool:
        futures = [pool.submit(worker, item) for item in sessions]
        records = []
        for future in futures:
            records.extend(future.result(timeout=40))
    return records


def report(samples):
    times = sorted(elapsed * 1000 for _, elapsed in samples)
    if len(times) != SESSION_COUNT * ROUNDS:
        raise RuntimeError("not all simulated requests completed")
    p95 = times[math.ceil(len(times) * 0.95) - 1]
    print("PASS: " + str(SESSION_COUNT) + " separate sessions across two agencies")
    print("PASS: " + str(len(times)) + " concurrent-round authenticated reads; no errors")
    print("Latency median: %.0f ms; p95: %.0f ms; slowest: %.0f ms" %
          (median(times), p95, max(times)))
    return p95


def main():
    try:
        manifests = preflight()
        print("PASS: staging-only, healthy production, resources sufficient", flush=True)
        sessions = independent_sessions(manifests)
        samples = simultaneous_rounds(sessions)
        report(samples)
        healthy_containers()
        if available_memory() < MEMORY_MIN_DURING:
            raise RuntimeError("memory too low after concurrency test")
        print("PASS: live Roger and both staging agencies still healthy")
        print("BOUNDED CONCURRENCY SMOKE TEST PASSED")
        print("NOTE: This small test does not establish production user capacity.")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        # No cookies/passwords or response bodies ever printed.
        print("STOP: staging concurrency test: " + str(exc)[:160],
              file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
