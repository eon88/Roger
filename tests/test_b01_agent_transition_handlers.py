"""B01 live-handler property/tenancy replay: idempotent and auditable."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"stage-clone"))
import serve


class AgentWorkflowReplayTests(unittest.TestCase):
    def setUp(self):
        self.stage={
            "properties":[{"id":"prop-1","lifecycle_status":"onboarding","title":"Test home",
                           "area":"Birmingham","rent":100000,"beds":1,
                           "public_listing":{"description":"Example"}}],
            "tenancies":[{"id":"tenancy-1","property_id":"prop-1",
                          "status":"application","history":[],
                          "tenancy_type":"assured_periodic"}],
            "parties":[],"audit_log":[],
        }
        self.h=serve.H.__new__(serve.H)
        self.h.user={"role":"agent","username":"office","display_name":"Agent"}
        self.out=[];self.h._json=lambda data,status=200:self.out.append((data,status))
        a=patch.object(serve,"load_stage",return_value=self.stage)
        b=patch.object(serve,"save_stage")
        c=patch.object(serve,"now",return_value="2026-11-10T14:00:00Z")
        for p in (a,b,c):p.start();self.addCleanup(p.stop)

    def test_property_changing_status_records_one_event_per_request(self):
        args={"property_id":"prop-1","status":"ready_to_market",
              "request_id":"prop-request-0001","reason":"Compliance reviewed"}
        self.h.handle_property_action(args)
        self.assertEqual(self.out[-1][1],200)
        self.assertEqual(self.stage["properties"][0]["lifecycle_history"][-1]["request_id"],
                         "prop-request-0001")
        self.h.handle_property_action(args)
        self.assertEqual(self.out[-1][0]["unchanged"],True)
        self.assertEqual(len(self.stage["properties"][0]["lifecycle_history"]),1)
        self.h.handle_property_action({**args,"status":"advertised"})
        self.assertEqual(self.out[-1][1],409)
        self.assertEqual(self.stage["properties"][0]["lifecycle_status"],"ready_to_market")
        self.assertEqual(len(self.stage["audit_log"]),1)

    def test_tenancy_lifecycle_refuses_replayed_id_for_new_state(self):
        args={"action":"transition","id":"tenancy-1","status":"referencing",
              "request_id":"tenant-transition-001","reason":"Application received"}
        self.h.handle_tenancy_action(args)
        self.assertEqual(self.out[-1][1],200)
        self.assertEqual(self.stage["tenancies"][0]["history"][-1]["request_id"],
                         "tenant-transition-001")
        self.h.handle_tenancy_action(args)
        self.assertEqual(self.out[-1][0]["unchanged"],True)
        self.h.handle_tenancy_action({**args,"status":"approved"})
        self.assertEqual(self.out[-1][1],409)
        self.assertEqual(self.stage["tenancies"][0]["status"],"referencing")
        self.assertEqual(len(self.stage["tenancies"][0]["history"]),1)

    def test_bad_reason_rejected_without_changing_state(self):
        self.h.handle_property_action({
            "property_id":"prop-1","status":"ready_to_market",
            "reason":"x"*501})
        self.assertEqual(self.out[-1][1],400)
        self.assertEqual(self.stage["properties"][0]["lifecycle_status"],"onboarding")
        self.h.handle_tenancy_action({
            "action":"transition","id":"tenancy-1","status":"referencing",
            "reason":"x"*501})
        self.assertEqual(self.out[-1][1],400)
        self.assertEqual(self.stage["tenancies"][0]["status"],"application")

    def test_unauthorised_transition_gate_is_server_defined(self):
        self.assertEqual(serve.H.ROLE_API["/api/property-action"],{"agent"})
        self.assertEqual(serve.H.ROLE_API["/api/tenancy-action"],{"agent"})


if __name__=="__main__":
    unittest.main()
