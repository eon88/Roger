"""England 2026 periodic-tenancy regression and property access tests."""
from datetime import date
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import tenancy_2026 as policy
import serve


class PeriodicTenancyUnitTests(TestCase):
    def test_standard_monthly_periodic_has_no_end(self):
        x = policy.assured_periodic_terms("2026-09-01", "monthly", 120000, 100000)
        self.assertEqual(x["tenancy_type"], "assured_periodic")
        self.assertEqual(x["rental_period"], "monthly")
        self.assertIsNone(x["fixed_term_end_date"])

    def test_no_new_annual_or_quarterly_period(self):
        for name in ("annually", "quarterly", "yearly"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                policy.assured_periodic_terms("2026-10-01", name, 120000, 100000)

    def test_deposit_cap_and_threshold(self):
        # £1200/month => £14,400/year; 5 weeks maximum is about £1,384.61.
        policy.assured_periodic_terms("2026-10-01", "monthly", 120000, 138461)
        with self.assertRaises(ValueError):
            policy.assured_periodic_terms("2026-10-01", "monthly", 120000, 138462)
        # £60k/year => six weeks.
        policy.assured_periodic_terms("2026-10-01", "monthly", 500000, 692307)
        with self.assertRaises(ValueError):
            policy.assured_periodic_terms("2026-10-01", "monthly", 500000, 692308)

    def test_legacy_start_becomes_periodic_from_first_may(self):
        x = policy.assured_periodic_terms("2024-09-01", "monthly", 95000, 0)
        self.assertEqual(x["periodic_from"], "2026-05-01")

    def test_section13_limits(self):
        tenancy = {"tenancy_type": "assured_periodic", "status": "active",
                   "start_date": "2026-06-01", "rent_amount_pence": 120000}
        notice = policy.rent_increase_proposal(
            tenancy, 130000, "2027-04-01", "2027-06-01", date(2027,4,5))
        self.assertEqual(notice["notice_form"], "Form 4A (Section 13)")
        with self.assertRaises(ValueError):
            policy.rent_increase_proposal(tenancy, 130000, "2027-04-01",
                                          "2027-05-01", date(2027,4,5))
        with self.assertRaises(ValueError):
            policy.rent_increase_proposal(tenancy, 130000, "2026-06-01",
                                          "2026-12-01", date(2026,6,1))
        tenancy["last_rent_increase_effective_at"] = "2027-07-01"
        with self.assertRaises(ValueError):
            policy.rent_increase_proposal(tenancy, 130000, "2027-11-01",
                                          "2028-01-01", date(2027,11,1))

    def test_notice_not_automatically_served_or_applied(self):
        tenancy = {"tenancy_type": "assured_periodic", "status": "active",
                   "start_date": "2025-01-01", "rent_amount_pence": 110000}
        notice=policy.rent_increase_proposal(
            tenancy, 120000, "2026-09-01", "2026-11-01", date(2026,9,1))
        self.assertIs(notice["actual_service_verified"], False)
        tenancy["pending_rent_increase"] = notice
        with self.assertRaises(ValueError):
            policy.confirm_rent_increase(tenancy, date(2026,10,31))
        notice["tenant_objection_status"] = "disputed"
        with self.assertRaises(ValueError):
            policy.confirm_rent_increase(tenancy, date(2026,11,8))
        notice["tenant_objection_status"] = "not_recorded"
        amount, when=policy.confirm_rent_increase(tenancy, date(2026,11,8))
        self.assertEqual((amount,when),(120000,"2026-11-01"))

    def test_pet_requires_human_reason_and_single_decision(self):
        obj=policy.pet_request("One small indoor cat", "2026-11-08T10:00:00Z")
        decision=policy.pet_decision(obj,"refused","The building rules prohibit animals.","2026-11-08")
        obj.update(decision)
        self.assertEqual(obj["status"],"refused")
        with self.assertRaises(ValueError):
            policy.pet_decision(obj,"approved","Changed mind","2026-11-09")


class TenancyPolicyHandlerTests(TestCase):
    def setUp(self):
        self.stage={
            "parties":[{"id":"tenant-a","status":"active","roles":["tenant"],"account_id":"acc-a"},
                       {"id":"tenant-b","status":"active","roles":["tenant"],"account_id":"acc-b"},
                       {"id":"landlord-1","status":"active","roles":["landlord"],"account_id":"acc-landlord"}],
            "properties":[{"id":"flat-a","tenant_party_id":"tenant-a"},
                          {"id":"flat-b","tenant_party_id":"tenant-b"}],
            "tenancies":[{"id":"t-a","property_id":"flat-a","tenant_party_ids":["tenant-a"],
                          "landlord_party_ids":["landlord-1"],"start_date":"2025-01-01",
                          "status":"active","tenancy_type":"assured_periodic",
                          "rent_amount_pence":90000,"rent_frequency":"monthly"},
                         {"id":"t-b","property_id":"flat-b","tenant_party_ids":["tenant-b"],
                          "landlord_party_ids":["landlord-1"],"start_date":"2026-09-01",
                          "status":"active","tenancy_type":"assured_periodic",
                          "rent_amount_pence":100000,"rent_frequency":"monthly"}],
            "audit_log":[]
        }
        self.h=serve.H.__new__(serve.H)
        self.h.user={"role":"tenant","account_id":"acc-a","username":"tenant-a"}
        self.answers=[]
        self.h._json=lambda payload,code=200:self.answers.append((payload,code))
        a=patch.object(serve,"load_stage",return_value=self.stage)
        b=patch.object(serve,"save_stage")
        c=patch.object(serve,"now",return_value="2026-11-08T10:00:00+00:00")
        a.start();b.start();c.start()
        self.addCleanup(a.stop);self.addCleanup(b.stop);self.addCleanup(c.stop)
        self.save=b

    def run_action(self, action, tenancy_id="t-a", **kwargs):
        self.h.handle_tenancy_policy_action({"action":action,"tenancy_id":tenancy_id,**kwargs})
        return self.answers[-1]

    def test_tenant_can_request_pet_once_and_cannot_decide(self):
        got,code=self.run_action("request_pet",request_id="request-pet-001",
                                 description="One indoor cat")
        self.assertEqual(code,200)
        self.assertEqual(got["request"]["status"],"pending_agent_review")
        self.assertEqual(len(self.stage["tenancies"][0]["pet_requests"]),1)
        got,code=self.run_action("request_pet",request_id="request-pet-001",
                                 description="One indoor cat")
        self.assertTrue(got["unchanged"])
        self.assertEqual(len(self.stage["tenancies"][0]["pet_requests"]),1)
        _,code=self.run_action("decide_pet",request_id=got["request"]["id"],
                               decision="approved",reason="Agent review")
        self.assertEqual(code,403)

    def test_foreign_tenant_denied_without_state_change(self):
        _,code=self.run_action("request_pet",tenancy_id="t-b",
                               request_id="request-pet-001",description="One cat")
        self.assertEqual(code,403)
        self.assertFalse(self.stage["audit_log"])

    def test_agent_only_decision_and_scoped_read(self):
        got,code=self.run_action("request_pet",request_id="request-pet-001",
                                 description="One indoor cat")
        petid=got["request"]["id"]
        tenant_view=self.h.tenancy_policy_view(self.stage,self.h.user)
        self.assertEqual([t["id"] for t in tenant_view["tenancies"]],["t-a"])
        self.h.user={"role":"agent","username":"agent-1"}
        got,code=self.run_action("decide_pet",request_id=petid,
                                 decision="approved",reason="Inspected agent response")
        self.assertEqual(code,200)
        self.assertEqual(got["request"]["status"],"approved")
        _,code=self.run_action("decide_pet",request_id=petid,
                               decision="refused",reason="Someone changed their mind")
        self.assertEqual(code,400)

    def test_invalid_rent_increase_proposal_does_not_change_record(self):
        self.h.user={"role":"agent","username":"agent-1"}
        _,code=self.run_action("propose_rent_increase",amount_pence=99000,
                               notice_served_on="2026-11-08",effective_on="2026-12-01")
        self.assertEqual(code,400)
        self.assertNotIn("pending_rent_increase",self.stage["tenancies"][0])

    def test_no_renewal_for_assured_periodic(self):
        self.h.user={"role":"agent","username":"agent-1"}
        self.h.handle_tenancy_action({"action":"transition","id":"t-a","status":"renewal"})
        self.assertEqual(self.answers[-1][1],409)
        self.assertEqual(self.stage["tenancies"][0]["status"],"active")


if __name__=="__main__":
    main()
