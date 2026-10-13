"""No-touch Hostinger stage capacity preflight tests."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "ops" / "saas" / "staging_preflight.py"
spec = importlib.util.spec_from_file_location("roger_stage_preflight", MODULE)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class HostingerStagingSafetyTests(unittest.TestCase):
    def check(self, ram=2.1, disk=29, load=0.02, cpus=1,
              names=None, healthy=None):
        if names is None:
            names = {"roger", "roger-postgres", "hermes-agent", "ollama", "project-universe"}
        if healthy is None:
            healthy = {"roger": "healthy", "roger-postgres": "healthy"}
        return preflight.assess(
            int(ram * preflight.GIB), int(disk * preflight.GIB),
            load, cpus, names, healthy)

    def test_observed_host_goes_to_preparation_not_production(self):
        errors, notes = self.check()
        self.assertEqual(errors, [])
        self.assertTrue(any("No swap" in n for n in notes))

    def test_memory_pressure_blocks_rehearsal(self):
        errors, _ = self.check(ram=1.0)
        self.assertTrue(any("RAM" in n for n in errors))

    def test_disk_pressure_blocks_rehearsal(self):
        errors, _ = self.check(disk=8)
        self.assertTrue(any("disk" in n for n in errors))

    def test_load_average_blocks_rehearsal(self):
        errors, _ = self.check(load=0.9)
        self.assertTrue(any("CPU" in n for n in errors))

    def test_live_rogers_must_both_be_healthy(self):
        errors, _ = self.check(healthy={"roger": "unhealthy", "roger-postgres": "healthy"})
        self.assertTrue(any("Live roger" in n for n in errors))

    def test_previous_staging_instances_block_recreation(self):
        errors, _ = self.check(names={"roger", "roger-postgres", "roger-stg-oak-app-1"})
        self.assertTrue(any("staging containers found" in n for n in errors))

    def test_unrelated_old_development_containers_are_not_deleted(self):
        errors, _ = self.check(names={
            "roger", "roger-postgres", "roger-security-lab", "roger-hotfix-test"})
        self.assertEqual(errors, [])

    def test_staging_overlay_limits_and_no_traefik(self):
        text = (ROOT / "ops" / "saas" / "staging-limits.yaml").read_text()
        self.assertIn('traefik.enable: "false"', text)
        self.assertIn('mem_limit: 192m', text)
        self.assertIn('mem_limit: 256m', text)
        self.assertIn('cpus: "0.20"', text)
        self.assertIn('cpus: "0.12"', text)
        self.assertEqual(text.count('restart: "no"'), 2)


if __name__ == "__main__":
    unittest.main()
