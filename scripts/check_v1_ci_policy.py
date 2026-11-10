#!/usr/bin/env python3
"""B00 CI release policy: checks that the Roger v1 branch only runs lab tests.

This is a source-level guard, not a substitute for GitHub branch rulesets,
permissions audits or a production backup / manual release approval.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
NAMES = ("tests.yml", "browser-smoke.yml", "saas-two-agency-pilot.yml",
         "repair-ollama-browser.yml", "v1-acceptance-gate.yml")
MANDATORY = ("tests.yml", "browser-smoke.yml", "saas-two-agency-pilot.yml")
GATE = "v1-acceptance-gate.yml"


def read(name):
    path = WORKFLOWS / name
    if not path.is_file():
        raise AssertionError("Missing workflow: " + name)
    return path.read_text(encoding="utf-8")


def check():
    all_workflows = list(WORKFLOWS.glob("*.yml")) + list(WORKFLOWS.glob("*.yaml"))
    if not all_workflows:
        raise AssertionError("No GitHub Actions workflows found")
    required_set = set(NAMES)
    current_set = {p.name for p in all_workflows}
    assert required_set <= current_set, "Missing a required B00 release workflow"

    for workflow in all_workflows:
        s = workflow.read_text(encoding="utf-8")
        assert re.search(r"(?m)^permissions:\s*$", s), workflow.name + ": missing permissions declaration"
        assert re.search(r"(?m)^\s{2}contents:\s*read\s*$", s), workflow.name + ": permissions not read-only"
        # Treat a new deployment action as failing the branch gate until explicitly reviewed.
        forbidden = (
            r"(?mi)^\s*(?:environment|deployment|deploy|id-token):\s*",
            r"(?mi)^\s*contents:\s*write\s*$",
            r"(?mi)^\s*packages:\s*write\s*$",
            r"(?mi)^\s*pull-requests:\s*write\s*$",
            r"(?mi)^\s*-\s*uses:\s*[^\n]*(?:appleboy/ssh-action|azure/webapps-deploy|"
            r"aws-actions/amazon-ecs-deploy-task-definition|cloudflare/wrangler-action)",
            r"(?mi)^\s*(?:ssh|scp|rsync|kubectl)\s+.*",
        )
        for pattern in forbidden:
            if re.search(pattern, s):
                raise AssertionError(workflow.name + ": possible release/deployment capability: " + pattern)
    for name in MANDATORY:
        assert re.search(r"(?m)^\s{2}workflow_call:\s*$", read(name)), \
            name + ": not reusable by mandatory v1 bundle gate"
    gate = read(GATE)
    assert "feature/roger-v1-single-release-20261108" in gate
    assert "pull_request:" in gate and "push:" in gate
    for name in MANDATORY:
        assert "./.github/workflows/" + name in gate, \
            "Mandatory suite not present in aggregate gate: " + name
    for job in ("policy", "unit", "browser", "saas"):
        assert re.search(r"(?m)^\s{4}" + job + r":\s*$", gate), "Missing gate job " + job
        assert re.search(r"needs\." + job + r"\.result", gate), \
            "Failed " + job + " suite would not block aggregate gate"
    assert "if: always()" in gate
    assert not re.search(r"\bdeploy(?:ment)?\s*:\s*", gate, re.I)
    return True


if __name__ == "__main__":
    check()
    print("PASS: v1 CI is read-only and aggregates unit, browser and isolated SaaS suites")
