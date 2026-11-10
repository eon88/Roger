"""B00 reusable synthetic scenario: deterministic and cross-agency-safe."""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests" / "fixtures" / "v1_two_agency_data.py"
spec = importlib.util.spec_from_file_location("v1_two_agency_data", SCRIPT)
data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data)


class TwoAgencyFixtureTests(unittest.TestCase):
    def setUp(self):
        self.a = data.build("oaklettings")
        self.b = data.build("birchlettings")

    def test_complete_synthetic_journeys_and_relationships(self):
        for stage in (self.a, self.b):
            self.assertTrue(data.validate(stage))
            for name, minimum in (
                ("parties", 5), ("properties", 2), ("tenancies", 2),
                ("registrations", 1), ("cases", 1), ("jobs", 1),
                ("rent_ledger_entries", 1), ("deposit_records", 1),
                ("documents", 1)
            ):
                self.assertGreaterEqual(len(stage[name]), minimum, name)
            self.assertGreater(stage["jobs"][0]["invoice"]["amount_pence"], 0)
            self.assertTrue(stage["properties"][0]["tenant_party_id"])
            self.assertIsNone(stage["parties"][0]["account_id"])
            self.assertEqual(stage["documents"][0]["status"], "metadata_only")

    def test_every_id_scoped_to_one_agency(self):
        ids_a = {x["id"] for v in self.a.values() if isinstance(v, list) for x in v}
        ids_b = {x["id"] for v in self.b.values() if isinstance(v, list) for x in v}
        self.assertFalse(ids_a & ids_b)
        self.assertTrue(all("oaklettings" in key for key in ids_a))
        self.assertTrue(all("birchlettings" in key for key in ids_b))
        self.assertNotEqual(self.a["agency_id"], self.b["agency_id"])

    def test_reproducible_without_clock_or_randomness(self):
        self.assertEqual(data.build("oaklettings"), self.a)
        result = subprocess.check_output(
            [sys.executable, str(SCRIPT), "--agency", "oaklettings"], text=True)
        self.assertEqual(json.loads(result), self.a)

    def test_invalid_agency_slug_rejected(self):
        for val in ("", "oak/../../live", "UPPER", "a", "--production", "a b"):
            with self.subTest(val=val), self.assertRaises(ValueError):
                data.build(val)

    def test_mutation_does_not_cross_into_other_fixture(self):
        self.a["parties"][0]["display_name"] = "Changed"
        self.assertNotEqual(self.a["parties"][0]["display_name"],
                            self.b["parties"][0]["display_name"])
        self.assertTrue(data.validate(self.a))
        self.assertTrue(data.validate(self.b))


if __name__ == "__main__":
    unittest.main()
