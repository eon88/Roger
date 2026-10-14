"""Fast, database-free HTTP pilot gate tests (no production access)."""
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch

STAGE = pathlib.Path(__file__).resolve().parents[1] / "stage-clone"
sys.path.insert(0, str(STAGE))
spec = importlib.util.spec_from_file_location("roger_serve_pilot", STAGE / "serve.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

class FakeHandler:
    do_GET = server.H.do_GET
    def __init__(self, user):
        self.path = "/api/hq/properties"
        self.user = user
        self.responses = []
    def require(self, roles):
        return self.user
    def _json(self, payload, code=200):
        self.responses.append((code, payload))

class PilotGateTests(unittest.TestCase):
    def test_disabled_returns_not_found(self):
        h = FakeHandler({"role":"agent"})
        with patch.object(server.roger_pg, "enabled", return_value=False):
            h.do_GET()
        self.assertEqual(h.responses[0][0],404)
    def test_missing_agency_identity_fails_closed(self):
        h = FakeHandler({"role":"agent"})
        with patch.object(server.roger_pg, "enabled", return_value=True):
            h.do_GET()
        self.assertEqual(h.responses[0][0],503)
    def test_unauthenticated_request_never_opens_database(self):
        h = FakeHandler(None)
        with patch.object(server.roger_pg, "agency_transaction") as tx:
            h.do_GET()
            tx.assert_not_called()
