"""Private rented sector registration tracking, official regional deadlines and audit."""
from datetime import date
from pathlib import Path
from unittest import TestCase,main
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"stage-clone"))
import serve
import prs_register as prs
import agent_briefing


class PrivateRentalRegisterTests(TestCase):
    def setUp(self):
        self.stage={
          "properties":[{"id":"p-1","title":"Synthetic West Midlands home","lifecycle_status":"occupied"},
                        {"id":"p-2","title":"Not yet occupied","lifecycle_status":"onboarding"}],
          "documents":[{"id":"doc-1","status":"verified","property_id":"p-1"},
                       {"id":"doc-2","status":"verified","property_id":"p-2"}],
          "audit_log":[],
        }
        self.h=serve.H.__new__(serve.H)
        self.h.user={"role":"agent","username":"office"}
        self.out=[]
        self.h._json=lambda data,status=200:self.out.append((data,status))
        a=patch.object(serve,"load_stage",return_value=self.stage)
        b=patch.object(serve,"save_stage")
        c=patch.object(serve,"now",return_value="2026-11-08T21:00:00Z")
        for x in (a,b,c): x.start();self.addCleanup(x.stop)

    def send(self,data):
        self.h.handle_property_registration_action({"property_id":"p-1",**data})
        return self.out[-1]

    def test_regional_dates_are_checked_against_guidance(self):
        self.assertEqual(prs.ROLLOUT["West Midlands"],("2026-12-15","2027-03-14"))
        self.assertEqual(prs.ROLLOUT["London"],("2027-07-15","2027-10-14"))
        self.assertEqual(prs.ROLLOUT["South West"],("2027-08-15","2027-11-14"))
        self.assertEqual(len(prs.ROLLOUT),9)

    def test_unregistered_occupied_property_yields_due_card(self):
        record,code=self.send({"region":"West Midlands","status":"not_started","notes":""})
        self.assertEqual(code,200)
        obj=agent_briefing.make_briefing(self.stage,today=date(2027,2,15))
        keys=[x["key"] for x in obj["cards"]]
        self.assertIn("prs-registration:p-1",keys)
        self.assertNotIn("prs-registration:p-2",keys)
        row=next(x for x in obj["cards"] if x["key"]=="prs-registration:p-1")
        self.assertEqual(row["due_date"],"2027-03-14")

    def test_registered_requires_evidence_numbers_and_valid_date(self):
        body={"region":"West Midlands","status":"registered",
              "landlord_registration_number":"L123","property_registration_number":"P987",
              "registered_on":"2026-11-07","renewal_date":"2027-11-07",
              "evidence_document_id":"doc-1"}
        data,code=self.send(body)
        self.assertEqual(code,200,data)
        self.assertFalse(data["registration"]["government_api_verified"])
        data,code=self.send({**body,"evidence_document_id":"doc-2"})
        self.assertEqual(code,400)
        data,code=self.send({**body,"property_registration_number":""})
        self.assertEqual(code,400)
        self.assertEqual(len(self.stage["prs_registration_history"]) if "prs_registration_history" in self.stage else 0,0)
        self.assertEqual(len(self.stage["properties"][0]["prs_registration_history"]) if "prs_registration_history" in self.stage["properties"][0] else 0,0)

    def test_exempt_needs_written_basis(self):
        _,code=self.send({"region":"West Midlands","status":"exempt","notes":"yes"})
        self.assertEqual(code,400)
        x,code=self.send({"region":"West Midlands","status":"exempt",
                          "notes":"Housing lawyer confirms supported exempt accommodation."})
        self.assertEqual(code,200)

    def test_missing_region_is_not_marked_compliant(self):
        found=prs.due_for_review(self.stage["properties"][0],date(2027,2,1))
        self.assertIn("Select",found[1])


if __name__=="__main__":
    main()
