import importlib.util
import json
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "provision_qa_accounts.py"
spec = importlib.util.spec_from_file_location("roger_qa_provision", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class QAProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.data = root / "data"
        self.data.mkdir()
        self.recovery = root / "recovery"
        self.recovery.mkdir()
        self.admin = {
            "username": "agent", "role": "agent", "display_name": "Owner",
            "account_id": "admin-account-1", "salt": "ab" * 16,
            "hash": "existing-hash", "created": "original",
        }
        self.users = {
            "users": [self.admin],
            "sessions": {"existing-session": {"username": "agent", "exp": "2999-01-01T00:00:00Z"}},
        }
        self.stage = {
            "parties": [], "next_party_id": 1, "audit_log": [],
            "properties": [{"id": "a-real-property"}], "cases": [],
        }
        (self.data / "users.json").write_text(json.dumps(self.users))
        (self.data / "stage.json").write_text(json.dumps(self.stage))

    def test_dry_run_does_not_write(self):
        self.assertIsNone(module.provision(self.data, None, False))
        self.assertEqual(json.loads((self.data / "users.json").read_text()), self.users)
        self.assertEqual(json.loads((self.data / "stage.json").read_text()), self.stage)

    def test_four_accounts_have_unique_passwords_and_party_links(self):
        backup = module.provision(self.data, self.recovery, True)
        users = json.loads((self.data / "users.json").read_text())
        stage = json.loads((self.data / "stage.json").read_text())
        self.assertEqual(users["users"][0], self.admin)
        self.assertEqual(users["sessions"], self.users["sessions"])
        self.assertEqual(len(users["users"]), 5)
        self.assertEqual(len(stage["parties"]), 4)
        self.assertEqual(stage["properties"], self.stage["properties"])
        self.assertEqual(stage["next_party_id"], 5)
        self.assertEqual(len(stage["audit_log"]), 4)
        self.assertEqual(len({x["account_id"] for x in users["users"]}), 5)
        secrets = (backup / "qa-credentials.txt").read_text()
        passwords = [line.partition(": ")[2] for line in secrets.splitlines()
                     if line.startswith("Password: ")]
        self.assertEqual(len(set(passwords)), 4)
        for idx, (name, role, _) in enumerate(module.ACCOUNTS):
            user = users["users"][idx + 1]
            self.assertEqual((user["username"], user["role"]), (name, role))
            self.assertEqual(stage["parties"][idx]["account_id"], user["account_id"])
            actual_hash = hashlib.scrypt(passwords[idx].encode(),
                    salt=bytes.fromhex(user["salt"]), n=2**14, r=8, p=1).hex()
            self.assertEqual(actual_hash, user["hash"])
        self.assertEqual(os.stat(backup).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(backup / "qa-credentials.txt").st_mode & 0o777, 0o600)
        self.assertEqual(json.loads((backup / "users.json").read_text()), self.users)
        self.assertEqual(json.loads((backup / "stage.json").read_text()), self.stage)
        with self.assertRaises(ValueError):
            module.provision(self.data, self.recovery, True)

    def test_refuses_unexpected_extra_admin(self):
        self.users["users"].append({"username": "dev", "role": "agent"})
        (self.data / "users.json").write_text(json.dumps(self.users))
        with self.assertRaises(ValueError):
            module.provision(self.data, self.recovery, True)
        self.assertEqual(list(self.recovery.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
