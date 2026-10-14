"""Fast, database-free HTTP pilot gate tests (no production access)."""
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch
from contextlib import contextmanager
import uuid

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

class AuthenticatedPilotTests(unittest.TestCase):
    def test_authorised_agent_reads_scoped_properties(self):
        agency, user = str(uuid.uuid4()), str(uuid.uuid4())
        h = FakeHandler({"role":"agent","agency_id":agency,"id":user})
        @contextmanager
        def transaction(url, tenant):
            self.assertEqual(tenant,agency)
            yield object()
        with (patch.dict(server.os.environ, {"ROGER_DATABASE_URL":"postgresql://test-only"}),
              patch.object(server.roger_pg,"enabled",return_value=True),
              patch.object(server.roger_pg,"agency_transaction",side_effect=transaction),
              patch.object(server.roger_pg,"assert_membership",return_value="agent") as membership,
              patch.object(server.roger_pg,"list_records",return_value=[{"id":"p1"}])):
            h.do_GET()
            membership.assert_called_once()
        self.assertEqual(h.responses,[(200,{"properties":[{"id":"p1"}]})])

    def test_denied_membership_returns_forbidden(self):
        h = FakeHandler({"role":"agent","agency_id":str(uuid.uuid4()),"id":str(uuid.uuid4())})
        @contextmanager
        def transaction(url, tenant):
            yield object()
        with (patch.dict(server.os.environ, {"ROGER_DATABASE_URL":"postgresql://test-only"}),
              patch.object(server.roger_pg,"enabled",return_value=True),
              patch.object(server.roger_pg,"agency_transaction",side_effect=transaction),
              patch.object(server.roger_pg,"assert_membership",side_effect=PermissionError)):
            h.do_GET()
        self.assertEqual(h.responses[0][0],403)

class AgencyRoleGateTests(unittest.TestCase):
    def test_each_portal_uses_scoped_property_repository(self):
        @contextmanager
        def transaction(url, agency):
            yield object()
        for role in ("agent","tenant","landlord","trades"):
            identity={"role":role,"id":str(uuid.uuid4()),
                      "agency_id":str(uuid.uuid4()),"username":"tester"}
            h=FakeHandler(None)
            h.path="/api/agency/properties"
            h.agency_session_user=lambda identity=identity: identity
            with (patch.dict(server.os.environ, {"ROGER_DATABASE_URL":"postgresql://test-only"}),
                  patch.object(server.roger_pg,"agency_transaction",side_effect=transaction),
                  patch.object(server.roger_pg,"portal_properties",return_value=[{"id":"allowed"}]) as scoped):
                h.do_GET()
                scoped.assert_called_once()
            self.assertEqual(h.responses,[(200,{"properties":[{"id":"allowed"}]})])
